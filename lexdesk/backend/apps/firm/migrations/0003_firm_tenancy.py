import django.core.validators
from django.db import migrations, models
from django.utils.text import slugify


def name_existing_firms(apps, schema_editor):
    Firm = apps.get_model("firm", "Firm")
    used_slugs, used_codes = set(), set()
    for i, firm in enumerate(Firm.objects.order_by("pk")):
        base = slugify(firm.name)[:50] or "firm"
        slug, n = base, 2
        while slug in used_slugs:
            slug, n = f"{base}-{n}", n + 1
        # The first firm keeps "LD" so its existing case numbers still match.
        code = "LD" if i == 0 else "".join(w[0] for w in firm.name.split() if w[:1].isalpha()).upper()[:6] or f"F{i}"
        while code in used_codes or len(code) < 2:
            code = (code + "X")[:6]
        used_slugs.add(slug)
        used_codes.add(code)
        Firm.objects.filter(pk=firm.pk).update(slug=slug, code=code)


class Migration(migrations.Migration):

    dependencies = [
        ("firm", "0002_testimonials"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel("FirmSettings", "Firm"),
        migrations.AlterModelOptions(name="firm", options={"ordering": ["name"]}),
        # No index yet: the unique index below brings it. Indexing here too makes
        # PostgreSQL create the same "_like" index twice and the migration fail.
        migrations.AddField("firm", "slug", models.SlugField(max_length=60, null=True, db_index=False)),
        migrations.AddField("firm", "code", models.CharField(max_length=6, null=True)),
        migrations.AddField("firm", "domain", models.CharField(blank=True, max_length=200, help_text="The firm's own website domain, if any, e.g. www.nsc-advocates.co.ug")),
        migrations.AddField("firm", "is_active", models.BooleanField(default=True, help_text="A suspended firm cannot sign in")),
        migrations.AddField("firm", "created_at", models.DateTimeField(auto_now_add=True, null=True)),
        migrations.RunPython(name_existing_firms, migrations.RunPython.noop),
        migrations.AlterField("firm", "slug", models.SlugField(max_length=60, unique=True, help_text="Web address name, e.g. namubiru-ssempala")),
        migrations.AlterField(
            "firm", "code",
            models.CharField(
                max_length=6, unique=True, help_text="Starts every case and invoice number, e.g. NSC-2026-0001",
                validators=[django.core.validators.RegexValidator("^[A-Z]{2,6}$", "Two to six capital letters, e.g. NSC.")],
            ),
        ),
    ]
