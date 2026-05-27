from django.db import migrations


def create_api_test_camin(apps, schema_editor):
    Camin = apps.get_model("booking", "Camin")
    Camin.objects.get_or_create(
        nume="API_TEST",
        defaults={"durata_interval": 2},
    )


def remove_api_test_camin(apps, schema_editor):
    Camin = apps.get_model("booking", "Camin")
    Camin.objects.filter(nume="API_TEST").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0011_camin_durata_interval_alter_camin_nume"),
    ]

    operations = [
        migrations.RunPython(create_api_test_camin, remove_api_test_camin),
    ]
