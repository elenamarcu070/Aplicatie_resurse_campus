# booking/context_processors.py

from booking.models import AdminCamin, ProfilStudent

def rol_utilizator(request):
    user = request.user
    context = {}

    if user.is_authenticated:
        context['user'] = user

        from booking.models import AdminCamin, ProfilStudent, Camin

        # Verifică dacă e admin de cămin
        admin_camin = AdminCamin.objects.filter(email=user.email).first()

    if admin_camin:
        context['rol'] = 'admin_camin'
        context['is_admin_camin'] = True

        # 👑 SUPER ADMIN
        if admin_camin.is_super_admin:
            context['is_super_admin'] = True

            camine = Camin.objects.all()
            context['camine_disponibile'] = camine

            camin_id = request.session.get("camin_selectat")

            # 🔥 dacă NU există în sesiune → setăm primul
            if camin_id:
                camin_selectat = camine.filter(id=camin_id).first()
            else:
                camin_selectat = camine.first()
                if camin_selectat:
                    request.session["camin_selectat"] = camin_selectat.id

            context['camin_selectat'] = camin_selectat
            context['nume_camin'] = camin_selectat.nume if camin_selectat else "Super Admin"


        else:
            context['is_super_admin'] = False
            context['camin_selectat'] = admin_camin.camin
            context['nume_camin'] = admin_camin.camin.nume if admin_camin.camin else "Fără cămin"
            context['camine_disponibile'] = [admin_camin.camin] if admin_camin.camin else []

    return context



# Un mic helper pentru template-uri (dacă mai folosești în HTML)
from django import template
register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

from django.conf import settings

def firebase_config(request):
    return {
        "firebase_config": {
            "apiKey": settings.FIREBASE_API_KEY,
            "authDomain": settings.FIREBASE_AUTH_DOMAIN,
            "projectId": settings.FIREBASE_PROJECT_ID,
            "storageBucket": settings.FIREBASE_STORAGE_BUCKET,
            "messagingSenderId": settings.FIREBASE_MESSAGING_SENDER_ID,
            "appId": settings.FIREBASE_APP_ID,
            "vapidKey": settings.FIREBASE_VAPID_KEY,
        }
    }
