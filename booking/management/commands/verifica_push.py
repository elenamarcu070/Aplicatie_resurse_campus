"""
Verifică dacă notificările push sunt configurate corect.

    railway run -- python manage.py verifica_push
    railway run -- python manage.py verifica_push --trimite-catre email@student.tuiasi.ro

Nu afișează niciodată cheia sau token-urile.
"""

from django.core.management.base import BaseCommand

from booking.models import ProfilStudent
from booking.push import _cont_de_serviciu, _token_acces, trimite_push


class Command(BaseCommand):
    help = "Verifică configurarea notificărilor push și, opțional, trimite una de test."

    def add_arguments(self, parser):
        parser.add_argument(
            "--trimite-catre",
            metavar="EMAIL",
            help="Trimite o notificare de test studentului cu acest email.",
        )

    def handle(self, *args, **optiuni):
        cont = _cont_de_serviciu()
        if not cont:
            self.stdout.write(self.style.ERROR(
                "FIREBASE_SERVICE_ACCOUNT lipsește sau nu poate fi citită. "
                "Vezi jurnalul aplicației pentru motivul exact."
            ))
            return

        self.stdout.write(self.style.SUCCESS("1. Cheia contului de serviciu: citită corect"))
        self.stdout.write(f"   proiect: {cont.get('project_id')}")
        self.stdout.write(f"   cont:    {cont.get('client_email')}")

        try:
            _token_acces(cont)
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"2. Google a respins cheia: {e}\n"
                "   Cheia e probabil dintr-un alt proiect, revocată, sau trunchiată."
            ))
            return
        self.stdout.write(self.style.SUCCESS("2. Google acceptă cheia: token obținut"))

        cu_token = ProfilStudent.objects.exclude(fcm_token__isnull=True).exclude(fcm_token="")
        numar = cu_token.count()
        self.stdout.write(f"3. Studenți cu notificări activate: {numar}")
        if not numar:
            self.stdout.write(
                "   Normal deocamdată: fiecare student apasă butonul de pe dashboard."
            )

        email = optiuni.get("trimite_catre")
        if not email:
            self.stdout.write(self.style.SUCCESS(
                "\nConfigurarea e completă. Pentru o notificare de test:\n"
                "  manage.py verifica_push --trimite-catre email@student.tuiasi.ro"
            ))
            return

        profil = ProfilStudent.objects.filter(email__iexact=email).first()
        if not profil:
            self.stdout.write(self.style.ERROR(f"Niciun student cu emailul {email}."))
            return
        if not profil.fcm_token:
            self.stdout.write(self.style.WARNING(
                f"{email} nu a activat încă notificările în browser."
            ))
            return

        jurnal = trimite_push(
            profil,
            "Test din Spălătorie",
            "Dacă vezi acest mesaj, notificările în browser funcționează.",
        )
        if jurnal and not jurnal.a_esuat:
            self.stdout.write(self.style.SUCCESS("4. Notificare de test trimisă."))
        else:
            detaliu = f"{jurnal.cod_eroare} {jurnal.detaliu}" if jurnal else "necunoscut"
            self.stdout.write(self.style.ERROR(f"4. Trimiterea a eșuat: {detaliu}"))
