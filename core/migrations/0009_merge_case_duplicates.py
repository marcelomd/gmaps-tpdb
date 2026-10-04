from types import SimpleNamespace

from django.db import migrations

from core.merge import dedupe_all


def merge_case_duplicates(apps, schema_editor):
    names = [
        "Class", "Subclass", "Treatment", "Compound",
        "ClassAlias", "SubclassAlias", "TreatmentAlias",
    ]
    dedupe_all(SimpleNamespace(**{n: apps.get_model("core", n) for n in names}))


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_keys_and_aliases'),
    ]

    operations = [
        # Existing rows get their key and any that differ only in letter case are merged,
        # which the unique constraints in the next migration require
        migrations.RunPython(merge_case_duplicates, migrations.RunPython.noop),
    ]
