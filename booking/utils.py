# booking/utils.py
from twilio.rest import Client
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

from .models import SMSLog

def trimite_sms(numar, mesaj, utilizator=None):
    if not numar or not numar.startswith("+"):
        logger.warning(f"❌ Număr invalid: {numar}")
        return

    try:
        # 🇷🇴 România → alfanumeric
        if numar.startswith("+40"):
            from_number = "WASHTUIASI"
        else:
            from_number = settings.TWILIO_PHONE_NUMBER

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            to=numar,
            from_=from_number,
            body=mesaj,
        )

        SMSLog.objects.create(
            utilizator=utilizator,
            telefon=numar,
            mesaj=mesaj,
            twilio_sid=msg.sid,
            status=msg.status,
        )

        logger.info(f"✅ SMS trimis către {numar} cu SID={msg.sid}, STATUS={msg.status}")

    except Exception as e:
        logger.error(f"💥 Eroare Twilio SMS: {e}")
