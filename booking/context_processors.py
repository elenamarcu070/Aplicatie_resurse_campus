# booking/context_processors.py

from booking.models import AdminCamin, ProfilStudent

def rol_utilizator(request):
    user = request.user
    context = {}

    if user.is_authenticated:
        context['user'] = user

        # Verifică dacă e admin de cămin
        admin_camin = AdminCamin.objects.filter(email=user.email).first()
        if admin_camin:
            context['rol'] = 'admin_camin'
            context['nume_camin'] = admin_camin.camin.nume
            context['is_admin_camin'] = True
        else:
            # Verifică dacă e student
            student = ProfilStudent.objects.filter(utilizator=user).first()
            if student:
                context['rol'] = 'student'
                context['is_admin_camin'] = False
                if student.camin:
                    context['nume_camin'] = student.camin.nume

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

from booking.models import Camin, AdminCamin

def camin_selectat_context(request):
    user = request.user
    camin_selectat = None
    camine = None
    is_super_admin = False

    if user.is_authenticated:
        admin = AdminCamin.objects.filter(email=user.email).first()
        if admin and admin.is_super_admin:
            is_super_admin = True
            camine = Camin.objects.all()
            camin_id = request.session.get("camin_selectat")
            if camin_id:
                camin_selectat = Camin.objects.filter(id=camin_id).first()
                if not camin_selectat and camine.exists():
                    camin_selectat = camine.first()
                    request.session["camin_selectat"] = camin_selectat.id

    return {
        "is_super_admin": is_super_admin,
        "camine_disponibile": camine,
        "camin_selectat": camin_selectat,
    }
