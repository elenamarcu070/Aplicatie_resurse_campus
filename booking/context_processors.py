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
