# booking/utils.py
from twilio.rest import Client
from django.conf import settings
import logging

import os
def trimite_whatsapp_anulare(destinatar, data, ora_start, ora_end, masina):
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
        content_sid=None,
        body=None,
        persistent_action=None,
        interactive_data=None,
        template={
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    )

    return message.sid