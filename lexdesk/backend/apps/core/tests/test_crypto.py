from django.test import SimpleTestCase

from apps.core.crypto import DecryptionError, SealedBlob, decrypt_text, encrypt_text, rewrap, seal, unseal


class EnvelopeEncryptionTests(SimpleTestCase):
    def test_round_trip(self):
        sealed = seal(b"Witness statement of J. Okello", associated_data=b"doc-1")
        self.assertNotIn(b"Okello", sealed.ciphertext)
        self.assertEqual(unseal(sealed, associated_data=b"doc-1"), b"Witness statement of J. Okello")

    def test_each_file_gets_its_own_key(self):
        a = seal(b"same", associated_data=b"x")
        b = seal(b"same", associated_data=b"x")
        self.assertNotEqual(a.ciphertext, b.ciphertext)
        self.assertNotEqual(a.wrapped_key, b.wrapped_key)

    def test_a_single_flipped_bit_is_detected(self):
        sealed = seal(b"Exhibit P1", associated_data=b"doc-1")
        tampered = bytearray(sealed.ciphertext)
        tampered[-1] ^= 0x01
        with self.assertRaises(DecryptionError):
            unseal(SealedBlob(bytes(tampered), sealed.wrapped_key, sealed.key_id), associated_data=b"doc-1")

    def test_files_cannot_be_swapped_between_records(self):
        sealed = seal(b"Client A's will", associated_data=b"doc-A")
        with self.assertRaises(DecryptionError):
            unseal(sealed, associated_data=b"doc-B")

    def test_rewrap_keeps_the_file_readable(self):
        sealed = seal(b"Board resolution", associated_data=b"doc-9")
        rewrapped = rewrap(sealed)
        self.assertNotEqual(rewrapped.wrapped_key, sealed.wrapped_key)
        self.assertEqual(unseal(rewrapped, associated_data=b"doc-9"), b"Board resolution")


class FieldEncryptionTests(SimpleTestCase):
    def test_round_trip_and_no_plaintext(self):
        token = encrypt_text("CM90012345ABCD")
        self.assertNotIn("CM90012345", token)
        self.assertEqual(decrypt_text(token), "CM90012345ABCD")
