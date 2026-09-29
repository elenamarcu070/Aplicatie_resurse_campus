from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0015_notificarelog"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificarelog",
            name="canal",
            field=models.CharField(
                choices=[("whatsapp", "WhatsApp"), ("push", "Push în browser")],
                default="whatsapp",
                max_length=16,
            ),
        ),
    ]
