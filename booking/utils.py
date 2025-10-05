
# booking/utils.py
from twilio.rest import Client
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def trimite_sms(numar, mesaj):
    """
    Trimite SMS prin Twilio.
    Loghează statusul (queued/sent/error) pentru debugging pe Railway.
    """
    if not numar:
        logger.warning("❌ SMS: lipsă număr destinatar.")
        return
    if not numar.startswith("+"):
        logger.warning(f"❌ SMS: număr fără prefix internațional: {numar}")
        return

    try:
        logger.info(f"📤 Trimit SMS către {numar}...")
        client = Client(
            settings.TWILIO_ACCOUNT_SID,   # din Railway ENV
            settings.TWILIO_AUTH_TOKEN     # din Railway ENV
        )
        msg = client.messages.create(
            to=numar,
            from_=settings.TWILIO_PHONE_NUMBER,  # din Railway ENV
            body=mesaj,
        )
        logger.info(f"✅ Twilio: SID={msg.sid}, STATUS={msg.status}")
    except Exception as e:
        logger.error(f"💥 Eroare Twilio SMS: {e}")



