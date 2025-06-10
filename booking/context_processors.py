from booking.models import AdminCamin, ProfilStudent

def rol_utilizator(request):
    user = request.user
    rol = None
    nume_camin = None

    if user.is_authenticated:
        admin_camin = AdminCamin.objects.filter(email=user.email).first()
        if admin_camin:
            rol = 'admin_camin'
            nume_camin = admin_camin.camin.nume
        elif user.email.endswith('@student.tuiasi.ro'):
            rol = 'student'
            profil = ProfilStudent.objects.filter(utilizator=user).first()
            if profil and profil.camin:
                nume_camin = profil.camin.nume

    return {
        'rol': rol,
        'nume_camin': nume_camin,
    }
