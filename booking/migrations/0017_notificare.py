from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0016_notificarelog_canal"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notificare",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titlu", models.CharField(max_length=120)),
                ("corp", models.TextField(blank=True)),
                ("link", models.CharField(blank=True, max_length=200)),
                ("citita", models.BooleanField(default=False)),
                ("creat_la", models.DateTimeField(auto_now_add=True)),
                ("profil", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="notificari_primite", to="booking.profilstudent")),
            ],
            options={"ordering": ["-creat_la", "-id"]},
        ),
    ]
