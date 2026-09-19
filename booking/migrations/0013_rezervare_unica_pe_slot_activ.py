from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0012_camin_api_test"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="rezervare",
            constraint=models.UniqueConstraint(
                condition=models.Q(("anulata", False)),
                fields=("masina", "data_rezervare", "ora_start"),
                name="rezervare_unica_pe_slot_activ",
            ),
        ),
    ]
