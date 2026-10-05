"""
Teste pentru regulile de rezervare.

Timpul este înghețat (`timezone.now` este mock-uit) la luni, 2 martie 2026,
ora 09:00 în Europe/Bucharest (07:00 UTC). Astfel regulile care depind de
săptămâna curentă sunt deterministe, indiferent de ziua în care rulează
testele, iar comportamentul dependent de fus orar poate fi verificat.
"""

import base64
import json
import shutil
import tempfile
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from unittest.mock import patch

from allauth.socialaccount.models import SocialApp
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from booking.push import _cont_de_serviciu, notifica_student, trimite_push
from booking.utils import (
    destinatari_cerere_cont,
    notifica_admini_cerere,
    sefi_de_camin,
    trimite_whatsapp,
    valideaza_numar,
)
from booking.models import (
    AdminCamin,
    Camin,
    CerereCont,
    IntervalDezactivare,
    Masina,
    Notificare,
    NotificareLog,
    ProfilStudent,
    Rezervare,
)

# Luni, 2 martie 2026, 09:00 ora României (iarna → UTC+2)
LUNI = date(2026, 3, 2)
MARTI = LUNI + timedelta(days=1)
FAKE_NOW = datetime(2026, 3, 2, 7, 0, tzinfo=dt_timezone.utc)


# În producție cererile HTTP sunt redirectate către HTTPS. Clientul de test
# vorbește HTTP, deci fără asta fiecare cerere s-ar opri într-un 301.
@override_settings(SECURE_SSL_REDIRECT=False)
class BazaRezervari(TestCase):
    """Fixture comun: un cămin cu două mașini și doi studenți."""

    def setUp(self):
        patcher = patch("django.utils.timezone.now", return_value=FAKE_NOW)
        patcher.start()
        self.addCleanup(patcher.stop)

        # base.html afișează butonul de login Google, deci are nevoie de un SocialApp.
        app = SocialApp.objects.create(
            provider="google", name="Google", client_id="test", secret="test"
        )
        app.sites.add(Site.objects.get_current())

        self.camin = Camin.objects.create(nume="T1", durata_interval=2)
        self.alt_camin = Camin.objects.create(nume="T2", durata_interval=2)

        self.masina = Masina.objects.create(camin=self.camin, nume="Masina 1")
        self.masina2 = Masina.objects.create(camin=self.camin, nume="Masina 2")
        self.masina_inactiva = Masina.objects.create(
            camin=self.camin, nume="Masina stricata", activa=False
        )
        self.masina_alt_camin = Masina.objects.create(
            camin=self.alt_camin, nume="Masina T2"
        )

        self.student = self._student("ana@student.tuiasi.ro")
        self.alt_student = self._student("bogdan@student.tuiasi.ro")

    def _student(self, email, camin=None):
        user = User.objects.create_user(
            username=email, email=email, first_name="Test", last_name="Student"
        )
        ProfilStudent.objects.create(
            utilizator=user,
            camin=camin or self.camin,
            numar_camera="101",
            telefon="+40700000000",
        )
        return user

    def _rezerva(self, masina, data, ora, user=None, saptamana=0):
        self.client.force_login(user or self.student)
        return self.client.post(
            reverse("creeaza_rezervare"),
            {
                "masina_id": masina.id,
                "data": data.isoformat(),
                "ora_start": ora,
                "saptamana": saptamana,
            },
            follow=True,
        )

    def _mesaje(self, response):
        return [str(m) for m in response.context["messages"]]


class ValidareMasina(BazaRezervari):
    """Mașina cerută trebuie să aparțină căminului studentului și să fie activă."""

    def test_rezervare_valida_se_creeaza(self):
        self._rezerva(self.masina, LUNI, "10:00")

        rezervare = Rezervare.objects.get(utilizator=self.student)
        self.assertEqual(rezervare.masina, self.masina)
        self.assertEqual(rezervare.data_rezervare, LUNI)
        self.assertEqual(rezervare.ora_start, time(10, 0))
        # durata_interval = 2 ore
        self.assertEqual(rezervare.ora_end, time(12, 0))
        self.assertEqual(rezervare.nivel_prioritate, 1)

    def test_masina_din_alt_camin_este_respinsa(self):
        raspuns = self._rezerva(self.masina_alt_camin, LUNI, "10:00")

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertIn(
            "Mașina selectată nu există în căminul tău.", self._mesaje(raspuns)
        )

    def test_masina_dezactivata_este_respinsa(self):
        raspuns = self._rezerva(self.masina_inactiva, LUNI, "10:00")

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertIn("Mașina selectată este dezactivată.", self._mesaje(raspuns))

    def test_masina_inexistenta_este_respinsa(self):
        self.client.force_login(self.student)
        raspuns = self.client.post(
            reverse("creeaza_rezervare"),
            {"masina_id": 99999, "data": LUNI.isoformat(), "ora_start": "10:00"},
            follow=True,
        )

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertIn(
            "Mașina selectată nu există în căminul tău.", self._mesaje(raspuns)
        )


class OcupareInterval(BazaRezervari):
    """Un interval ocupat nu poate fi luat de altcineva cu prioritate egală."""

    def test_interval_ocupat_este_respins(self):
        Rezervare.objects.create(
            utilizator=self.alt_student,
            masina=self.masina,
            data_rezervare=LUNI,
            ora_start=time(10, 0),
            ora_end=time(12, 0),
            nivel_prioritate=1,
        )

        raspuns = self._rezerva(self.masina, LUNI, "10:00")

        self.assertEqual(Rezervare.objects.filter(utilizator=self.student).count(), 0)
        self.assertIn("Intervalul este deja ocupat.", self._mesaje(raspuns))

    def test_suprapunere_partiala_este_respinsa(self):
        """10:00-12:00 ocupat ⇒ 11:00-13:00 se suprapune și trebuie respins."""
        Rezervare.objects.create(
            utilizator=self.alt_student,
            masina=self.masina,
            data_rezervare=LUNI,
            ora_start=time(10, 0),
            ora_end=time(12, 0),
            nivel_prioritate=1,
        )

        raspuns = self._rezerva(self.masina, LUNI, "11:00")

        self.assertEqual(Rezervare.objects.filter(utilizator=self.student).count(), 0)
        self.assertIn("Intervalul este deja ocupat.", self._mesaje(raspuns))

    def test_interval_dezactivat_este_respins(self):
        IntervalDezactivare.objects.create(
            masina=self.masina,
            data=LUNI,
            ora_start=time(9, 0),
            ora_end=time(13, 0),
        )

        raspuns = self._rezerva(self.masina, LUNI, "10:00")

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertIn(
            "Mașina este dezactivată în intervalul selectat. Alege alt interval.",
            self._mesaje(raspuns),
        )

    @patch("booking.views.notifica_student")
    def test_preluare_rezervare_cu_prioritate_mai_mica(self, mock_notifica):
        """Un student fără rezervări preia slotul deținut cu prioritate 4."""
        ocupata = Rezervare.objects.create(
            utilizator=self.alt_student,
            masina=self.masina,
            data_rezervare=LUNI,
            ora_start=time(10, 0),
            ora_end=time(12, 0),
            nivel_prioritate=4,
        )

        self._rezerva(self.masina, LUNI, "10:00")

        ocupata.refresh_from_db()
        self.assertTrue(ocupata.anulata)
        self.assertTrue(
            Rezervare.objects.filter(
                utilizator=self.student,
                masina=self.masina,
                data_rezervare=LUNI,
                ora_start=time(10, 0),
                anulata=False,
            ).exists()
        )
        mock_notifica.assert_called_once()


class ConstrangereBazaDeDate(BazaRezervari):
    """Constrângerea din DB prinde dubla rezervare chiar dacă view-ul e ocolit."""

    def _creeaza(self, user, anulata=False):
        return Rezervare.objects.create(
            utilizator=user,
            masina=self.masina,
            data_rezervare=LUNI,
            ora_start=time(10, 0),
            ora_end=time(12, 0),
            anulata=anulata,
        )

    def test_doua_rezervari_active_pe_acelasi_slot_sunt_respinse(self):
        self._creeaza(self.student)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._creeaza(self.alt_student)

    def test_slotul_se_elibereaza_dupa_anulare(self):
        prima = self._creeaza(self.student)
        prima.anulata = True
        prima.save()

        a_doua = self._creeaza(self.alt_student)

        self.assertEqual(
            Rezervare.objects.filter(anulata=False, masina=self.masina).count(), 1
        )
        self.assertEqual(a_doua.utilizator, self.alt_student)

    def test_mai_multe_rezervari_anulate_pe_acelasi_slot_sunt_permise(self):
        self._creeaza(self.student, anulata=True)
        self._creeaza(self.alt_student, anulata=True)

        self.assertEqual(Rezervare.objects.filter(anulata=True).count(), 2)


class LimiteSaptamanale(BazaRezervari):
    """Regulile de cotă pe săptămână."""

    def test_maxim_patru_rezervari_in_saptamana_curenta(self):
        for masina, data, ora in [
            (self.masina, LUNI, "10:00"),
            (self.masina, LUNI, "12:00"),
            (self.masina, MARTI, "10:00"),
            (self.masina2, MARTI, "12:00"),
        ]:
            self._rezerva(masina, data, ora)
        self.assertEqual(Rezervare.objects.filter(utilizator=self.student).count(), 4)

        raspuns = self._rezerva(self.masina2, LUNI, "14:00")

        self.assertEqual(Rezervare.objects.filter(utilizator=self.student).count(), 4)
        self.assertIn(
            "Ai atins numărul maxim de rezervări pentru această săptămână.",
            self._mesaje(raspuns),
        )

    def test_a_doua_rezervare_din_saptamana_curenta_doar_azi_sau_maine(self):
        self._rezerva(self.masina, LUNI, "10:00")

        joi = LUNI + timedelta(days=3)
        raspuns = self._rezerva(self.masina, joi, "10:00")

        self.assertEqual(Rezervare.objects.filter(utilizator=self.student).count(), 1)
        self.assertIn(
            "În săptămâna curentă doar prima rezervare poate fi făcută oricând, "
            "restul doar pentru azi și mâine.",
            self._mesaje(raspuns),
        )

    def test_o_singura_rezervare_pe_saptamana_viitoare(self):
        saptamana_viitoare = LUNI + timedelta(days=7)
        self._rezerva(self.masina, saptamana_viitoare, "10:00")
        self.assertEqual(Rezervare.objects.filter(utilizator=self.student).count(), 1)

        raspuns = self._rezerva(self.masina, saptamana_viitoare + timedelta(days=1), "10:00")

        self.assertEqual(Rezervare.objects.filter(utilizator=self.student).count(), 1)
        self.assertIn(
            "Poți face doar o rezervare pe săptămână pentru săptămânile viitoare.",
            self._mesaje(raspuns),
        )

    def test_nu_se_poate_rezerva_cu_peste_patru_saptamani_in_avans(self):
        prea_departe = LUNI + timedelta(days=35)

        raspuns = self._rezerva(self.masina, prea_departe, "10:00")

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertIn(
            "Nu poți face rezervări cu mai mult de 4 săptămâni în avans.",
            self._mesaje(raspuns),
        )

    def test_nu_se_poate_rezerva_in_trecut(self):
        raspuns = self._rezerva(self.masina, LUNI - timedelta(days=1), "10:00")

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertIn(
            "Nu poți face rezervări pentru date din trecut.", self._mesaje(raspuns)
        )


