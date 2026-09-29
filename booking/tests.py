"""
Teste pentru regulile de rezervare.

Timpul este înghețat (`timezone.now` este mock-uit) la luni, 2 martie 2026,
ora 09:00 în Europe/Bucharest (07:00 UTC). Astfel regulile care depind de
săptămâna curentă sunt deterministe, indiferent de ziua în care rulează
testele, iar comportamentul dependent de fus orar poate fi verificat.
"""

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

from booking.utils import trimite_whatsapp, valideaza_numar
from booking.models import (
    AdminCamin,
    Camin,
    IntervalDezactivare,
    Masina,
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

    @patch("booking.views.trimite_whatsapp")
    def test_preluare_rezervare_cu_prioritate_mai_mica(self, mock_whatsapp):
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
        mock_whatsapp.assert_called_once()


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
