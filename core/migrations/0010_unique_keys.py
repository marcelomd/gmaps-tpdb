from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_merge_case_duplicates'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='class',
            constraint=models.UniqueConstraint(fields=('key',), name='unique_class_key'),
        ),
        migrations.AddConstraint(
            model_name='subclass',
            constraint=models.UniqueConstraint(fields=('clas', 'key'), name='unique_subclass_key_per_class'),
        ),
        migrations.AddConstraint(
            model_name='treatment',
            constraint=models.UniqueConstraint(fields=('key',), name='unique_treatment_key'),
        ),
    ]