class RestrictiiCont(BazaRezervari):
    """Suspendare și număr de telefon obligatoriu."""

    def test_student_suspendat_nu_poate_rezerva(self):
        profil = ProfilStudent.objects.get(utilizator=self.student)
        profil.suspendat_pana_la = LUNI + timedelta(days=5)
        profil.save()

        raspuns = self._rezerva(self.masina, LUNI, "10:00")

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertTrue(
            any("Contul tău este blocat" in m for m in self._mesaje(raspuns))
        )

    def test_suspendarea_expirata_nu_mai_blocheaza(self):
        profil = ProfilStudent.objects.get(utilizator=self.student)
        profil.suspendat_pana_la = LUNI - timedelta(days=1)
        profil.save()

        self._rezerva(self.masina, LUNI, "10:00")

        self.assertEqual(Rezervare.objects.count(), 1)

    def test_fara_telefon_ajunge_pe_dashboard_unde_e_formularul(self):
        """
        `adauga_telefon` accepta doar POST, deci un redirect acolo ar fi lasat
        studentul pe pagina de start, fara formular. Formularul de telefon este
        pe dashboard-ul studentului.
        """
        profil = ProfilStudent.objects.get(utilizator=self.student)
        profil.telefon = ""
        profil.save()

        raspuns = self._rezerva(self.masina, LUNI, "10:00")

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertEqual(raspuns.redirect_chain[0][0], reverse("dashboard_student"))
        self.assertContains(raspuns, "Completează numărul tău de telefon")
        self.assertTrue(
            any("număr de telefon" in m for m in self._mesaje(raspuns))
        )

    def test_utilizator_fara_rol_nu_poate_rezerva(self):
        strain = User.objects.create_user(
            username="strain@example.com", email="strain@example.com"
        )
        self.client.force_login(strain)

        self.client.post(
            reverse("creeaza_rezervare"),
            {"masina_id": self.masina.id, "data": LUNI.isoformat(), "ora_start": "10:00"},
        )

        self.assertEqual(Rezervare.objects.count(), 0)


class Anulare(BazaRezervari):
    """Anularea ține cont de ora locală, nu de ora UTC a serverului."""

    def _rezervare(self, ora_start, data=LUNI, user=None):
        return Rezervare.objects.create(
            utilizator=user or self.student,
            masina=self.masina,
            data_rezervare=data,
            ora_start=ora_start,
            ora_end=time((ora_start.hour + 2) % 24, 0),
            nivel_prioritate=1,
        )

    def _anuleaza(self, rezervare, user=None):
        self.client.force_login(user or self.student)
        return self.client.post(
            reverse("anuleaza_rezervare", args=[rezervare.id]), follow=True
        )

    def test_rezervare_viitoare_poate_fi_anulata(self):
        # ora locală înghețată: 09:00; rezervarea începe la 14:00
        rezervare = self._rezervare(time(14, 0))

        self._anuleaza(rezervare)

        rezervare.refresh_from_db()
        self.assertTrue(rezervare.anulata)

    def test_rezervare_deja_inceputa_nu_poate_fi_anulata(self):
        # ora locală înghețată: 09:00; rezervarea a început la 08:00
        rezervare = self._rezervare(time(8, 0))

        raspuns = self._anuleaza(rezervare)

        rezervare.refresh_from_db()
        self.assertFalse(rezervare.anulata)
        self.assertIn(
            "Rezervarea a început deja și nu mai poate fi anulată.",
            self._mesaje(raspuns),
        )

    def test_ora_locala_nu_ora_utc_decide_anularea(self):
        """
        La 21:30 UTC este deja 23:30 în România, deci o rezervare de la 23:00
        a început. Cu ora UTC (20:30 < 23:00) ar părea că încă nu a început.
        """
        patcher = patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 3, 2, 21, 30, tzinfo=dt_timezone.utc),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        rezervare = self._rezervare(time(23, 0))
        self._anuleaza(rezervare)

        rezervare.refresh_from_db()
        self.assertFalse(rezervare.anulata)

    def test_data_locala_nu_data_utc_decide_ce_e_in_trecut(self):
        """
        La 22:30 UTC pe 2 martie este deja 3 martie, 00:30, în România.
        O rezervare pe 3 martie ora 08:00 este în viitor și poate fi anulată.
        """
        patcher = patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 3, 2, 22, 30, tzinfo=dt_timezone.utc),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        rezervare = self._rezervare(time(8, 0), data=date(2026, 3, 3))
        self._anuleaza(rezervare)

        rezervare.refresh_from_db()
        self.assertTrue(rezervare.anulata)

    def test_nu_poti_anula_rezervarea_altui_student(self):
        rezervare = self._rezervare(time(14, 0), user=self.alt_student)

        self._anuleaza(rezervare, user=self.student)

        rezervare.refresh_from_db()
        self.assertFalse(rezervare.anulata)

    def test_anularea_necesita_post(self):
        rezervare = self._rezervare(time(14, 0))
        self.client.force_login(self.student)

        raspuns = self.client.get(reverse("anuleaza_rezervare", args=[rezervare.id]))

        self.assertEqual(raspuns.status_code, 405)
        rezervare.refresh_from_db()
        self.assertFalse(rezervare.anulata)


class IzolareIntreCamine(BazaRezervari):
    """Un student vede și poate rezerva doar în căminul lui."""

    def test_student_din_alt_camin_nu_poate_rezerva_aici(self):
        strain = self._student("carmen@student.tuiasi.ro", camin=self.alt_camin)

        raspuns = self._rezerva(self.masina, LUNI, "10:00", user=strain)

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertIn(
            "Mașina selectată nu există în căminul tău.", self._mesaje(raspuns)
        )

    def test_student_fara_camin_primeste_mesaj_clar(self):
        profil = ProfilStudent.objects.get(utilizator=self.student)
        profil.camin = None
        profil.save()

        raspuns = self._rezerva(self.masina, LUNI, "10:00")

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertIn(
            "Nu ai un cămin asociat. Contactează administratorul.",
            self._mesaje(raspuns),
        )


class SlotPesteMiezulNoptii(BazaRezervari):
    """
    Programul real e 07:00 → 01:00, deci ultimul slot al zilei se termină după
    miezul nopții (22:00 → 01:00 la un interval de 3 ore). Comparațiile de
    suprapunere trebuie să trateze corect cazul ora_end < ora_start.
    """

    def setUp(self):
        super().setUp()
        self.camin.durata_interval = 3
        self.camin.save()

    def test_slotul_de_noapte_se_salveaza_cu_ora_end_dupa_miezul_noptii(self):
        self._rezerva(self.masina, LUNI, "22:00")

        rezervare = Rezervare.objects.get(utilizator=self.student)
        self.assertEqual(rezervare.ora_start, time(22, 0))
        self.assertEqual(rezervare.ora_end, time(1, 0))

    def test_slotul_de_noapte_nu_poate_fi_rezervat_de_doua_ori(self):
        Rezervare.objects.create(
            utilizator=self.alt_student,
            masina=self.masina,
            data_rezervare=LUNI,
            ora_start=time(22, 0),
            ora_end=time(1, 0),
            nivel_prioritate=1,
        )

        raspuns = self._rezerva(self.masina, LUNI, "22:00")

        self.assertEqual(Rezervare.objects.filter(utilizator=self.student).count(), 0)
        self.assertIn("Intervalul este deja ocupat.", self._mesaje(raspuns))

    def test_slotul_de_noapte_se_suprapune_cu_o_cerere_mai_tarzie(self):
        """22:00-01:00 ocupat ⇒ o cerere de la 23:00 se suprapune."""
        Rezervare.objects.create(
            utilizator=self.alt_student,
            masina=self.masina,
            data_rezervare=LUNI,
            ora_start=time(22, 0),
            ora_end=time(1, 0),
            nivel_prioritate=1,
        )

        raspuns = self._rezerva(self.masina, LUNI, "23:00")

        self.assertEqual(Rezervare.objects.filter(utilizator=self.student).count(), 0)
        self.assertIn("Intervalul este deja ocupat.", self._mesaje(raspuns))

    def test_slotul_de_noapte_respecta_masina_dezactivata(self):
        IntervalDezactivare.objects.create(
            masina=self.masina,
            data=LUNI,
            ora_start=time(21, 0),
            ora_end=time(23, 0),
        )

        raspuns = self._rezerva(self.masina, LUNI, "22:00")

        self.assertEqual(Rezervare.objects.count(), 0)
        self.assertIn(
            "Mașina este dezactivată în intervalul selectat. Alege alt interval.",
            self._mesaje(raspuns),
        )

    def test_slotul_de_dimineata_ramane_liber(self):
        """Slotul de noapte nu trebuie să blocheze restul zilei."""
        Rezervare.objects.create(
            utilizator=self.alt_student,
            masina=self.masina,
            data_rezervare=LUNI,
            ora_start=time(22, 0),
            ora_end=time(1, 0),
            nivel_prioritate=1,
        )

        self._rezerva(self.masina, LUNI, "07:00")

        self.assertEqual(Rezervare.objects.filter(utilizator=self.student).count(), 1)


