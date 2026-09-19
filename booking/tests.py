"""
Teste pentru regulile de rezervare.

Timpul este înghețat (`timezone.now` este mock-uit) la luni, 2 martie 2026,
ora 09:00 în Europe/Bucharest (07:00 UTC). Astfel regulile care depind de
săptămâna curentă sunt deterministe, indiferent de ziua în care rulează
testele, iar comportamentul dependent de fus orar poate fi verificat.
"""

import json
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from unittest.mock import patch

from allauth.socialaccount.models import SocialApp
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from booking.models import (
    AdminCamin,
    Camin,
    IntervalDezactivare,
    Masina,
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
