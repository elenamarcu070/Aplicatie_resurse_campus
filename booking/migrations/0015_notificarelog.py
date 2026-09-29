from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0014_profilstudent_activ"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificareLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("destinatar", models.CharField(max_length=20)),
                ("sablon", models.CharField(max_length=64)),
                ("message_sid", models.CharField(blank=True, db_index=True, max_length=64)),
                ("stare", models.CharField(default="in_asteptare", max_length=24)),
                ("cod_eroare", models.CharField(blank=True, max_length=16)),
                ("detaliu", models.TextField(blank=True)),
                ("creat_la", models.DateTimeField(auto_now_add=True)),
                ("actualizat_la", models.DateTimeField(auto_now=True)),
                ("profil", models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="notificari", to="booking.profilstudent")),
            ],
            options={"ordering": ["-creat_la", "-id"]},
        ),
    ]
