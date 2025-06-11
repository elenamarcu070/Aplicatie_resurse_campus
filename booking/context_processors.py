from booking.models import AdminCamin, ProfilStudent


def rol_utilizator(request):
    user = request.user
    rol = None
    nume_camin = None

    if user.is_authenticated:
        # Verifică mai întâi dacă e admin
        admin_camin = AdminCamin.objects.filter(email=user.email).first()
        if admin_camin:
            rol = 'admin_camin'
            nume_camin = admin_camin.camin.nume
        
        # Verifică dacă e student
        elif user.email.endswith('@student.tuiasi.ro'):
            # Caută direct după email
            student = ProfilStudent.objects.filter(utilizator__email=user.email).first()
            
            if not student:
                # Dacă nu găsește după email, încearcă după nume și prenume
                email_parts = user.email.split('@')[0].split('.')
                if len(email_parts) >= 2:
                    nume_email = email_parts[-1].replace('-', ' ').title()
                    prenume_email = email_parts[0].replace('-', ' ').title()
                    
                    student = ProfilStudent.objects.filter(
                        utilizator__last_name__iexact=nume_email,
                        utilizator__first_name__iexact=prenume_email
                    ).first()

            if student:
                rol = 'student'
                if student.camin:
                    nume_camin = student.camin.nume
                
                # Actualizează email-ul studentului dacă e diferit
                if student.utilizator.email != user.email:
                    student.utilizator.email = user.email
                    student.utilizator.username = user.email
                    student.utilizator.save()

    return {
        'rol': rol,
        'nume_camin': nume_camin,
    }



from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)