@override_settings(SECURE_SSL_REDIRECT=False)
class AutentificareAPI(TestCase):
    """API-ul TAD si dashboard-ul lui nu mai sunt accesibile fara cont."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="api@student.tuiasi.ro", email="api@student.tuiasi.ro"
        )

    def test_citirile_cer_autentificare(self):
        for cale in [
            "/api/",
            "/api/masini/",
            "/api/camine/",
            "/api/masini-camin/?camin_id=1",
            "/api/statistici/avansate/",
        ]:
            with self.subTest(cale=cale):
                raspuns = self.client.get(cale)
                self.assertEqual(raspuns.status_code, 401)
                self.assertIn("Autentificare", raspuns.json()["error"])

    def test_scrierile_cer_autentificare(self):
        raspuns = self.client.post(
            "/api/masini/",
            data=json.dumps({"nume": "Masina intrusului"}),
            content_type="application/json",
        )

        self.assertEqual(raspuns.status_code, 401)
        self.assertFalse(Masina.objects.filter(nume="Masina intrusului").exists())

    def test_stergerea_in_masa_cere_autentificare(self):
        raspuns = self.client.delete("/api/masini/")

        self.assertEqual(raspuns.status_code, 401)

    def test_utilizatorul_logat_are_acces(self):
        self.client.force_login(self.user)

        raspuns = self.client.get("/api/masini/")

        self.assertEqual(raspuns.status_code, 200)

    def test_dashboardul_api_cere_autentificare(self):
        raspuns = self.client.get(reverse("api_dashboard"))

        self.assertEqual(raspuns.status_code, 302)
        self.assertIn("login", raspuns.url)


@override_settings(SECURE_SSL_REDIRECT=False)
class Deconectare(TestCase):
    """
    Logout-ul trebuie sa duca pe pagina de autentificare, nu inapoi in fluxul
    Google: `/accounts/login/` e deturnat catre Google, care re-autentifica
    tacut utilizatorul si anuleaza efectul deconectarii.
    """

    def setUp(self):
        app = SocialApp.objects.create(
            provider="google", name="Google", client_id="test", secret="test"
        )
        app.sites.add(Site.objects.get_current())

        self.user = User.objects.create_user(
            username="ana@student.tuiasi.ro", email="ana@student.tuiasi.ro"
        )
        ProfilStudent.objects.create(utilizator=self.user, numar_camera="101")

    def test_logout_duce_pe_pagina_de_autentificare(self):
        self.client.force_login(self.user)

        raspuns = self.client.get(reverse("custom_logout"), follow=True)

        self.assertRedirects(raspuns, reverse("home"))
        self.assertContains(raspuns, "Conectează-te")

    def test_logout_nu_trimite_inapoi_la_google(self):
        self.client.force_login(self.user)

        raspuns = self.client.get(reverse("custom_logout"))

        self.assertNotIn("accounts/login", raspuns.url)
        self.assertNotIn("google", raspuns.url)

    def test_sesiunea_chiar_se_inchide(self):
        self.client.force_login(self.user)
        self.client.get(reverse("custom_logout"))

        raspuns = self.client.get(reverse("dashboard_student"))

        self.assertEqual(raspuns.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_google_cere_alegerea_contului(self):
        """
        Pe calculatoarele comune din camin, Google trebuie sa intrebe cu ce cont
        se intra, altfel urmatorul utilizator ajunge in contul precedentului.
        """
        raspuns = self.client.get("/accounts/google/login/?process=login")

        self.assertEqual(raspuns.status_code, 302)
        self.assertIn("prompt=select_account", raspuns.url)


def _fisier_excel(randuri):
    """Construiește un .xlsx în memorie, ca cel încărcat de administrator."""
    import io

    import pandas as pd
    from django.core.files.uploadedfile import SimpleUploadedFile

    df = pd.DataFrame(randuri, columns=["email", "nume", "prenume", "camin", "camera"])
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return SimpleUploadedFile(
        "lista.xlsx",
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# Fișierele încărcate în teste nu au ce căuta în directorul proiectului.
_MEDIA_TESTE = tempfile.mkdtemp(prefix="washtuiasi-teste-")


@override_settings(MEDIA_ROOT=_MEDIA_TESTE)
class BazaImport(TestCase):
    """Fixture comun pentru importul de studenți."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA_TESTE, ignore_errors=True)

    def setUp(self):
        app = SocialApp.objects.create(
            provider="google", name="Google", client_id="test", secret="test"
        )
        app.sites.add(Site.objects.get_current())

        self.t1 = Camin.objects.create(nume="T1", durata_interval=2)
        self.t2 = Camin.objects.create(nume="T2", durata_interval=2)

        self.admin_user = User.objects.create_user(
            username="admin@tuiasi.ro", email="admin@tuiasi.ro"
        )
        AdminCamin.objects.create(email="admin@tuiasi.ro", is_super_admin=True)

    def _student(self, email, camin, camera="101", activ=True, username=None):
        user = User.objects.create_user(
            username=username or email, email=email,
            first_name="Vechi", last_name="Nume",
        )
        return ProfilStudent.objects.create(
            utilizator=user, camin=camin, numar_camera=camera, activ=activ
        )

    def _incarca(self, randuri):
        self.client.force_login(self.admin_user)
        return self.client.post(
            reverse("incarca_studenti"), {"fisier": _fisier_excel(randuri)}, follow=True
        )

    def _confirma(self, dezactiveaza=False):
        date = {"actiune": "confirma"}
        if dezactiveaza:
            date["dezactiveaza"] = "on"
        return self.client.post(reverse("incarca_studenti"), date, follow=True)


