from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Authority(BaseModel):
    """
    The firm's own research library: the cases, statutes and precedents its
    lawyers rely on, with their own summaries. One lawyer's research
    becomes the whole firm's, and the next brief starts from it.
    """

    class Kind(models.TextChoices):
        CASE = "case", "Case law"
        STATUTE = "statute", "Statute / regulation"
        PRECEDENT = "precedent", "Precedent / pleading"
        OPINION = "opinion", "Legal opinion"
        ARTICLE = "article", "Article / commentary"
        PRACTICE = "practice", "Practice direction"

    firm = models.ForeignKey("firm.Firm", on_delete=models.CASCADE, related_name="authorities")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CASE, db_index=True)
    title = models.CharField(max_length=300, help_text="e.g. Mulindwa v. Uganda Breweries Ltd")
    citation = models.CharField(max_length=200, blank=True, help_text="e.g. [2019] UGCA 42")
    court = models.CharField(max_length=200, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    practice_area = models.CharField(max_length=20, blank=True)
    summary = models.TextField(blank=True, help_text="What it decides, in the firm's own words")
    key_points = models.TextField(blank=True, help_text="Holdings and quotable passages, one per line")
    tags = models.CharField(max_length=300, blank=True, help_text="Comma separated")
    url = models.URLField(blank=True, help_text="Link to the full text, e.g. on ULII")
    document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                 help_text="The full text, if filed on a matter")
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(BaseModel.Meta):
        ordering = ["-year", "title"]
        verbose_name_plural = "authorities"

    def __str__(self):
        return f"{self.title} {self.citation}".strip()
