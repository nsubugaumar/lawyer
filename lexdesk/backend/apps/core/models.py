import uuid

from django.db import models


class BaseModel(models.Model):
    """
    Every LexDesk record gets a random UUID instead of 1, 2, 3...

    Sequential ids leak business information (how many clients you have) and
    invite people to try /documents/1235 after seeing /documents/1234. UUIDs
    close that door, and the object-level permission checks lock it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class ReferenceCounter(models.Model):
    """Hands out human-friendly numbers like LD-2026-0042, one per year."""

    prefix = models.CharField(max_length=16)
    year = models.PositiveIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("prefix", "year")]

    @classmethod
    def next(cls, prefix: str, year: int) -> str:
        from django.db import transaction

        # select_for_update makes two receptionists opening matters at the
        # same second get different numbers, not the same one.
        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(prefix=prefix, year=year)
            counter.last_value += 1
            counter.save(update_fields=["last_value"])
            return f"{prefix}-{year}-{counter.last_value:04d}"