@override_settings(SECURE_SSL_REDIRECT=False)
class PlanificareImport(BazaImport):
    """Planul se calculează fără să atingă baza de date."""

    def test_previzualizarea_nu_scrie_nimic(self):
        raspuns = self._incarca([["ana@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])

        self.assertEqual(ProfilStudent.objects.count(), 0)
        plan = raspuns.context["plan"]
        self.assertEqual(len(plan.de_creat), 1)

    def test_confirmarea_creeaza_studentii(self):
        self._incarca([["ana@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])
        self._confirma()

        profil = ProfilStudent.objects.get(email="ana@student.tuiasi.ro")
        self.assertEqual(profil.camin, self.t1)
        self.assertEqual(profil.numar_camera, "203")
        self.assertEqual(profil.nume, "Pop")
        self.assertTrue(profil.activ)

    def test_studentul_existent_este_actualizat_nu_duplicat(self):
        self._student("ana@student.tuiasi.ro", self.t1, camera="101")

        raspuns = self._incarca([["ana@student.tuiasi.ro", "Pop", "Ana", "T2", "305"]])
        plan = raspuns.context["plan"]
        self.assertEqual(len(plan.de_creat), 0)
        self.assertEqual(len(plan.de_actualizat), 1)

        self._confirma()

        self.assertEqual(ProfilStudent.objects.count(), 1)
        profil = ProfilStudent.objects.get()
        self.assertEqual(profil.camin, self.t2)
        self.assertEqual(profil.numar_camera, "305")

    def test_contul_creat_la_login_nu_este_duplicat(self):
        """
        Conturile create la autentificare au username-ul fără domeniu. Căutarea
        după username ar crea un al doilea cont pentru același om.
        """
        self._student("ana@student.tuiasi.ro", self.t1, username="ana")

        self._incarca([["ana@student.tuiasi.ro", "Pop", "Ana", "T1", "305"]])
        self._confirma()

        self.assertEqual(User.objects.filter(email="ana@student.tuiasi.ro").count(), 1)
        self.assertEqual(ProfilStudent.objects.count(), 1)

    def test_contul_fara_profil_este_refolosit(self):
        """
        Cazul real din producție: cineva s-a autentificat, a fost respins,
        și a rămas un cont cu username fără domeniu și fără ProfilStudent.
        O căutare după username nu-l găsește și creează un al doilea cont
        cu același email.
        """
        User.objects.create_user(username="ana", email="ana@student.tuiasi.ro")

        self._incarca([["ana@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])
        self._confirma()

        self.assertEqual(User.objects.filter(email="ana@student.tuiasi.ro").count(), 1)
        self.assertEqual(ProfilStudent.objects.count(), 1)
        self.assertEqual(
            ProfilStudent.objects.get().utilizator.username, "ana"
        )

    def test_randurile_invalide_sunt_raportate_si_sarite(self):
        raspuns = self._incarca([
            ["ana@student.tuiasi.ro", "Pop", "Ana", "T1", "203"],
            ["", "Ionescu", "Dan", "T1", "204"],
            ["fara-adresa", "Marin", "Ioana", "T1", "205"],
            ["ana@student.tuiasi.ro", "Pop", "Ana", "T1", "206"],
        ])

        plan = raspuns.context["plan"]
        self.assertEqual(len(plan.de_creat), 1)
        self.assertEqual(len(plan.erori), 3)

    def test_domeniul_fara_punct_este_semnalat(self):
        raspuns = self._incarca([["ana@student", "Pop", "Ana", "T1", "203"]])

        plan = raspuns.context["plan"]
        self.assertEqual(len(plan.avertismente), 1)
        self.assertIn("student", plan.avertismente[0][1])


@override_settings(SECURE_SSL_REDIRECT=False)
class DezactivareLaImport(BazaImport):
    """Studenții care nu mai apar în liste sunt dezactivați, niciodată șterși."""

    def test_fara_bifa_nu_se_dezactiveaza_nimeni(self):
        plecat = self._student("plecat@student.tuiasi.ro", self.t1)

        self._incarca([["nou@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])
        self._confirma(dezactiveaza=False)

        plecat.refresh_from_db()
        self.assertTrue(plecat.activ)

    def test_cu_bifa_cei_lipsa_sunt_dezactivati(self):
        plecat = self._student("plecat@student.tuiasi.ro", self.t1)
        ramas = self._student("ramas@student.tuiasi.ro", self.t1)

        self._incarca([["ramas@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])
        self._confirma(dezactiveaza=True)

        plecat.refresh_from_db()
        ramas.refresh_from_db()
        self.assertFalse(plecat.activ)
        self.assertTrue(ramas.activ)

    def test_dezactivarea_nu_atinge_alte_camine(self):
        alt_camin = self._student("altul@student.tuiasi.ro", self.t2)

        self._incarca([["ana@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])
        self._confirma(dezactiveaza=True)

        alt_camin.refresh_from_db()
        self.assertTrue(alt_camin.activ)

    def test_dezactivarea_nu_sterge_nimic(self):
        plecat = self._student("plecat@student.tuiasi.ro", self.t1)
        masina = Masina.objects.create(camin=self.t1, nume="Masina 1")
        Rezervare.objects.create(
            utilizator=plecat.utilizator, masina=masina,
            data_rezervare=LUNI, ora_start=time(10, 0), ora_end=time(12, 0),
        )

        self._incarca([["ana@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])
        self._confirma(dezactiveaza=True)

        self.assertTrue(User.objects.filter(id=plecat.utilizator_id).exists())
        self.assertEqual(Rezervare.objects.count(), 1)

    def test_studentul_reaparut_este_reactivat(self):
        intors = self._student("intors@student.tuiasi.ro", self.t1, activ=False)

        raspuns = self._incarca([["intors@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])
        self.assertEqual(len(raspuns.context["plan"].de_reactivat), 1)

        self._confirma()

        intors.refresh_from_db()
        self.assertTrue(intors.activ)


@override_settings(SECURE_SSL_REDIRECT=False)
class AccesStudentInactiv(BazaImport):
    """Un student dezactivat nu mai intră în aplicație, dar nu pierde nimic."""

    def setUp(self):
        super().setUp()
        self.profil = self._student("ana@student.tuiasi.ro", self.t1, activ=False)
        self.masina = Masina.objects.create(camin=self.t1, nume="Masina 1")

    def test_nu_ajunge_pe_dashboard(self):
        self.client.force_login(self.profil.utilizator)

        raspuns = self.client.get(reverse("dashboard_student"))

        self.assertContains(raspuns, "nu mai este activ")

    def test_nu_poate_rezerva(self):
        self.client.force_login(self.profil.utilizator)

        self.client.post(reverse("creeaza_rezervare"), {
            "masina_id": self.masina.id,
            "data": LUNI.isoformat(),
            "ora_start": "10:00",
        })

        self.assertEqual(Rezervare.objects.count(), 0)

    def test_callbackul_il_opreste_fara_sa_stearga_contul(self):
        self.client.force_login(self.profil.utilizator)

        raspuns = self.client.get(reverse("callback"))

        self.assertContains(raspuns, "nu mai este activ")
        self.assertTrue(User.objects.filter(id=self.profil.utilizator_id).exists())
        self.assertTrue(ProfilStudent.objects.filter(id=self.profil.id).exists())

    def test_adminul_il_poate_reactiva_dintr_un_clic(self):
        self.client.force_login(self.admin_user)

        self.client.post(reverse("comuta_activ_student", args=[self.profil.id]))

        self.profil.refresh_from_db()
        self.assertTrue(self.profil.activ)


@override_settings(SECURE_SSL_REDIRECT=False)
class AccesLaImport(BazaImport):
    """Pagina de import nu e pentru oricine."""

    def test_anonimul_este_trimis_la_autentificare(self):
        raspuns = self.client.get(reverse("incarca_studenti"))

        self.assertEqual(raspuns.status_code, 302)
        self.assertIn("login", raspuns.url)

    def test_studentul_nu_are_acces(self):
        profil = self._student("ana@student.tuiasi.ro", self.t1)
        self.client.force_login(profil.utilizator)

        raspuns = self.client.get(reverse("incarca_studenti"))

        self.assertContains(raspuns, "administratorilor")
        self.assertEqual(raspuns.status_code, 200)

    def test_studentul_nu_poate_dezactiva_pe_altcineva(self):
        tinta = self._student("victima@student.tuiasi.ro", self.t1)
        atacator = self._student("ana@student.tuiasi.ro", self.t1)
        self.client.force_login(atacator.utilizator)

        self.client.post(reverse("comuta_activ_student", args=[tinta.id]))

        tinta.refresh_from_db()
        self.assertTrue(tinta.activ)

    def test_renuntarea_nu_schimba_nimic(self):
        self._student("plecat@student.tuiasi.ro", self.t1)
        self.client.force_login(self.admin_user)
        self._incarca([["ana@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])

        self.client.post(
            reverse("incarca_studenti"), {"actiune": "anuleaza"}, follow=True
        )

        self.assertFalse(ProfilStudent.objects.filter(email="ana@student.tuiasi.ro").exists())
        self.assertEqual(ProfilStudent.objects.count(), 1)

    def test_confirmarea_fara_fisier_incarcat_nu_face_nimic(self):
        self.client.force_login(self.admin_user)

        raspuns = self.client.post(
            reverse("incarca_studenti"), {"actiune": "confirma"}, follow=True
        )

        self.assertEqual(ProfilStudent.objects.count(), 0)
        self.assertTrue(
            any("nu mai este disponibil" in m for m in
                [str(x) for x in raspuns.context["messages"]])
        )


class ValidareNumar(TestCase):
    """
    Regula generala E.164 accepta 9-15 cifre, deci lasa sa treaca si un numar
    romanesc caruia ii lipseste o cifra. Acela nu primeste niciodata mesaje.
    """

    def test_numar_romanesc_corect(self):
        valid, _ = valideaza_numar("+40712345678")
        self.assertTrue(valid)

    def test_numar_romanesc_cu_o_cifra_lipsa(self):
        valid, mesaj = valideaza_numar("+4071234567")
        self.assertFalse(valid)
        self.assertIn("9 cifre", mesaj)

    def test_numar_romanesc_cu_o_cifra_in_plus(self):
        valid, _ = valideaza_numar("+407123456789")
        self.assertFalse(valid)

    def test_numar_moldovenesc(self):
        self.assertTrue(valideaza_numar("+37360123456")[0])
        self.assertFalse(valideaza_numar("+3736012345")[0])

    def test_fara_prefix_international(self):
        self.assertFalse(valideaza_numar("0712345678")[0])

    def test_alt_prefix_de_tara_ramane_permisiv(self):
        self.assertTrue(valideaza_numar("+441632960961")[0])


@override_settings(SECURE_SSL_REDIRECT=False)
class FormularTelefon(BazaRezervari):
    """Numerele scurte nu mai ajung în baza de date."""

    def test_numarul_scurt_este_respins(self):
        profil = ProfilStudent.objects.get(utilizator=self.student)
        profil.telefon = ""
        profil.save()
        self.client.force_login(self.student)

        raspuns = self.client.post(
            reverse("adauga_telefon"), {"telefon": "071234567", "tara": "ro"}, follow=True
        )

        profil.refresh_from_db()
        self.assertEqual(profil.telefon, "")
        self.assertTrue(any("9 cifre" in m for m in self._mesaje(raspuns)))


@override_settings(
    SECURE_SSL_REDIRECT=False,
    WHATSAPP_TEMPLATES={"rezervare_preluata_student": "HXtest"},
)
class JurnalNotificari(BazaRezervari):
    """Fiecare încercare de notificare lasă o urmă."""

    def setUp(self):
        super().setUp()
        self.profil = ProfilStudent.objects.get(utilizator=self.student)

    @patch("booking.utils.Client")
    def test_trimiterea_reusita_este_inregistrata(self, MockClient):
        mesaj = MockClient.return_value.messages.create.return_value
        mesaj.sid = "SM123"
        mesaj.status = "queued"

        jurnal = trimite_whatsapp(
            "+40712345678", "rezervare_preluata_student", {"1": "x"}, profil=self.profil
        )

        self.assertEqual(jurnal.message_sid, "SM123")
        self.assertEqual(jurnal.stare, "queued")
        self.assertEqual(jurnal.profil, self.profil)
        self.assertFalse(jurnal.a_esuat)

    @patch("booking.utils.Client")
    def test_eroarea_twilio_este_inregistrata_fara_sa_arunce(self, MockClient):
        MockClient.return_value.messages.create.side_effect = RuntimeError("retea picata")

        jurnal = trimite_whatsapp(
            "+40712345678", "rezervare_preluata_student", {"1": "x"}, profil=self.profil
        )

        self.assertEqual(jurnal.stare, NotificareLog.EROARE_TRIMITERE)
        self.assertIn("retea picata", jurnal.detaliu)
        self.assertTrue(jurnal.a_esuat)

    @patch("booking.utils.Client")
    def test_se_cere_raportarea_starii_finale(self, MockClient):
        MockClient.return_value.messages.create.return_value.sid = "SM1"
        MockClient.return_value.messages.create.return_value.status = "queued"

        trimite_whatsapp("+40712345678", "rezervare_preluata_student", {"1": "x"})

        argumente = MockClient.return_value.messages.create.call_args.kwargs
        self.assertIn("status_callback", argumente)
        self.assertIn("/twilio/status/", argumente["status_callback"])


@override_settings(SECURE_SSL_REDIRECT=False, TWILIO_AUTH_TOKEN="token-de-test")
class WebhookTwilio(TestCase):
    """Starea finală vine de la Twilio, iar cererea e verificată cu semnătura."""

    def setUp(self):
        self.jurnal = NotificareLog.objects.create(
            destinatar="+40712345678", sablon="rezervare_preluata_student",
            message_sid="SM999", stare="queued",
        )
        self.url = reverse("twilio_status")

    def _trimite(self, date, semnatura=None):
        from twilio.request_validator import RequestValidator

        adresa = "http://testserver" + self.url
        if semnatura is None:
            semnatura = RequestValidator("token-de-test").compute_signature(adresa, date)
        return self.client.post(self.url, date, HTTP_X_TWILIO_SIGNATURE=semnatura)

    def test_starea_livrata_este_scrisa(self):
        raspuns = self._trimite({"MessageSid": "SM999", "MessageStatus": "delivered"})

        self.assertEqual(raspuns.status_code, 204)
        self.jurnal.refresh_from_db()
        self.assertEqual(self.jurnal.stare, "delivered")
        self.assertFalse(self.jurnal.a_esuat)

    def test_esecul_este_scris_cu_tot_cu_cod(self):
        self._trimite({
            "MessageSid": "SM999", "MessageStatus": "undelivered",
            "ErrorCode": "63024", "ErrorMessage": "Invalid message recipient",
        })

        self.jurnal.refresh_from_db()
        self.assertEqual(self.jurnal.cod_eroare, "63024")
        self.assertTrue(self.jurnal.a_esuat)
        self.assertIn("WhatsApp", self.jurnal.explicatie())

    def test_cererea_fara_semnatura_valida_este_respinsa(self):
        raspuns = self._trimite(
            {"MessageSid": "SM999", "MessageStatus": "delivered"}, semnatura="inventata"
        )

        self.assertEqual(raspuns.status_code, 403)
        self.jurnal.refresh_from_db()
        self.assertEqual(self.jurnal.stare, "queued")

    def test_sid_necunoscut_nu_produce_eroare(self):
        raspuns = self._trimite({"MessageSid": "SM-inexistent", "MessageStatus": "delivered"})

        self.assertEqual(raspuns.status_code, 204)

    def test_doar_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


@override_settings(SECURE_SSL_REDIRECT=False)
class AvertismentPeDashboard(BazaRezervari):
    """Studentul află de pe dashboard că mesajele nu ajung la el."""

    def setUp(self):
        super().setUp()
        self.profil = ProfilStudent.objects.get(utilizator=self.student)
        self.client.force_login(self.student)

    def test_esecul_este_aratat_studentului(self):
        NotificareLog.objects.create(
            profil=self.profil, destinatar=self.profil.telefon,
            sablon="rezervare_preluata_student", stare="undelivered", cod_eroare="63024",
        )

        raspuns = self.client.get(reverse("dashboard_student"))

        self.assertContains(raspuns, "Ultimul mesaj nu a ajuns la tine")
        self.assertContains(raspuns, "WhatsApp instalat")

    def test_fara_esec_nu_se_arata_nimic(self):
        NotificareLog.objects.create(
            profil=self.profil, destinatar=self.profil.telefon,
            sablon="rezervare_preluata_student", stare="delivered",
        )

        raspuns = self.client.get(reverse("dashboard_student"))

        self.assertNotContains(raspuns, "Ultimul mesaj nu a ajuns la tine")

    def test_conteaza_doar_ultima_notificare(self):
        NotificareLog.objects.create(
            profil=self.profil, destinatar=self.profil.telefon,
            sablon="rezervare_preluata_student", stare="failed", cod_eroare="63024",
        )
        NotificareLog.objects.create(
            profil=self.profil, destinatar=self.profil.telefon,
            sablon="rezervare_preluata_student", stare="delivered",
        )

        raspuns = self.client.get(reverse("dashboard_student"))

        self.assertNotContains(raspuns, "Ultimul mesaj nu a ajuns la tine")


@override_settings(SECURE_SSL_REDIRECT=False)
class NotificariPush(BazaRezervari):
    """Push-ul completează WhatsApp-ul și se înregistrează la fel."""

    CONT = json.dumps({
        "project_id": "washtuiasi-push",
        "client_email": "x@y.z",
        "private_key": "cheie-de-test",
    })

    def setUp(self):
        super().setUp()
        self.profil = ProfilStudent.objects.get(utilizator=self.student)
        self.profil.fcm_token = "token-de-test"
        self.profil.save()

    def test_fara_token_nu_se_trimite_nimic(self):
        self.profil.fcm_token = None
        self.profil.save()

        self.assertIsNone(trimite_push(self.profil, "Titlu", "Corp"))
        self.assertEqual(NotificareLog.objects.count(), 0)

    @override_settings(FIREBASE_SERVICE_ACCOUNT=None)
    def test_fara_cheie_de_serviciu_push_ul_e_oprit(self):
        self.assertIsNone(trimite_push(self.profil, "Titlu", "Corp"))
        self.assertEqual(NotificareLog.objects.count(), 0)

    @patch("booking.push._token_acces", return_value="jeton")
    @patch("booking.push.requests.post")
    def test_trimiterea_reusita_este_inregistrata(self, mock_post, _):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"name": "projects/x/messages/1"}

        with override_settings(FIREBASE_SERVICE_ACCOUNT=self.CONT):
            jurnal = trimite_push(self.profil, "Titlu", "Corp")

        self.assertEqual(jurnal.canal, NotificareLog.PUSH)
        self.assertEqual(jurnal.stare, "delivered")
        self.assertFalse(jurnal.a_esuat)

    @patch("booking.push._token_acces", return_value="jeton")
    @patch("booking.push.requests.post")
    def test_esecul_este_inregistrat_cu_cod(self, mock_post, _):
        mock_post.return_value.status_code = 400
        mock_post.return_value.content = b"{}"
        mock_post.return_value.json.return_value = {
            "error": {"status": "INVALID_ARGUMENT", "message": "token stricat"}
        }

        with override_settings(FIREBASE_SERVICE_ACCOUNT=self.CONT):
            jurnal = trimite_push(self.profil, "Titlu", "Corp")

        self.assertTrue(jurnal.a_esuat)
        self.assertEqual(jurnal.cod_eroare, "INVALID_ARGUMENT")

    @patch("booking.push._token_acces", return_value="jeton")
    @patch("booking.push.requests.post")
    def test_tokenul_invalid_este_sters(self, mock_post, _):
        """Altfel am reîncerca la infinit către un browser care nu mai există."""
        mock_post.return_value.status_code = 404
        mock_post.return_value.content = b"{}"
        mock_post.return_value.json.return_value = {"error": {"status": "UNREGISTERED"}}

        with override_settings(FIREBASE_SERVICE_ACCOUNT=self.CONT):
            trimite_push(self.profil, "Titlu", "Corp")

        self.profil.refresh_from_db()
        self.assertIsNone(self.profil.fcm_token)

    @patch("booking.push._token_acces", return_value="jeton")
    @patch("booking.push.requests.post")
    @patch("booking.utils.Client")
    def test_ambele_canale_sunt_folosite(self, MockTwilio, mock_post, _):
        MockTwilio.return_value.messages.create.return_value.sid = "SM1"
        MockTwilio.return_value.messages.create.return_value.status = "queued"
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"name": "m/1"}

        with override_settings(
            FIREBASE_SERVICE_ACCOUNT=self.CONT,
            WHATSAPP_TEMPLATES={"rezervare_preluata_student": "HXtest"},
        ):
            rezultat = notifica_student(
                self.profil, "rezervare_preluata_student", {"1": "x"}, "Titlu", "Corp"
            )

        self.assertIsNotNone(rezultat["whatsapp"])
        self.assertIsNotNone(rezultat["push"])
        canale = set(NotificareLog.objects.values_list("canal", flat=True))
        self.assertEqual(canale, {NotificareLog.WHATSAPP, NotificareLog.PUSH})

    @patch("booking.push.trimite_push", side_effect=RuntimeError("push picat"))
    @patch("booking.utils.Client")
    def test_un_canal_picat_nu_il_opreste_pe_celalalt(self, MockTwilio, _):
        MockTwilio.return_value.messages.create.return_value.sid = "SM1"
        MockTwilio.return_value.messages.create.return_value.status = "queued"

        with override_settings(WHATSAPP_TEMPLATES={"rezervare_preluata_student": "HXtest"}):
            rezultat = notifica_student(
                self.profil, "rezervare_preluata_student", {"1": "x"}, "Titlu", "Corp"
            )

        self.assertIsNotNone(rezultat["whatsapp"])
        self.assertIsNone(rezultat["push"])


@override_settings(SECURE_SSL_REDIRECT=False)
class SalvareTokenPush(BazaRezervari):
    """Endpoint-ul de salvare a token-ului cere cont și metoda POST."""

    def test_anonimul_nu_poate_salva(self):
        raspuns = self.client.post(
            reverse("save_fcm_token"), data=json.dumps({"token": "t"}),
            content_type="application/json",
        )

        self.assertEqual(raspuns.status_code, 302)

    def test_get_nu_este_permis(self):
        self.client.force_login(self.student)

        self.assertEqual(self.client.get(reverse("save_fcm_token")).status_code, 405)

    def test_tokenul_se_salveaza(self):
        self.client.force_login(self.student)

        raspuns = self.client.post(
            reverse("save_fcm_token"), data=json.dumps({"token": "abc123"}),
            content_type="application/json",
        )

        self.assertEqual(raspuns.status_code, 200)
        profil = ProfilStudent.objects.get(utilizator=self.student)
        self.assertEqual(profil.fcm_token, "abc123")

    def test_tokenul_gol_este_respins(self):
        self.client.force_login(self.student)

        raspuns = self.client.post(
            reverse("save_fcm_token"), data=json.dumps({"token": "  "}),
            content_type="application/json",
        )

        self.assertEqual(raspuns.status_code, 400)


@override_settings(SECURE_SSL_REDIRECT=False)
class ButonActivarePush(BazaRezervari):
    """
    Butonul de activare apare doar cand serverul chiar poate trimite push:
    altfel studentul ar acorda permisiunea degeaba.
    """

    CONT = json.dumps({
        "project_id": "washtuiasi-push",
        "client_email": "x@y.z",
        "private_key": "cheie-de-test",
    })

    def setUp(self):
        super().setUp()
        self.profil = ProfilStudent.objects.get(utilizator=self.student)
        self.profil.fcm_token = None
        self.profil.save()
        self.client.force_login(self.student)

    @override_settings(FIREBASE_SERVICE_ACCOUNT=None)
    def test_lipseste_cat_timp_push_ul_nu_e_configurat(self):
        raspuns = self.client.get(reverse("dashboard_student"))

        self.assertNotContains(raspuns, "Primește notificările și în browser")

    def test_apare_cand_push_ul_e_configurat(self):
        with override_settings(FIREBASE_SERVICE_ACCOUNT=self.CONT):
            raspuns = self.client.get(reverse("dashboard_student"))

        self.assertContains(raspuns, "Primește notificările și în browser")

    def test_nu_apare_daca_studentul_l_a_activat_deja(self):
        self.profil.fcm_token = "deja-activat"
        self.profil.save()

        with override_settings(FIREBASE_SERVICE_ACCOUNT=self.CONT):
            raspuns = self.client.get(reverse("dashboard_student"))

        self.assertNotContains(raspuns, "Primește notificările și în browser")


class CheiaContuluiDeServiciu(TestCase):
    """Cheia poate veni ca JSON sau ca base64, fiindcă se strică ușor la copiere."""

    CONT = {"project_id": "p", "client_email": "c@d.e", "private_key": "cheie"}

    def test_json_direct(self):
        with override_settings(FIREBASE_SERVICE_ACCOUNT=json.dumps(self.CONT)):
            self.assertEqual(_cont_de_serviciu()["project_id"], "p")

    def test_json_codificat_base64(self):
        codificat = base64.b64encode(json.dumps(self.CONT).encode()).decode()
        with override_settings(FIREBASE_SERVICE_ACCOUNT=codificat):
            self.assertEqual(_cont_de_serviciu()["project_id"], "p")

    def test_text_care_nu_e_nici_una_nici_alta(self):
        with override_settings(FIREBASE_SERVICE_ACCOUNT="ceva gresit"):
            self.assertIsNone(_cont_de_serviciu())

    def test_cheie_incompleta_este_respinsa(self):
        """O cheie fără private_key ar produce erori obscure abia la trimitere."""
        with override_settings(FIREBASE_SERVICE_ACCOUNT=json.dumps({"project_id": "p"})):
            self.assertIsNone(_cont_de_serviciu())

    def test_nesetata(self):
        with override_settings(FIREBASE_SERVICE_ACCOUNT=None):
            self.assertIsNone(_cont_de_serviciu())


@override_settings(SECURE_SSL_REDIRECT=False)
class NotificariInAplicatie(BazaRezervari):
    """
    Caseta din bara de sus păstrează notificarea chiar dacă studentul a ratat
    mesajul de sistem sau nu are WhatsApp.
    """

    def setUp(self):
        super().setUp()
        self.profil = ProfilStudent.objects.get(utilizator=self.student)
        self.client.force_login(self.student)

    def _notificare(self, titlu="Rezervarea ta a fost preluată", citita=False):
        return Notificare.objects.create(
            profil=self.profil, titlu=titlu, corp="Mașina 1, 2 mar la 10:00", citita=citita
        )

    def test_clopotelul_apare_pentru_student(self):
        raspuns = self.client.get(reverse("dashboard_student"))

        self.assertContains(raspuns, "clopotelNotificari")

    def test_notificarea_este_afisata(self):
        self._notificare()

        raspuns = self.client.get(reverse("dashboard_student"))

        self.assertContains(raspuns, "Rezervarea ta a fost preluată")
        self.assertContains(raspuns, "necitita")

    def test_contorul_numara_doar_necitite(self):
        self._notificare()
        self._notificare(titlu="A doua")
        self._notificare(titlu="Deja citită", citita=True)

        raspuns = self.client.get(reverse("dashboard_student"))

        self.assertEqual(raspuns.context["notificari_necitite"], 2)

    def test_deschiderea_le_marcheaza_citite(self):
        self._notificare()
        self._notificare(titlu="A doua")

        raspuns = self.client.post(reverse("marcheaza_notificari_citite"))

        self.assertEqual(raspuns.json()["marcate"], 2)
        self.assertEqual(Notificare.objects.filter(citita=False).count(), 0)

    def test_marcarea_nu_atinge_alt_student(self):
        self._notificare()
        alt_profil = ProfilStudent.objects.get(utilizator=self.alt_student)
        a_lui = Notificare.objects.create(profil=alt_profil, titlu="A lui", corp="x")

        self.client.post(reverse("marcheaza_notificari_citite"))

        a_lui.refresh_from_db()
        self.assertFalse(a_lui.citita)

    def test_marcarea_cere_post_si_cont(self):
        self.assertEqual(
            self.client.get(reverse("marcheaza_notificari_citite")).status_code, 405
        )
        self.client.logout()
        self.assertEqual(
            self.client.post(reverse("marcheaza_notificari_citite")).status_code, 302
        )

    @patch("booking.push.trimite_push", return_value=None)
    @patch("booking.utils.trimite_whatsapp", return_value=None)
    def test_notificarea_ramane_chiar_daca_ambele_canale_esueaza(self, *_):
        notifica_student(
            self.profil, "rezervare_preluata_student", {"1": "x"},
            "Rezervarea ta a fost preluată", "Mașina 1",
        )

        notificare = Notificare.objects.get(profil=self.profil)
        self.assertEqual(notificare.titlu, "Rezervarea ta a fost preluată")
        self.assertFalse(notificare.citita)

    def test_cine_nu_e_student_nu_vede_clopotelul(self):
        self.client.logout()
        admin_user = User.objects.create_user(username="a@t.ro", email="a@t.ro")
        AdminCamin.objects.create(email="a@t.ro", camin=self.camin)
        self.client.force_login(admin_user)

        raspuns = self.client.get(reverse("dashboard_admin_camin"))

        self.assertNotContains(raspuns, "clopotelNotificari")


@override_settings(SECURE_SSL_REDIRECT=False)
class BazaCereriCont(TestCase):
    """Fixture comun: două cămine, șefii lor și un super-admin."""

    def setUp(self):
        app = SocialApp.objects.create(
            provider="google", name="Google", client_id="test", secret="test"
        )
        app.sites.add(Site.objects.get_current())

        self.t1 = Camin.objects.create(nume="T1", durata_interval=2)
        self.t2 = Camin.objects.create(nume="T2", durata_interval=2)

        self.sef_t1 = self._admin("sef1@tuiasi.ro", camin=self.t1, telefon="+40711111111")
        self.sef_t2 = self._admin("sef2@tuiasi.ro", camin=self.t2, telefon="+40722222222")
        self.super_admin = self._admin(
            "sefa@tuiasi.ro", camin=None, telefon="+40733333333", super_admin=True
        )

    def _admin(self, email, camin=None, telefon="", super_admin=False):
        user = User.objects.create_user(username=email, email=email)
        AdminCamin.objects.create(
            email=email, camin=camin, telefon=telefon, is_super_admin=super_admin
        )
        return user

    def _sesiune_dupa_google(self, email, nume="Pop", prenume="Ana"):
        """Ce lasă `callback` în sesiune când emailul nu e în liste."""
        sesiune = self.client.session
        sesiune["cerere_cont"] = {"email": email, "nume": nume, "prenume": prenume}
        sesiune.save()

    def _trimite(self, email="ana@student.tuiasi.ro", **suprascrieri):
        self._sesiune_dupa_google(email)
        date = {
            "nume": "Pop", "prenume": "Ana",
            "camin": self.t1.id, "numar_camera": "203",
            "telefon": "0712345678", "tara": "ro",
        }
        date.update(suprascrieri)
        return self.client.post(reverse("cerere_cont"), date, follow=True)

    def _mesaje(self, raspuns):
        return [str(m) for m in raspuns.context["messages"]]

    def _raspuns_twilio(self, MockClient, sid="SM1", stare="queued"):
        """Twilio întoarce șiruri; un MagicMock lăsat așa pică la scrierea în CharField."""
        mesaj = MockClient.return_value.messages.create.return_value
        mesaj.sid = sid
        mesaj.status = stare
        return mesaj


class AccesLaFormularulDeCerere(BazaCereriCont):
    """Formularul se deschide doar după o autentificare Google respinsă."""

    def test_callback_lasa_datele_in_sesiune_si_arata_butonul(self):
        strain = User.objects.create_user(
            username="strain", email="strain@student.tuiasi.ro",
            first_name="Ion", last_name="Ionescu",
        )
        self.client.force_login(strain)

        raspuns = self.client.get(reverse("callback"))

        self.assertContains(raspuns, "Cere un cont")
        self.assertEqual(
            self.client.session["cerere_cont"],
            {"email": "strain@student.tuiasi.ro", "prenume": "Ion", "nume": "Ionescu"},
        )
        # Contul neautorizat nu rămâne în baza de date.
        self.assertFalse(User.objects.filter(email="strain@student.tuiasi.ro").exists())

    def test_fara_autentificare_formularul_nu_se_deschide(self):
        raspuns = self.client.get(reverse("cerere_cont"), follow=True)

        self.assertEqual(CerereCont.objects.count(), 0)
        self.assertTrue(any("Autentifică-te" in m for m in self._mesaje(raspuns)))

    def test_emailul_vine_din_sesiune_nu_din_formular(self):
        """Altfel oricine ar putea cere cont în numele altcuiva."""
        self._trimite(email="ana@student.tuiasi.ro", email_ascuns="rector@tuiasi.ro")

        cerere = CerereCont.objects.get()
        self.assertEqual(cerere.email, "ana@student.tuiasi.ro")

    def test_studentul_deja_inregistrat_este_trimis_la_autentificare(self):
        user = User.objects.create_user(
            username="ana@student.tuiasi.ro", email="ana@student.tuiasi.ro"
        )
        ProfilStudent.objects.create(utilizator=user, camin=self.t1, activ=True)
        self._sesiune_dupa_google("ana@student.tuiasi.ro")

        raspuns = self.client.get(reverse("cerere_cont"), follow=True)

        self.assertTrue(any("Ai deja cont" in m for m in self._mesaje(raspuns)))


class TrimitereaCererii(BazaCereriCont):
    """Ce ajunge în baza de date când studentul apasă „Trimite"."""

    def test_cererea_se_salveaza_cu_caminul_ales(self):
        self._trimite(camin=self.t2.id, numar_camera="510")

        cerere = CerereCont.objects.get()
        self.assertEqual(cerere.camin, self.t2)
        self.assertEqual(cerere.numar_camera, "510")
        self.assertEqual(cerere.stare, CerereCont.IN_ASTEPTARE)

    def test_numarul_primeste_prefixul_de_tara(self):
        self._trimite(telefon="0712 345 678")

        self.assertEqual(CerereCont.objects.get().telefon, "+40712345678")

    def test_fara_numar_nu_se_salveaza_nimic(self):
        raspuns = self._trimite(telefon="")

        self.assertEqual(CerereCont.objects.count(), 0)
        self.assertTrue(any("numărul de telefon" in m for m in self._mesaje(raspuns)))

    def test_motivul_pentru_care_numarul_e_cerut_este_explicat(self):
        self._sesiune_dupa_google("ana@student.tuiasi.ro")

        raspuns = self.client.get(reverse("cerere_cont"))

        self.assertContains(raspuns, "când cererea ta e aprobată")

    def test_numarul_incomplet_este_respins(self):
        raspuns = self._trimite(telefon="071234567")

        self.assertEqual(CerereCont.objects.count(), 0)
        self.assertTrue(any("9 cifre" in m for m in self._mesaje(raspuns)))

    def test_fara_camin_nu_se_salveaza_nimic(self):
        raspuns = self._trimite(camin="")

        self.assertEqual(CerereCont.objects.count(), 0)
        self.assertTrue(any("căminul" in m for m in self._mesaje(raspuns)))

    def test_a_doua_cerere_nu_creeaza_duplicat(self):
        self._trimite()
        self._trimite()

        self.assertEqual(CerereCont.objects.count(), 1)

    def test_dupa_trimitere_vede_starea_cererii(self):
        self._trimite()

        raspuns = self.client.get(reverse("cerere_cont"))

        self.assertContains(raspuns, "Cererea ta a fost trimisă")


@override_settings(WHATSAPP_TEMPLATES={"cerere_cont_noua": "HXcerere"})
class AnuntareaAdminilor(BazaCereriCont):
    """Cine primește WhatsApp când vine o cerere."""

    def _cerere(self, camin):
        return CerereCont.objects.create(
            email="ana@student.tuiasi.ro", nume="Pop", prenume="Ana",
            camin=camin, numar_camera="203",
        )

    @patch("booking.utils.Client")
    def test_primesc_seful_caminului_si_super_adminul(self, MockClient):
        self._raspuns_twilio(MockClient)

        notifica_admini_cerere(self._cerere(self.t1))

        destinatari = {
            apel.kwargs["to"]
            for apel in MockClient.return_value.messages.create.call_args_list
        }
        self.assertEqual(
            destinatari, {"whatsapp:+40711111111", "whatsapp:+40733333333"}
        )

    @patch("booking.utils.Client")
    def test_adminii_fara_telefon_sunt_sariti(self, MockClient):
        self._raspuns_twilio(MockClient)
        AdminCamin.objects.filter(email="sef1@tuiasi.ro").update(telefon="")

        notifica_admini_cerere(self._cerere(self.t1))

        destinatari = [
            apel.kwargs["to"]
            for apel in MockClient.return_value.messages.create.call_args_list
        ]
        self.assertEqual(destinatari, ["whatsapp:+40733333333"])

    @patch("booking.utils.Client")
    def test_o_eroare_twilio_nu_opreste_cererea(self, MockClient):
        MockClient.return_value.messages.create.side_effect = RuntimeError("retea picata")

        self._trimite()

        self.assertEqual(CerereCont.objects.count(), 1)


class RezolvareaCererii(BazaCereriCont):
    """Aprobarea și respingerea, și cine are voie să le apese."""

    def setUp(self):
        super().setUp()
        self.cerere = CerereCont.objects.create(
            email="ana@student.tuiasi.ro", nume="Pop", prenume="Ana",
            camin=self.t1, numar_camera="203", telefon="+40712345678",
        )

    def _aproba(self, cine):
        self.client.force_login(cine)
        return self.client.post(
            reverse("aproba_cerere_cont", args=[self.cerere.id]), follow=True
        )

    def test_aprobarea_creeaza_contul(self):
        self._aproba(self.sef_t1)

        profil = ProfilStudent.objects.get(email="ana@student.tuiasi.ro")
        self.assertEqual(profil.camin, self.t1)
        self.assertEqual(profil.numar_camera, "203")
        self.assertEqual(profil.telefon, "+40712345678")
        self.assertTrue(profil.activ)
        self.cerere.refresh_from_db()
        self.assertEqual(self.cerere.stare, CerereCont.APROBATA)
        self.assertEqual(self.cerere.procesat_de, "sef1@tuiasi.ro")

    def test_aprobarea_refoloseste_contul_existent(self):
        """Conturile create la autentificare au username-ul fără domeniu."""
        User.objects.create_user(username="ana", email="ana@student.tuiasi.ro")

        self._aproba(self.super_admin)

        self.assertEqual(User.objects.filter(email="ana@student.tuiasi.ro").count(), 1)

    def test_seful_altui_camin_nu_poate_aproba(self):
        raspuns = self._aproba(self.sef_t2)

        self.assertContains(raspuns, "Nu ai acces")
        self.assertFalse(ProfilStudent.objects.exists())
        self.cerere.refresh_from_db()
        self.assertEqual(self.cerere.stare, CerereCont.IN_ASTEPTARE)

    def test_studentul_nu_poate_aproba(self):
        user = User.objects.create_user(
            username="alt@student.tuiasi.ro", email="alt@student.tuiasi.ro"
        )
        ProfilStudent.objects.create(utilizator=user, camin=self.t1)

        self._aproba(user)

        self.cerere.refresh_from_db()
        self.assertEqual(self.cerere.stare, CerereCont.IN_ASTEPTARE)

    def test_anonimul_nu_poate_aproba(self):
        raspuns = self.client.post(
            reverse("aproba_cerere_cont", args=[self.cerere.id])
        )

        self.assertEqual(raspuns.status_code, 302)
        self.assertIn("login", raspuns.url)
        self.cerere.refresh_from_db()
        self.assertEqual(self.cerere.stare, CerereCont.IN_ASTEPTARE)

    def test_respingerea_nu_creeaza_cont(self):
        self.client.force_login(self.sef_t1)

        self.client.post(
            reverse("respinge_cerere_cont", args=[self.cerere.id]),
            {"motiv": "Nu e cazat aici."}, follow=True,
        )

        self.assertFalse(ProfilStudent.objects.exists())
        self.cerere.refresh_from_db()
        self.assertEqual(self.cerere.stare, CerereCont.RESPINSA)
        self.assertEqual(self.cerere.motiv, "Nu e cazat aici.")

    def test_a_doua_aprobare_nu_mai_face_nimic(self):
        self._aproba(self.sef_t1)
        raspuns = self._aproba(self.super_admin)

        self.assertTrue(any("deja rezolvată" in m for m in self._mesaje(raspuns)))
        self.cerere.refresh_from_db()
        self.assertEqual(self.cerere.procesat_de, "sef1@tuiasi.ro")


class CereriInPaginaDeStudenti(BazaCereriCont):
    """Fiecare admin vede doar cererile care îl privesc."""

    def setUp(self):
        super().setUp()
        self.cerere_t1 = CerereCont.objects.create(
            email="ana@student.tuiasi.ro", nume="Pop", prenume="Ana",
            camin=self.t1, numar_camera="203",
        )
        self.cerere_t2 = CerereCont.objects.create(
            email="bogdan@student.tuiasi.ro", nume="Ilie", prenume="Bogdan",
            camin=self.t2, numar_camera="510",
        )

    def _cereri_vazute(self, cine):
        self.client.force_login(cine)
        raspuns = self.client.get(reverse("incarca_studenti"))
        return {c.email for c in raspuns.context["cereri"]}

    def test_seful_vede_doar_caminul_lui(self):
        self.assertEqual(self._cereri_vazute(self.sef_t1), {"ana@student.tuiasi.ro"})

    def test_super_adminul_le_vede_pe_toate(self):
        self.assertEqual(
            self._cereri_vazute(self.super_admin),
            {"ana@student.tuiasi.ro", "bogdan@student.tuiasi.ro"},
        )

    def test_badge_ul_numara_doar_cererile_deschise(self):
        self.cerere_t2.stare = CerereCont.APROBATA
        self.cerere_t2.save()
        self.client.force_login(self.super_admin)

        raspuns = self.client.get(reverse("incarca_studenti"))

        self.assertEqual(raspuns.context["cereri_in_asteptare"], 1)


class CamineleOferiteInFormular(BazaCereriCont):
    """Căminul de probă nu are ce căuta în lista studentului."""

    def setUp(self):
        super().setUp()
        # Căminul de probă e creat de migrarea 0012 și ascuns de 0019.
        self.test = Camin.objects.get(nume="API_TEST")
        self._sesiune_dupa_google("ana@student.tuiasi.ro")

    def test_migrarea_l_a_ascuns(self):
        self.assertFalse(self.test.accepta_cereri)

    def test_nu_apare_in_lista(self):
        raspuns = self.client.get(reverse("cerere_cont"))

        oferite = {c.nume for c in raspuns.context["camine"]}
        self.assertEqual(oferite, {"T1", "T2"})

    def test_nu_poate_fi_ales_nici_direct(self):
        raspuns = self._trimite(camin=self.test.id)

        self.assertEqual(CerereCont.objects.count(), 0)
        self.assertTrue(any("căminul" in m for m in self._mesaje(raspuns)))


@override_settings(WHATSAPP_TEMPLATES={"cerere_aprobata": "HXaprobata"})
class AnuntareaStudentuluiAprobat(BazaCereriCont):
    """Studentul află că are cont, fără să mai încerce din nou de unul singur."""

    def setUp(self):
        super().setUp()
        self.cerere = CerereCont.objects.create(
            email="ana@student.tuiasi.ro", nume="Pop", prenume="Ana",
            camin=self.t1, numar_camera="203", telefon="+40712345678",
        )

    def _aproba(self):
        self.client.force_login(self.sef_t1)
        return self.client.post(
            reverse("aproba_cerere_cont", args=[self.cerere.id]), follow=True
        )

    @patch("booking.utils.Client")
    def test_primeste_whatsapp_pe_numarul_din_cerere(self, MockClient):
        self._raspuns_twilio(MockClient, sid="SM9")

        self._aproba()

        argumente = MockClient.return_value.messages.create.call_args.kwargs
        self.assertEqual(argumente["to"], "whatsapp:+40712345678")
        self.assertEqual(argumente["content_sid"], "HXaprobata")

    @patch("booking.utils.Client")
    def test_notificarea_din_aplicatie_il_asteapta_la_autentificare(self, MockClient):
        self._raspuns_twilio(MockClient)

        self._aproba()

        profil = ProfilStudent.objects.get(email="ana@student.tuiasi.ro")
        notificare = Notificare.objects.get(profil=profil)
        self.assertIn("aprobată", notificare.titlu)
        self.assertIn("T1", notificare.corp)
        self.assertEqual(notificare.link, "/dashboard/student/")
        self.assertFalse(notificare.citita)

    @patch("booking.utils.Client")
    def test_fara_numar_ramane_doar_notificarea_din_aplicatie(self, MockClient):
        self.cerere.telefon = ""
        self.cerere.save()

        self._aproba()

        MockClient.return_value.messages.create.assert_not_called()
        self.assertEqual(Notificare.objects.count(), 1)

    @patch("booking.utils.Client")
    def test_un_whatsapp_esuat_nu_anuleaza_contul(self, MockClient):
        MockClient.return_value.messages.create.side_effect = RuntimeError("retea picata")

        self._aproba()

        profil = ProfilStudent.objects.get(email="ana@student.tuiasi.ro")
        self.assertTrue(profil.activ)
        self.cerere.refresh_from_db()
        self.assertEqual(self.cerere.stare, CerereCont.APROBATA)

    @patch("booking.utils.Client")
    def test_respingerea_nu_trimite_nimic(self, MockClient):
        self.client.force_login(self.sef_t1)

        self.client.post(
            reverse("respinge_cerere_cont", args=[self.cerere.id]), follow=True
        )

        MockClient.return_value.messages.create.assert_not_called()
        self.assertEqual(Notificare.objects.count(), 0)


@override_settings(SECURE_SSL_REDIRECT=False)
class ContacteSefiDeCamin(BazaCereriCont):
    """Pagina de acces interzis se construiește din baza de date."""

    def setUp(self):
        super().setUp()
        AdminCamin.objects.filter(email="sef1@tuiasi.ro").update(
            nume="Pop Ion", telefon="+40711111111"
        )

    def test_numele_scris_de_mana_este_folosit(self):
        sefi = sefi_de_camin()

        self.assertEqual([s.nume_afisat for s in sefi if s.camin == self.t1], ["Pop Ion"])

    def test_numele_se_deduce_din_adresa_cand_lipseste(self):
        admin = AdminCamin.objects.get(email="sef2@tuiasi.ro")

        self.assertEqual(admin.nume_afisat, "Sef2")

    def test_numele_dedus_desparte_punctele_si_liniutele(self):
        admin = AdminCamin.objects.create(
            email="daniel-stefan.samoila@student.tuiasi.ro",
            camin=self.t1, telefon="+40786713950",
        )

        self.assertEqual(admin.nume_afisat, "Daniel-Stefan Samoila")

    def test_super_adminii_nu_apar_ca_sefi_de_camin(self):
        emailuri = {s.email for s in sefi_de_camin()}

        self.assertNotIn("sefa@tuiasi.ro", emailuri)

    def test_cei_fara_telefon_nu_apar(self):
        AdminCamin.objects.filter(email="sef2@tuiasi.ro").update(telefon="")

        self.assertNotIn("sef2@tuiasi.ro", {s.email for s in sefi_de_camin()})

    def test_pagina_arata_contactele_din_baza_de_date(self):
        strain = User.objects.create_user(
            username="strain", email="strain@student.tuiasi.ro"
        )
        self.client.force_login(strain)

        raspuns = self.client.get(reverse("callback"))

        self.assertContains(raspuns, "Pop Ion")
        self.assertContains(raspuns, "wa.me/40711111111")
        # Adresa incercata apare, desi utilizatorul tocmai a fost deconectat.
        self.assertContains(raspuns, "strain@student.tuiasi.ro")


@override_settings(SECURE_SSL_REDIRECT=False)
class ComutatorulDeNotificari(BazaCereriCont):
    """Un cămin are un singur șef responsabil; ceilalți doar văd aplicația."""

    def setUp(self):
        super().setUp()
        self.observator = self._admin(
            "profesor@tuiasi.ro", camin=self.t1, telefon="+40799999999"
        )
        AdminCamin.objects.filter(email="profesor@tuiasi.ro").update(
            primeste_notificari=False
        )
        self.cerere = CerereCont.objects.create(
            email="ana@student.tuiasi.ro", nume="Pop", prenume="Ana",
            camin=self.t1, numar_camera="203",
        )

    def test_cel_debifat_nu_primeste_mesaj(self):
        numere = {a.telefon for a in destinatari_cerere_cont(self.t1)}

        self.assertEqual(numere, {"+40711111111", "+40733333333"})

    def test_cel_debifat_nu_apare_nici_pe_pagina_de_contact(self):
        self.assertNotIn("profesor@tuiasi.ro", {s.email for s in sefi_de_camin()})

    def test_implicit_un_admin_nou_primeste(self):
        nou = AdminCamin.objects.create(
            email="nou@tuiasi.ro", camin=self.t1, telefon="+40788888888"
        )

        self.assertTrue(nou.primeste_notificari)
        self.assertIn(nou.telefon, {a.telefon for a in destinatari_cerere_cont(self.t1)})


@override_settings(SECURE_SSL_REDIRECT=False)
class EditareaContactelor(BazaCereriCont):
    """Formularul din pagina căminului, de unde se schimbă datele de contact."""

    def _salveaza(self, cine, **date):
        self.client.force_login(cine)
        rand = AdminCamin.objects.get(email="sef1@tuiasi.ro")
        camp = {
            "salveaza_admin_id": rand.id,
            "nume": "Raba Alexandru",
            "telefon": "0758112351",
            "tara": "ro",
            "primeste_notificari": "on",
        }
        camp.update(date)
        return self.client.post(
            reverse("detalii_camin_admin", args=[self.t1.id]), camp, follow=True
        )

    def test_super_adminul_salveaza_numele_si_numarul(self):
        self._salveaza(self.super_admin)

        rand = AdminCamin.objects.get(email="sef1@tuiasi.ro")
        self.assertEqual(rand.nume, "Raba Alexandru")
        self.assertEqual(rand.telefon, "+40758112351")
        self.assertTrue(rand.primeste_notificari)

    def test_debifarea_se_salveaza(self):
        self._salveaza(self.super_admin, primeste_notificari="")

        self.assertFalse(AdminCamin.objects.get(email="sef1@tuiasi.ro").primeste_notificari)

    def test_numarul_incomplet_este_respins(self):
        raspuns = self._salveaza(self.super_admin, telefon="075811235")

        self.assertEqual(AdminCamin.objects.get(email="sef1@tuiasi.ro").telefon, "+40711111111")
        self.assertTrue(any("9 cifre" in m for m in self._mesaje(raspuns)))

    def test_seful_de_camin_nu_poate_modifica(self):
        raspuns = self._salveaza(self.sef_t1)

        self.assertEqual(AdminCamin.objects.get(email="sef1@tuiasi.ro").nume, "")
        self.assertTrue(any("super-adminii" in m for m in self._mesaje(raspuns)))

    def test_nu_se_poate_edita_adminul_altui_camin(self):
        tinta = AdminCamin.objects.get(email="sef2@tuiasi.ro")
        self.client.force_login(self.super_admin)

        raspuns = self.client.post(
            reverse("detalii_camin_admin", args=[self.t1.id]),
            {"salveaza_admin_id": tinta.id, "nume": "Intrus", "telefon": "", "tara": "ro"},
        )

        self.assertEqual(raspuns.status_code, 404)
        tinta.refresh_from_db()
        self.assertEqual(tinta.nume, "")


@override_settings(SECURE_SSL_REDIRECT=False)
class StudentulDezactivat(BazaCereriCont):
    """
    La început de an, cine s-a mutat în alt cămin sau a fost omis de pe liste
    ajunge dezactivat. Fără o cale proprie, rămâne blocat pe un ecran fix.
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="ana", email="ana@student.tuiasi.ro",
            first_name="Ana", last_name="Pop",
        )
        self.profil = ProfilStudent.objects.create(
            utilizator=self.user, camin=self.t2, numar_camera="305", activ=False
        )

    def test_vede_butonul_de_actualizare(self):
        self.client.force_login(self.user)

        raspuns = self.client.get(reverse("callback"))

        self.assertContains(raspuns, "nu mai este activ")
        self.assertContains(raspuns, "Cere actualizarea contului")

    def test_primeste_datele_in_sesiune(self):
        self.client.force_login(self.user)

        self.client.get(reverse("callback"))

        self.assertEqual(
            self.client.session["cerere_cont"],
            {"email": "ana@student.tuiasi.ro", "prenume": "Ana", "nume": "Pop"},
        )

    def test_formularul_spune_de_unde_vine(self):
        self._sesiune_dupa_google("ana@student.tuiasi.ro")

        raspuns = self.client.get(reverse("cerere_cont"))

        self.assertContains(raspuns, "Actualizarea contului")
        self.assertContains(raspuns, "T2")
        self.assertTrue(raspuns.context["reactivare"])

    def test_contul_activ_tot_nu_poate_cere(self):
        ProfilStudent.objects.filter(id=self.profil.id).update(activ=True)
        self._sesiune_dupa_google("ana@student.tuiasi.ro")

        raspuns = self.client.get(reverse("cerere_cont"), follow=True)

        self.assertTrue(any("Ai deja cont" in m for m in self._mesaje(raspuns)))

    def test_aprobarea_il_muta_si_il_reactiveaza(self):
        self._trimite(email="ana@student.tuiasi.ro", camin=self.t1.id, numar_camera="110")
        cerere = CerereCont.objects.get()
        self.client.force_login(self.sef_t1)

        self.client.post(reverse("aproba_cerere_cont", args=[cerere.id]), follow=True)

        self.profil.refresh_from_db()
        self.assertTrue(self.profil.activ)
        self.assertEqual(self.profil.camin, self.t1)
        self.assertEqual(self.profil.numar_camera, "110")

    def test_aprobarea_nu_creeaza_un_al_doilea_profil(self):
        """Istoricul de rezervări atârnă de profilul vechi; el trebuie refolosit."""
        self._trimite(email="ana@student.tuiasi.ro", camin=self.t1.id)
        cerere = CerereCont.objects.get()
        self.client.force_login(self.sef_t1)

        self.client.post(reverse("aproba_cerere_cont", args=[cerere.id]), follow=True)

        self.assertEqual(
            ProfilStudent.objects.filter(email="ana@student.tuiasi.ro").count(), 1
        )
        self.assertEqual(ProfilStudent.objects.get().id, self.profil.id)

    def test_profilul_legat_de_alt_cont_este_tot_refolosit(self):
        """
        Acelasi om poate avea doua randuri de utilizator cu aceeasi adresa:
        unul creat la autentificare, altul din import. Profilul e unul singur.
        """
        User.objects.create_user(username="ana@student.tuiasi.ro",
                                 email="ana@student.tuiasi.ro")
        self._trimite(email="ana@student.tuiasi.ro", camin=self.t1.id)
        cerere = CerereCont.objects.get()
        self.client.force_login(self.sef_t1)

        self.client.post(reverse("aproba_cerere_cont", args=[cerere.id]), follow=True)

        self.assertEqual(ProfilStudent.objects.count(), 1)
        self.assertEqual(ProfilStudent.objects.get().id, self.profil.id)


@override_settings(SECURE_SSL_REDIRECT=False, WHATSAPP_TEMPLATES={"cerere_cont_noua": "HXcerere"})
class UnSingurMesajPePersoana(BazaCereriCont):
    """
    Acelasi om poate avea mai multe randuri de admin cu acelasi numar: adresa
    institutionala si cea personala, sau doua camine. Mesajul e unul singur.
    """

    def setUp(self):
        super().setUp()
        # Al doilea cont al super-adminei, cu acelasi numar.
        self._admin("sefa2@tuiasi.ro", camin=None, telefon="+40733333333",
                    super_admin=True)
        self.cerere = CerereCont.objects.create(
            email="ana@student.tuiasi.ro", nume="Pop", prenume="Ana",
            camin=self.t1, numar_camera="203",
        )

    def test_numarul_repetat_apare_o_singura_data(self):
        numere = [a.telefon for a in destinatari_cerere_cont(self.t1)]

        self.assertEqual(sorted(numere), ["+40711111111", "+40733333333"])

    @patch("booking.utils.Client")
    def test_se_trimite_un_singur_mesaj_pe_numar(self, MockClient):
        self._raspuns_twilio(MockClient)

        notifica_admini_cerere(self.cerere)

        trimise = [a.kwargs["to"] for a in MockClient.return_value.messages.create.call_args_list]
        self.assertEqual(len(trimise), len(set(trimise)))
        self.assertEqual(sorted(trimise), ["whatsapp:+40711111111", "whatsapp:+40733333333"])

    def test_acelasi_om_pe_doua_camine_primeste_tot_o_data(self):
        """Seful de T1 e sef si la T2, cu acelasi numar, dar cererea e pentru T1."""
        self._admin("sef1personal@gmail.com", camin=self.t2, telefon="+40711111111")

        numere = [a.telefon for a in destinatari_cerere_cont(self.t1)]

        self.assertEqual(numere.count("+40711111111"), 1)


@override_settings(SECURE_SSL_REDIRECT=False)
class SchimbareDeAdresa(BazaImport):
    """
    Bobocii se inscriu cu adresa personala si primesc adresa institutionala in
    anul urmator. Fara recunoasterea lor, al doilea import le-ar da cont nou si
    l-ar dezactiva pe cel vechi, cu tot istoricul pe el.
    """

    def _confirma(self, dezactiveaza=False, reasigneaza=False):
        date = {"actiune": "confirma"}
        if dezactiveaza:
            date["dezactiveaza"] = "on"
        if reasigneaza:
            date["reasigneaza"] = "on"
        return self.client.post(reverse("incarca_studenti"), date, follow=True)

    def test_este_recunoscut_dupa_nume(self):
        self._student("ana.pop@gmail.com", self.t1)
        ProfilStudent.objects.filter(email="ana.pop@gmail.com").update(
            nume="Pop", prenume="Ana"
        )

        raspuns = self._incarca([["ana.pop@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])

        plan = raspuns.context["plan"]
        self.assertEqual(len(plan.de_reasignat), 1)
        profil, rand = plan.de_reasignat[0]
        self.assertEqual(profil.email, "ana.pop@gmail.com")
        self.assertEqual(rand.email, "ana.pop@student.tuiasi.ro")

    def test_bifa_muta_adresa_si_pastreaza_contul(self):
        vechi = self._student("ana.pop@gmail.com", self.t1)
        ProfilStudent.objects.filter(id=vechi.id).update(nume="Pop", prenume="Ana")

        self._incarca([["ana.pop@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])
        self._confirma(dezactiveaza=True, reasigneaza=True)

        self.assertEqual(ProfilStudent.objects.count(), 1)
        profil = ProfilStudent.objects.get()
        self.assertEqual(profil.id, vechi.id)
        self.assertEqual(profil.email, "ana.pop@student.tuiasi.ro")
        self.assertEqual(profil.numar_camera, "203")
        self.assertTrue(profil.activ)

    def test_fara_bifa_ramane_comportamentul_vechi(self):
        vechi = self._student("ana.pop@gmail.com", self.t1)
        ProfilStudent.objects.filter(id=vechi.id).update(nume="Pop", prenume="Ana")

        self._incarca([["ana.pop@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])
        self._confirma(dezactiveaza=True)

        self.assertEqual(ProfilStudent.objects.count(), 2)
        vechi.refresh_from_db()
        self.assertFalse(vechi.activ)

    def test_diacriticele_si_ordinea_nu_incurca(self):
        vechi = self._student("ion@gmail.com", self.t1)
        ProfilStudent.objects.filter(id=vechi.id).update(
            nume="Țăranu", prenume="Ion-Andrei"
        )

        raspuns = self._incarca([["ion@student.tuiasi.ro", "Ion Andrei", "Taranu", "T1", "11"]])

        self.assertEqual(len(raspuns.context["plan"].de_reasignat), 1)

    def test_omonimii_nu_sunt_impereceati(self):
        """Doi studenți cu același nume nu pot fi deosebiți, deci nu se ating."""
        for email in ("pop1@gmail.com", "pop2@gmail.com"):
            p = self._student(email, self.t1)
            ProfilStudent.objects.filter(id=p.id).update(nume="Pop", prenume="Ana")

        raspuns = self._incarca([["ana.pop@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])

        self.assertEqual(raspuns.context["plan"].de_reasignat, [])
        self.assertEqual(len(raspuns.context["plan"].de_creat), 1)

    def test_acelasi_nume_de_doua_ori_in_fisier_nu_se_potriveste(self):
        p = self._student("ana.pop@gmail.com", self.t1)
        ProfilStudent.objects.filter(id=p.id).update(nume="Pop", prenume="Ana")

        raspuns = self._incarca([
            ["ana.pop@student.tuiasi.ro", "Pop", "Ana", "T1", "203"],
            ["ana.pop2@student.tuiasi.ro", "Pop", "Ana", "T1", "204"],
        ])

        self.assertEqual(raspuns.context["plan"].de_reasignat, [])

    def test_adresa_noua_cu_cont_propriu_este_semnalata_nu_aplicata(self):
        p = self._student("ana.pop@gmail.com", self.t1)
        ProfilStudent.objects.filter(id=p.id).update(nume="Pop", prenume="Ana")
        User.objects.create_user(username="altcineva", email="ana.pop@student.tuiasi.ro")

        raspuns = self._incarca([["ana.pop@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])

        plan = raspuns.context["plan"]
        self.assertEqual(plan.de_reasignat, [])
        self.assertEqual(len(plan.reasignari_blocate), 1)
        self.assertIn("deja un cont", plan.reasignari_blocate[0][2])

    def test_studentul_mutat_in_alt_camin_isi_pastreaza_contul(self):
        vechi = self._student("ana.pop@gmail.com", self.t1)
        ProfilStudent.objects.filter(id=vechi.id).update(nume="Pop", prenume="Ana")

        self._incarca([["ana.pop@student.tuiasi.ro", "Pop", "Ana", "T2", "305"]])
        self._confirma(dezactiveaza=True, reasigneaza=True)

        self.assertEqual(ProfilStudent.objects.count(), 1)
        profil = ProfilStudent.objects.get()
        self.assertEqual(profil.id, vechi.id)
        self.assertEqual(profil.camin, self.t2)

    def test_rezervarile_raman_pe_acelasi_cont(self):
        vechi = self._student("ana.pop@gmail.com", self.t1)
        ProfilStudent.objects.filter(id=vechi.id).update(nume="Pop", prenume="Ana")
        masina = Masina.objects.create(camin=self.t1, nume="M1")
        Rezervare.objects.create(
            utilizator=vechi.utilizator, masina=masina,
            data_rezervare=LUNI, ora_start=time(8, 0), ora_end=time(10, 0),
        )

        self._incarca([["ana.pop@student.tuiasi.ro", "Pop", "Ana", "T1", "203"]])
        self._confirma(reasigneaza=True)

        profil = ProfilStudent.objects.get()
        self.assertEqual(
            Rezervare.objects.filter(utilizator=profil.utilizator).count(), 1
        )
