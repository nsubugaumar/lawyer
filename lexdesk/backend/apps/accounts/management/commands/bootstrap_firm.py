from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User
from apps.accounts.provisioning import activation_link, provision_user


class Command(BaseCommand):
    help = (
        "First-run setup. Creates the firm's first administrator automatically. "
        "Safe to run on every deploy: it does nothing once an administrator exists."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--first-name", default="Firm")
        parser.add_argument("--last-name", default="Administrator")

    def handle(self, *args, **opts):
        if User.objects.filter(role=Role.ADMIN, is_active=True).exists():
            self.stdout.write("An administrator already exists. Nothing to do.")
            return

        email = opts["email"].strip().lower()
        if "@" not in email:
            raise CommandError("Please give a real email address.")

        user, _ = provision_user(
            email=email, first_name=opts["first_name"], last_name=opts["last_name"], role=Role.ADMIN,
        )
        user.is_superuser = True
        user.save(update_fields=["is_superuser"])

        self.stdout.write(self.style.SUCCESS(f"Administrator account created for {email}."))
        self.stdout.write("An activation email has been sent. If email is not set up yet, use this one-time link:")
        self.stdout.write(f"  {activation_link(user)}")
        self.stdout.write("The link expires in 3 days and works once.")
