import re

import pyotp
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.core.testing import PASSWORD, api_as, make_user

LOGIN = "/api/v1/auth/login/"


class LoginTests(TestCase):
    def setUp(self):
        self.user = make_user(Role.LAWYER, email="amina@firm.test")
        self.api = APIClient()

    def test_web_login_puts_refresh_token_in_httponly_cookie_only(self):
        r = self.api.post(LOGIN, {"email": "amina@firm.test", "password": PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertNotIn("refresh", r.data)
        cookie = r.cookies["lexdesk_refresh"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")

    def test_mobile_login_returns_refresh_token_in_body(self):
        r = self.api.post(LOGIN, {"email": "amina@firm.test", "password": PASSWORD}, HTTP_X_LEXDESK_CLIENT="mobile")
        self.assertIn("refresh", r.data)
        self.assertNotIn("lexdesk_refresh", r.cookies)

    def test_email_is_case_insensitive(self):
        r = self.api.post(LOGIN, {"email": "AMINA@Firm.Test", "password": PASSWORD})
        self.assertEqual(r.status_code, 200)

    def test_unknown_email_and_wrong_password_look_identical(self):
        a = self.api.post(LOGIN, {"email": "nobody@firm.test", "password": PASSWORD})
        b = self.api.post(LOGIN, {"email": "amina@firm.test", "password": "wrong"})
        self.assertEqual(a.status_code, b.status_code)
        self.assertEqual(a.data, b.data)

    def test_account_locks_after_repeated_failures(self):
        for _ in range(5):
            self.api.post(LOGIN, {"email": "amina@firm.test", "password": "wrong"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked)
        # Even the right password is refused while locked.
        r = self.api.post(LOGIN, {"email": "amina@firm.test", "password": PASSWORD})
        self.assertEqual(r.status_code, 401)

    def test_refresh_rotates_and_old_token_is_dead(self):
        r = self.api.post(LOGIN, {"email": "amina@firm.test", "password": PASSWORD}, HTTP_X_LEXDESK_CLIENT="mobile")
        old = r.data["refresh"]
        r2 = self.api.post("/api/v1/auth/refresh/", {"refresh": old}, HTTP_X_LEXDESK_CLIENT="mobile")
        self.assertEqual(r2.status_code, 200)
        self.assertNotEqual(r2.data["refresh"], old)
        replay = self.api.post("/api/v1/auth/refresh/", {"refresh": old}, HTTP_X_LEXDESK_CLIENT="mobile")
        self.assertEqual(replay.status_code, 401)

    def test_changing_password_kills_existing_access_tokens(self):
        api = api_as(self.user)
        self.assertEqual(api.get("/api/v1/auth/me/").status_code, 200)
        r = api.post("/api/v1/auth/password/change/", {"current_password": PASSWORD, "new_password": "A-brand-new-Passphrase-77"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(api.get("/api/v1/auth/me/").status_code, 401)


class TwoFactorTests(TestCase):
    def setUp(self):
        self.user = make_user(Role.PARTNER, email="partner@firm.test")
        self.api = APIClient()

    def _enrol(self):
        api = api_as(self.user, mfa=False)
        secret = api.post("/api/v1/auth/mfa/setup/").data["secret"]
        r = api.post("/api/v1/auth/mfa/confirm/", {"code": pyotp.TOTP(secret).now()})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["recovery_codes"]), 10)
        return secret, r.data["recovery_codes"]

    def test_full_mfa_sign_in(self):
        secret, _ = self._enrol()
        self.user.refresh_from_db()
        self.user.mfa_last_used_step = None  # pretend the enrolment code was a while ago
        self.user.save()

        r = self.api.post(LOGIN, {"email": "partner@firm.test", "password": PASSWORD})
        self.assertTrue(r.data["mfa_required"])
        self.assertNotIn("access", r.data)

        r = self.api.post("/api/v1/auth/mfa/verify/", {"mfa_token": r.data["mfa_token"], "code": pyotp.TOTP(secret).now()})
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)

    def test_a_code_cannot_be_used_twice(self):
        secret, _ = self._enrol()  # the enrolment used the current code
        r = self.api.post(LOGIN, {"email": "partner@firm.test", "password": PASSWORD})
        r = self.api.post("/api/v1/auth/mfa/verify/", {"mfa_token": r.data["mfa_token"], "code": pyotp.TOTP(secret).now()})
        self.assertEqual(r.status_code, 401)

    def test_recovery_code_works_exactly_once(self):
        _, codes = self._enrol()
        for expected in (200, 401):
            token = self.api.post(LOGIN, {"email": "partner@firm.test", "password": PASSWORD}).data["mfa_token"]
            r = self.api.post("/api/v1/auth/mfa/verify/", {"mfa_token": token, "code": codes[0]})
            self.assertEqual(r.status_code, expected)

    def test_forged_challenge_is_rejected(self):
        r = self.api.post("/api/v1/auth/mfa/verify/", {"mfa_token": "forged", "code": "123456"})
        self.assertEqual(r.status_code, 401)

    @override_settings(LEXDESK_REQUIRE_MFA_FOR_STAFF=True)
    def test_staff_without_mfa_can_only_set_it_up(self):
        api = api_as(self.user, mfa=False)
        r = api.get("/api/v1/matters/")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["error"]["code"], "mfa_setup_required")
        self.assertEqual(api.post("/api/v1/auth/mfa/setup/").status_code, 200)

    @override_settings(LEXDESK_REQUIRE_MFA_FOR_STAFF=True)
    def test_clients_are_not_forced_into_mfa(self):
        client_user = make_user(Role.CLIENT)
        self.assertEqual(api_as(client_user, mfa=False).get("/api/v1/matters/").status_code, 200)


class AutomaticAccountTests(TestCase):
    """Accounts are created by the system, never by self sign-up."""

    def setUp(self):
        self.admin = make_user(Role.ADMIN, email="admin@firm.test")

    def _link_from_last_email(self):
        body = mail.outbox[-1].body
        uid, token = re.search(r"uid=([\w-]+)&token=([\w-]+)", body).groups()
        return uid, token

    def test_admin_adds_lawyer_and_they_activate_from_the_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            r = api_as(self.admin).post("/api/v1/auth/team/", {
                "email": "new.lawyer@firm.test", "first_name": "Grace", "last_name": "Namubiru", "role": "lawyer",
            })
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(email="new.lawyer@firm.test")
        self.assertFalse(user.has_usable_password())  # nobody chose a password for her

        uid, token = self._link_from_last_email()
        api = APIClient()
        self.assertEqual(api.get(f"/api/v1/auth/activate/?uid={uid}&token={token}").data["first_name"], "Grace")
        r = api.post("/api/v1/auth/activate/", {"uid": uid, "token": token, "password": "Grace-Strong-Passphrase-1"})
        self.assertEqual(r.status_code, 200)

        # The link is single-use.
        r = api.post("/api/v1/auth/activate/", {"uid": uid, "token": token, "password": "Another-Strong-Passphrase-2"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(api.post(LOGIN, {"email": "new.lawyer@firm.test", "password": "Grace-Strong-Passphrase-1"}).status_code, 200)

    def test_weak_password_is_refused_at_activation(self):
        with self.captureOnCommitCallbacks(execute=True):
            api_as(self.admin).post("/api/v1/auth/team/", {
                "email": "x@firm.test", "first_name": "X", "last_name": "Y", "role": "paralegal",
            })
        uid, token = self._link_from_last_email()
        r = APIClient().post("/api/v1/auth/activate/", {"uid": uid, "token": token, "password": "password"})
        self.assertEqual(r.status_code, 400)

    def test_registering_a_client_creates_their_portal_account(self):
        receptionist = make_user(Role.RECEPTIONIST)
        with self.captureOnCommitCallbacks(execute=True):
            r = api_as(receptionist).post("/api/v1/clients/", {"name": "Peter Mugisha", "email": "peter@mail.test", "phone": "+256700000001"})
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data["has_portal_access"])
        portal = User.objects.get(email="peter@mail.test")
        self.assertEqual(portal.role, Role.CLIENT)
        self.assertIn("client portal", mail.outbox[-1].body)

    def test_client_cannot_be_given_a_staff_account_email(self):
        receptionist = make_user(Role.RECEPTIONIST)
        r = api_as(receptionist).post("/api/v1/clients/", {"name": "Sneaky", "email": self.admin.email})
        self.assertFalse(r.data["has_portal_access"])
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, Role.ADMIN)

    def test_only_admins_can_add_staff(self):
        lawyer = make_user(Role.LAWYER)
        r = api_as(lawyer).post("/api/v1/auth/team/", {"email": "a@b.test", "first_name": "A", "last_name": "B", "role": "admin"})
        self.assertEqual(r.status_code, 403)

    def test_team_endpoint_cannot_create_client_accounts(self):
        r = api_as(self.admin).post("/api/v1/auth/team/", {"email": "c@b.test", "first_name": "C", "last_name": "B", "role": "client"})
        self.assertEqual(r.status_code, 400)

    def test_deactivating_staff_ends_their_sessions(self):
        lawyer = make_user(Role.LAWYER, email="leaver@firm.test")
        r = APIClient().post(LOGIN, {"email": "leaver@firm.test", "password": PASSWORD}, HTTP_X_LEXDESK_CLIENT="mobile")
        refresh = r.data["refresh"]
        api_as(self.admin).patch(f"/api/v1/auth/team/{lawyer.id}/", {"is_active": False})
        r = APIClient().post("/api/v1/auth/refresh/", {"refresh": refresh}, HTTP_X_LEXDESK_CLIENT="mobile")
        self.assertEqual(r.status_code, 401)

    def test_forgot_password_does_not_reveal_who_has_an_account(self):
        api = APIClient()
        a = api.post("/api/v1/auth/password/forgot/", {"email": "admin@firm.test"})
        b = api.post("/api/v1/auth/password/forgot/", {"email": "ghost@firm.test"})
        self.assertEqual((a.status_code, a.data), (b.status_code, b.data))
