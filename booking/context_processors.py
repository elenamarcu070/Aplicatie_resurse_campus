from booking.models import AdminCamin, ProfilStudent

def rol_utilizator(request):
    user = request.user
    context = {}

    if user.is_authenticated:
        context['user'] = user

        admin_camin = AdminCamin.objects.filter(email=user.email).first()
        if admin_camin:
            context['rol'] = 'admin_camin'
            context['nume_camin'] = admin_camin.camin.nume
            context['is_admin_camin'] = True  # Adaugă is_admin_camin în context
        elif user.email.endswith('@student.tuiasi.ro'):
            student = ProfilStudent.objects.filter(utilizator__email=user.email).first()
            
            if not student:
                email_parts = user.email.split('@')[0].split('.')
                if len(email_parts) >= 2:
                    nume_email = email_parts[-1].replace('-', ' ').title()
                    prenume_email = email_parts[0].replace('-', ' ').title()
                    
                    student = ProfilStudent.objects.filter(
                        utilizator__last_name__iexact=nume_email,
                        utilizator__first_name__iexact=prenume_email
                    ).first()

            if student:
                context['rol'] = 'student'
                if student.camin:
                    context['nume_camin'] = student.camin.nume
                context['is_admin_camin'] = False  # Adaugă is_admin_camin în context
                if student.utilizator.email != user.email:
                    student.utilizator.email = user.email
                    student.utilizator.username = user.email
                    student.utilizator.save()
        else:  # Adaugă și pentru alți utilizatori
            context['is_admin_camin'] = False

    return context



from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)