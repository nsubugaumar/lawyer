from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import TestCase

from apps.audit.models import AuditEvent
from apps.audit.services import record, verify_chain


class AuditChainTests(TestCase):
    def test_an_untouched_chain_verifies(self):
        for i in range(5):
            record("test.event", n=i)
        ok, broken_at, checked = verify_chain()
        self.assertTrue(ok)
        self.assertIsNone(broken_at)
        self.assertEqual(checked, 5)

    def test_events_cannot_be_edited_or_deleted_through_the_app(self):
        event = record("test.event")
        with self.assertRaises(PermissionDenied):
            event.save()
        with self.assertRaises(PermissionDenied):
            event.delete()

    def test_editing_a_row_directly_in_the_database_is_caught(self):
        record("document.downloaded", who="lawyer")
        middle = record("document.downloaded", who="intruder")
        record("auth.logout")

        # Someone with database access tries to cover their tracks.
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE audit_auditevent SET details = %s WHERE id = %s", ['{"who": "lawyer"}', middle.id]
            )

        ok, broken_at, _ = verify_chain()
        self.assertFalse(ok)
        self.assertEqual(broken_at, middle.id)

    def test_deleting_a_row_is_caught(self):
        record("a")
        victim = record("b")
        record("c")
        AuditEvent.objects.filter(pk=victim.pk)._raw_delete(AuditEvent.objects.db)
        ok, _, _ = verify_chain()
        self.assertFalse(ok)
