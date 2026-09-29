"""
Notificări push în browser, prin Firebase Cloud Messaging.

Trimiterea se face prin API-ul HTTP v1 al FCM, care cere un token OAuth2 obținut
dintr-un cont de serviciu. Cheia contului de serviciu stă în variabila de mediu
`FIREBASE_SERVICE_ACCOUNT`, ca JSON. Fără ea, trimiterea este dezactivată și
aplicația funcționează exact ca înainte.

Push-ul completează WhatsApp-ul, nu îl înlocuiește: pe iPhone ajunge doar dacă
studentul a adăugat site-ul pe ecranul principal, iar token-ul expiră când își
schimbă browserul.
"""

import json
import logging

import requests
from django.conf import settings

from booking.models import NotificareLog

logger = logging.getLogger(__name__)

SCOP_FCM = "https://www.googleapis.com/auth/firebase.messaging"
TIMP_MAXIM = 10

# Codurile prin care FCM spune ca token-ul nu mai e bun de nimic.
TOKEN_INVALID = {"UNREGISTERED", "INVALID_ARGUMENT", "NOT_FOUND"}


def _cont_de_serviciu():
    """Cheia contului de serviciu, ca dicționar, sau None dacă nu e configurată."""
    brut = getattr(settings, "FIREBASE_SERVICE_ACCOUNT", None)
    if not brut:
        return None
    try:
        return json.loads(brut) if isinstance(brut, str) else brut
    except json.JSONDecodeError:
        logger.error("FIREBASE_SERVICE_ACCOUNT nu conține JSON valid.")
        return None


def _token_acces(info_cont):
    """Schimbă cheia contului de serviciu pe un token OAuth2 de scurtă durată."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    credentiale = service_account.Credentials.from_service_account_info(
        info_cont, scopes=[SCOP_FCM]
    )
    credentiale.refresh(Request())
    return credentiale.token


def push_este_configurat():
    return _cont_de_serviciu() is not None


def trimite_push(profil, titlu, corp, date_suplimentare=None):
    """
    Trimite o notificare push către un student și înregistrează încercarea.

    Întoarce rândul de jurnal, sau None dacă studentul nu are token ori push-ul
    nu e configurat. Nu aruncă excepții.
    """
    if not profil or not profil.fcm_token:
        return None

    info_cont = _cont_de_serviciu()
    if not info_cont:
        logger.info("Push neconfigurat (lipsește FIREBASE_SERVICE_ACCOUNT); sar peste.")
        return None

    jurnal = NotificareLog.objects.create(
        profil=profil,
        canal=NotificareLog.PUSH,
        destinatar=profil.fcm_token[:20],
        sablon=titlu[:64],
    )

    try:
        proiect = info_cont.get("project_id") or settings.FIREBASE_PROJECT_ID
        adresa = f"https://fcm.googleapis.com/v1/projects/{proiect}/messages:send"
        mesaj = {
            "message": {
                "token": profil.fcm_token,
                "notification": {"title": titlu, "body": corp},
                "data": {str(k): str(v) for k, v in (date_suplimentare or {}).items()},
                "webpush": {
                    "fcm_options": {"link": (settings.SITE_DOMAIN or "") + "/dashboard/student/"},
                },
            }
        }

        raspuns = requests.post(
            adresa,
            headers={
                "Authorization": f"Bearer {_token_acces(info_cont)}",
                "Content-Type": "application/json",
            },
            json=mesaj,
            timeout=TIMP_MAXIM,
        )

        if raspuns.status_code == 200:
            jurnal.stare = "delivered"
            jurnal.message_sid = (raspuns.json().get("name") or "")[-64:]
            jurnal.save(update_fields=["stare", "message_sid", "actualizat_la"])
            return jurnal

        # FCM nu raspunde intotdeauna cu JSON (de exemplu la erori de la proxy).
        try:
            detaliu = raspuns.json().get("error", {}) if raspuns.content else {}
        except ValueError:
            detaliu = {}

        cod = str(detaliu.get("status") or raspuns.status_code)
        jurnal.stare = "failed"
        jurnal.cod_eroare = cod[:16]
        jurnal.detaliu = str(detaliu.get("message") or raspuns.text or "")[:500]
        jurnal.save(update_fields=["stare", "cod_eroare", "detaliu", "actualizat_la"])

        if cod in TOKEN_INVALID:
            # Token-ul nu mai e valabil: îl ștergem, ca să nu reîncercăm la infinit.
            # Studentul va primi din nou butonul de activare pe dashboard.
            profil.fcm_token = None
            profil.save(update_fields=["fcm_token"])
            logger.info(f"Token push invalid, sters pentru {profil.email}")

        logger.warning(f"Push nelivrat catre {profil.email}: {cod}")

    except Exception as e:
        jurnal.stare = NotificareLog.EROARE_TRIMITERE
        jurnal.detaliu = str(e)[:500]
        jurnal.save(update_fields=["stare", "detaliu", "actualizat_la"])
        logger.error(f"Eroare la trimiterea push: {e}")

    return jurnal


def notifica_student(profil, sablon, variabile, titlu, corp):
    """
    Trimite aceeași veste pe ambele canale.

    Un canal care eșuează nu îl oprește pe celălalt și nu oprește acțiunea care
    a declanșat notificarea.
    """
    from booking.utils import trimite_whatsapp

    rezultat = {"whatsapp": None, "push": None}

    if profil and profil.telefon:
        try:
            rezultat["whatsapp"] = trimite_whatsapp(
                profil.telefon, sablon, variabile, profil=profil
            )
        except Exception as e:
            logger.error(f"Eroare neasteptata la WhatsApp: {e}")

    try:
        rezultat["push"] = trimite_push(profil, titlu, corp)
    except Exception as e:
        logger.error(f"Eroare neasteptata la push: {e}")

    return rezultat
