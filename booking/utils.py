from twilio.rest import Client
from django.conf import settings

def trimite_sms(destinatar, mesaj):
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    try:
        mesaj_sms = client.messages.create(
            body=mesaj,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=destinatar
        )
        print(f"SMS trimis către {destinatar}: {mesaj_sms.sid}")
        return True
    except Exception as e:
        print(f"Eroare la trimiterea SMS-ului: {e}")
        return False


