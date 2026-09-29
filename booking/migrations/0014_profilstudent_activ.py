from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0013_rezervare_unica_pe_slot_activ"),
    ]

    operations = [
        migrations.AddField(
            model_name="profilstudent",
            name="activ",
            field=models.BooleanField(default=True),
        ),
    ]
