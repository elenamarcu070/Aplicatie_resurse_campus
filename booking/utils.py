# booking/utils.py
from twilio.rest import Client
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def trimite_sms(numar, mesaj):
    """Trimite SMS prin Twilio cu expeditor alfanumeric WASHTUIASI."""
    if not numar:
        logger.warning("❌ Lipsă număr destinatar.")
        return
    if not numar.startswith("+"):
        logger.warning(f"❌ Număr fără prefix internațional: {numar}")
        return

    try:
        logger.info(f"📤 Trimit SMS către {numar} cu sender WASHTUIASI")
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            to=numar,
            messaging_service_sid=settings.TWILIO_MESSAGING_SERVICE_SID,  # ← nu 'WASHTUIASI'
            body=mesaj,
        )
        logger.info(f"✅ Twilio: SID={msg.sid}, STATUS={msg.status}")
    except Exception as e:
        logger.error(f"💥 Eroare Twilio SMS: {e}")

#"twilio-domain-verification=aeef8bb394851e10b5e36ff12d8721f3"

import os, json
from twilio.rest import Client
from django.conf import settings

def trimite_whatsapp(destinatar, template_name, variabile):
    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN
    from_number = settings.TWILIO_WHATSAPP_NUMBER

    TEMPLATE_MAP = {
        "rezervare_preluata": os.getenv("WHATSAPP_CONTENT_SID_PRELUATA"),
        "anulare_rezervare_interval": os.getenv("WHATSAPP_CONTENT_SID_INTERVAL"),
        "anulare_rezervare_masina_complet": os.getenv("WHATSAPP_CONTENT_SID_COMPLET"),
    }

    content_sid = TEMPLATE_MAP.get(template_name)
    if not content_sid:
        print(f"⚠️ Template necunoscut: {template_name}")
        return

    # 🧼 Curățăm numărul și variabilele
    destinatar = destinatar.replace(" ", "")
    variabile = {str(k): str(v) for k, v in variabile.items()}

    client = Client(account_sid, auth_token)
    message = client.messages.create(
        from_=f'whatsapp:{from_number}',
        to=f'whatsapp:{destinatar}',
        content_sid=content_sid,
        content_variables=json.dumps(variabile)
    )

    print(f"✅ WhatsApp trimis către {destinatar} (template: {template_name}) — SID: {message.sid}")

