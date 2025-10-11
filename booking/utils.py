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

import os
from twilio.rest import Client

def trimite_whatsapp_template(destinatar, data, ora_start, ora_end, masina):
    """
    Trimite un mesaj WhatsApp folosind un template aprobat din Meta Business Manager.
    """
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    from_number = os.getenv('TWILIO_WHATSAPP_NUMBER')
    template_name = os.getenv('WHATSAPP_TEMPLATE_NAME')
    language_code = os.getenv('WHATSAPP_TEMPLATE_LANGUAGE', 'ro')

    client = Client(account_sid, auth_token)
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": data},
                {"type": "text", "text": ora_start},
                {"type": "text", "text": ora_end},
                {"type": "text", "text": masina},
            ],
        }
    ]

    message = client.messages.create(
        from_=f'whatsapp:{from_number}',
        to=f'whatsapp:{destinatar}',
        template={
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    )

    return message.sid
