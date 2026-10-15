from django.conf import settings
from django.db import migrations


def assign(apps, schema_editor):
    """
    Everything that existed before LexDesk held many firms belonged to the one
    firm it served. Give each record that firm, so nothing becomes invisible.
    """
    Firm = apps.get_model("firm", "Firm")
    User = apps.get_model("accounts", "User")
    Client = apps.get_model("clients", "Client")
    Matter = apps.get_model("matters", "Matter")
    Appointment = apps.get_model("appointments", "Appointment")

    has_data = User.objects.exists() or Client.objects.exists() or Matter.objects.exists()
    if not has_data:
        return
    firm = Firm.objects.order_by("pk").first()
    if firm is None:
        firm = Firm.objects.create(name=settings.LEXDESK_FIRM_NAME, slug="main", code="LD")

    User.objects.filter(firm__isnull=True).update(firm=firm)
    Client.objects.filter(firm__isnull=True).update(firm=firm)
    Matter.objects.filter(firm__isnull=True).update(firm=firm)
    Appointment.objects.filter(firm__isnull=True).update(firm=firm)


class Migration(migrations.Migration):

    dependencies = [
        ("firm", "0003_firm_tenancy"),
        ("accounts", "0002_user_firm"),
        ("clients", "0002_client_firm"),
        ("matters", "0003_matter_firm_note_court_event"),
        ("appointments", "0003_appointment_firm"),
    ]

    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
