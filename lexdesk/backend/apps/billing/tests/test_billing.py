from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Role
from apps.core.testing import api_as, make_client, make_matter, make_user


class BillingTests(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER, hourly_rate=Decimal("300000"))
        self.accountant = make_user(Role.ACCOUNTANT)
        self.client_user = make_user(Role.CLIENT)
        self.matter = make_matter(self.lawyer, make_client(portal_user=self.client_user))

    def _log(self, minutes, text="Drafting plaint"):
        r = api_as(self.lawyer).post("/api/v1/billing/time/", {"matter": self.matter.id, "minutes": minutes, "description": text})
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def test_rate_comes_from_the_lawyer_not_the_request(self):
        r = api_as(self.lawyer).post("/api/v1/billing/time/", {
            "matter": self.matter.id, "minutes": 60, "description": "x", "rate": "1",
        })
        self.assertEqual(Decimal(r.data["rate"]), Decimal("300000"))

    def test_time_to_invoice_to_payment(self):
        self._log(90)
        self._log(30, "Call with client")
        api = api_as(self.accountant)

        r = api.post("/api/v1/billing/invoices/generate/", {"matter": str(self.matter.id), "tax_rate": "18.00"})
        self.assertEqual(r.status_code, 201, r.data)
        invoice = r.data
        self.assertEqual(Decimal(invoice["subtotal"]), Decimal("600000.00"))
        self.assertEqual(Decimal(invoice["tax"]), Decimal("108000.00"))
        self.assertEqual(Decimal(invoice["total"]), Decimal("708000.00"))

        # The client cannot see a draft...
        self.assertEqual(api_as(self.client_user).get("/api/v1/billing/invoices/").data["count"], 0)
        api.post(f"/api/v1/billing/invoices/{invoice['id']}/issue/")
        # ...but can see it once issued.
        self.assertEqual(api_as(self.client_user).get("/api/v1/billing/invoices/").data["count"], 1)

        r = api.post(f"/api/v1/billing/invoices/{invoice['id']}/payments/", {"amount": "800000", "method": "mobile_money"})
        self.assertEqual(r.status_code, 400)  # more than owed

        r = api.post(f"/api/v1/billing/invoices/{invoice['id']}/payments/", {"amount": "708000", "method": "mobile_money", "reference": "MP123"})
        self.assertEqual(r.data["status"], "paid")
        self.assertEqual(Decimal(r.data["balance"]), Decimal("0.00"))

    def test_invoiced_time_is_locked(self):
        entry = self._log(60)
        api_as(self.accountant).post("/api/v1/billing/invoices/generate/", {"matter": str(self.matter.id)})
        r = api_as(self.lawyer).patch(f"/api/v1/billing/time/{entry['id']}/", {"minutes": 600})
        self.assertEqual(r.status_code, 400)

    def test_lawyers_cannot_raise_invoices(self):
        self._log(60)
        r = api_as(self.lawyer).post("/api/v1/billing/invoices/generate/", {"matter": str(self.matter.id)})
        self.assertEqual(r.status_code, 403)
