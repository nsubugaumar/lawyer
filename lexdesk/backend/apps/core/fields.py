from django.db import models

from .crypto import decrypt_text, encrypt_text


class EncryptedTextField(models.TextField):
    """
    A text column that is encrypted before it reaches the database.

    Use it for anything you would not want to read in a leaked backup:
    identity numbers, privileged notes, MFA secrets. The trade-off is that
    you cannot filter or search on it, so keep searchable data elsewhere.
    """

    description = "Text encrypted at rest"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        return encrypt_text(value)

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        return decrypt_text(value)
