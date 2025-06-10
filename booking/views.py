import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib import messages
from booking.models import Camin, ProfilStudent , AdminCamin , Rezervare, ProgramMasina, Masina,Avertisment
from django.contrib.auth.models import User
from datetime import datetime, timedelta, time
from datetime import date
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q
from django.utils.timezone import now

from allauth.socialaccount import providers
from allauth.socialaccount.providers.google.views import oauth2_login
from allauth.socialaccount.models import SocialApp
from django.http import HttpRequest
from django.contrib.sites.models import Site
import pandas as pd
from django.core.files.storage import default_storage



# =========================
# Pagina Home
# =========================


def home(request):
    return render(request, 'home.html')

# =========================
# Callback după autentificare Google
# =========================

# Forțăm providerul să aleagă aplicația corectă din admin (după nume)

# @login_required
# def callback(request):
#     user = request.user
#     email = user.email.strip().lower()

#     # Verificare dacă este admin de cămin
#     admin = AdminCamin.objects.filter(email=email).first()
#     if admin:
#         return redirect('dashboard_admin_camin')

#     # Dacă este student TUIASI sau cu email personal
#     # Ne asigurăm că are profil student asociat
#     profil, created = ProfilStudent.objects.get_or_create(utilizator=user)

#     return redirect('dashboard_student')
# VALID_EMAIL_DOMAINS = ['student.tuiasi.ro', 'academic.tuiasi.ro']


# from django.contrib.auth import logout

def callback(request):
    user = request.user
    try:
        social_account = SocialAccount.objects.get(user=user)
        email = social_account.extra_data.get('email', '')

        # Admin cămin
        if AdminCamin.objects.filter(email=email).exists():
            return redirect('dashboard_admin_camin')

        # Student valid?
        if ProfilStudent.objects.filter(utilizator__email=email).exists():
            return redirect('dashboard_student')

        # Nu e în baza de date → deloghează și arată mesaj
        logout(request)
        return render(request, 'eroare.html', {
            'mesaj': 'Contul tău nu se află în baza de date. Te rugăm să contactezi administratorul căminului.'
        })

    except SocialAccount.DoesNotExist:
        return render(request, 'eroare.html', {
            'mesaj': 'Contul Google nu a fost găsit.'
        })

def logout_view(request):
    logout(request)
    return redirect("/accounts/google/login/?process=login&prompt=select_account")

# =========================
# Logout personalizat
# =========================
def custom_logout(request):
    logout(request)
    return redirect('https://accounts.google.com/Logout?continue=https://appengine.google.com/_ah/logout?continue=http://127.0.0.1:8000/')

# =========================
# Dashboard-uri după rol
# =========================
@login_required
def dashboard_student(request):
    return render(request, 'dashboard/student.html')



@login_required
def dashboard_admin_camin(request):
    camine = Camin.objects.all()
    return render(request, 'dashboard/admin_camin.html', {
        'camine': camine
    })





from booking.models import Masina, ProgramMasina
from booking.models import Uscator, ProgramUscator
from collections import Counter



@login_required
def lista_camine_admin(request):
    camine = Camin.objects.all()
    return render(request, 'dashboard/admin_camin/lista_camine.html', {'camine': camine})


@login_required
def adauga_camin_view(request):
    if request.method == 'POST':
        nume = request.POST.get('nume')
        if nume:
            Camin.objects.create(nume=nume)
            messages.success(request, 'Cămin adăugat cu succes!')
            return redirect('dashboard_admin_camin')
    return render(request, 'dashboard/admin_camin/adauga_camin.html')

@login_required
def sterge_camin_view(request, camin_id):
    camin = get_object_or_404(Camin, id=camin_id)
    camin.delete()
    messages.success(request, f'Căminul "{camin.nume}" a fost șters.')
    return redirect('dashboard_admin_camin')




@login_required
def detalii_camin_admin(request, camin_id):
    camin = get_object_or_404(Camin, id=camin_id)

    if request.method == 'POST':
        # Adăugare admin
        if 'email_nou_admin' in request.POST:
            email_nou = request.POST.get('email_nou_admin').strip().lower()
            if email_nou:
                if not AdminCamin.objects.filter(camin=camin, email=email_nou).exists():
                    AdminCamin.objects.create(camin=camin, email=email_nou)
                    messages.success(request, f"Adminul '{email_nou}' a fost adăugat cu succes.")
                else:
                    messages.warning(request, f"'{email_nou}' este deja admin la cămin.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # Ștergere admin
        if 'sterge_admin_id' in request.POST:
            admin_id = request.POST.get('sterge_admin_id')
            admin = get_object_or_404(AdminCamin, id=admin_id)
            admin.delete()
            messages.success(request, f"Adminul '{admin.email}' a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # Adăugare mașină
        if 'nume_masina' in request.POST:
            nume = request.POST.get('nume_masina').strip()
            if nume:
                Masina.objects.create(camin=camin, nume=nume, activa=True)
                messages.success(request, f"Mașina '{nume}' a fost adăugată.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # Ștergere mașină
        if 'sterge_masina_id' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['sterge_masina_id'])
            masina.delete()
            messages.success(request, f"Mașina '{masina.nume}' a fost ștearsă.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # Toggle activare/dezactivare mașină
        if 'toggle_masina_id' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['toggle_masina_id'])
            masina.activa = not masina.activa
            masina.save()
            messages.success(request, f"Statusul mașinii '{masina.nume}' a fost modificat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # Editare nume mașină
        if 'edit_masina_id' in request.POST and 'nume_masina_nou' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['edit_masina_id'])
            nume_nou = request.POST.get('nume_masina_nou').strip()
            if nume_nou:
                masina.nume = nume_nou
                masina.save()
                messages.success(request, f"Numele mașinii a fost actualizat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # Adăugare uscător
        if 'nume_uscator' in request.POST:
            nume = request.POST.get('nume_uscator').strip()
            if nume:
                Uscator.objects.create(camin=camin, nume=nume, activa=True)
                messages.success(request, f"Uscătorul '{nume}' a fost adăugat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # Ștergere uscător
        if 'sterge_uscator_id' in request.POST:
            uscator = get_object_or_404(Uscator, id=request.POST['sterge_uscator_id'])
            uscator.delete()
            messages.success(request, f"Uscătorul '{uscator.nume}' a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # Toggle activare/dezactivare uscător
        if 'toggle_uscator_id' in request.POST:
            uscator = get_object_or_404(Uscator, id=request.POST['toggle_uscator_id'])
            uscator.activa = not uscator.activa
            uscator.save()
            messages.success(request, f"Statusul uscătorului '{uscator.nume}' a fost modificat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # Editare nume uscător
        if 'edit_uscator_id' in request.POST and 'nume_uscator_nou' in request.POST:
            uscator = get_object_or_404(Uscator, id=request.POST['edit_uscator_id'])
            nume_nou = request.POST.get('nume_uscator_nou').strip()
            if nume_nou:
                uscator.nume = nume_nou
                uscator.save()
                messages.success(request, f"Numele uscătorului a fost actualizat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)
        # Adaugă program mașină
        if 'adauga_program_masina' in request.POST:
            masina_id = request.POST.get('masina_id')
            ora_start = request.POST.get('ora_start_masina')
            ora_end = request.POST.get('ora_end_masina')
            masina = get_object_or_404(Masina, id=masina_id)
            ProgramMasina.objects.create(masina=masina, ora_start=ora_start, ora_end=ora_end)
            messages.success(request, "Programul mașinii a fost adăugat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

# Adaugă program uscător
        if 'adauga_program_uscator' in request.POST:
            uscator_id = request.POST.get('uscator_id')
            ora_start = request.POST.get('ora_start_uscator')
            ora_end = request.POST.get('ora_end_uscator')
            uscator = get_object_or_404(Uscator, id=uscator_id)
            ProgramUscator.objects.create(uscator=uscator, ora_start=ora_start, ora_end=ora_end)
            messages.success(request, "Programul uscătorului a fost adăugat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

# Șterge program mașină
        if 'sterge_program_masina_id' in request.POST:
            program_id = request.POST.get('sterge_program_masina_id')
            program = get_object_or_404(ProgramMasina, id=program_id)
            program.delete()
            messages.success(request, "Programul mașinii a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

# Șterge program uscător
        if 'sterge_program_uscator_id' in request.POST:
            program_id = request.POST.get('sterge_program_uscator_id')
            program = get_object_or_404(ProgramUscator, id=program_id)
            program.delete()
            messages.success(request, "Programul uscătorului a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)
        
        # Adaugă program pentru mașină
        if 'program_masina_id' in request.POST:
            masina_id = request.POST.get('program_masina_id')
            ora_start = request.POST.get('ora_start_masina')
            ora_end = request.POST.get('ora_end_masina')

            masina = get_object_or_404(Masina, id=masina_id)
            ProgramMasina.objects.create(masina=masina, ora_start=ora_start, ora_end=ora_end)
            messages.success(request, "Programul pentru mașină a fost adăugat.")
            return redirect('detalii_camin_admin', camin_id=camin_id)
        # Adaugă program pentru uscător
        if 'program_uscator_id' in request.POST:
            uscator_id = request.POST.get('program_uscator_id')
            ora_start = request.POST.get('ora_start_uscator')
            ora_end = request.POST.get('ora_end_uscator')
            uscator = get_object_or_404(Uscator, id=uscator_id)
            ProgramUscator.objects.create(uscator=uscator, ora_start=ora_start, ora_end=ora_end)
            messages.success(request, "Programul pentru uscător a fost adăugat.")
            return redirect('detalii_camin_admin', camin_id=camin_id)



    # Preluare date pentru afișare
    admini = AdminCamin.objects.filter(camin=camin)
    masini = Masina.objects.filter(camin=camin)
    uscatoare = Uscator.objects.filter(camin=camin)
    programe_masini = ProgramMasina.objects.filter(masina__camin=camin)
    programe_uscatoare = ProgramUscator.objects.filter(uscator__camin=camin)

    return render(request, 'dashboard/admin_camin/detalii_camin.html', {
        'camin': camin,
        'admini': admini,
        'masini': masini,
        'uscatoare': uscatoare,
        'programe_masini': programe_masini,
        'programe_uscatoare': programe_uscatoare,
    })


# =========================
# Rezervarea masinilor
# =========================
@login_required
def calendar_rezervari_view(request):
    user = request.user
    este_admin_camin = False
    este_student = False

    # verificăm dacă userul e admin cămin (căutăm după email)
    admin_camin = AdminCamin.objects.filter(email=user.email).first()

    if admin_camin:
        camin = admin_camin.camin
        masini = Masina.objects.filter(camin=camin, activa=True)
        nume_camin = camin.nume
        este_admin_camin = True
    else:
        # dacă nu e admin, verificăm dacă e student
        try:
            profil = ProfilStudent.objects.get(utilizator=user)
            camin = profil.camin
            masini = Masina.objects.filter(camin=camin, activa=True)
            nume_camin = camin.nume if camin else "Cămin necunoscut"
            este_student = True
        except ProfilStudent.DoesNotExist:
            masini = []
            nume_camin = "Cămin necunoscut"

    # DEBUG
    print(f"DEBUG: este_admin_camin={este_admin_camin}, este_student={este_student}")
    print(f"MASINI: {masini}")

    # index săptămână din query string
    try:
        index_saptamana = int(request.GET.get('saptamana', 0))
    except ValueError:
        index_saptamana = 0

    azi = date.today()
    start_saptamana = azi - timedelta(days=azi.weekday()) + timedelta(weeks=index_saptamana)
    end_saptamana = start_saptamana + timedelta(days=6)
    zile_saptamana = [start_saptamana + timedelta(days=i) for i in range(7)]
    intervale_ore = list(range(8, 22, 2))

    # Rezervări active pentru săptămână
    rezervari = Rezervare.objects.filter(
        masina__in=masini,
        data_rezervare__range=(start_saptamana, end_saptamana),
        anulata=False
    )

    # Dicționar rezervări
    rezervari_dict = {
        masina.id: {zi: {} for zi in zile_saptamana}
        for masina in masini
    }

    for r in rezervari:
        start_hour = r.ora_start.hour
        r.avertizat = Avertisment.objects.filter(utilizator=r.utilizator, data__gte=r.data_rezervare).exists()
        rezervari_dict[r.masina.id][r.data_rezervare][start_hour] = r

    print(f"REZERVARI_DICT: {rezervari_dict}")

    # Verificare blocare
    este_blocat = Avertisment.este_blocat(user)

    context = {
        'masini': masini,
        'zile_saptamana': zile_saptamana,
        'intervale_ore': intervale_ore,
        'rezervari_dict': rezervari_dict,
        'start_saptamana': start_saptamana,
        'end_saptamana': end_saptamana,
        'saptamana_index': index_saptamana,
        'saptamana_precedenta': index_saptamana - 1,
        'saptamana_urmatoare': index_saptamana + 1,
        'today': azi,
        'este_admin_camin': este_admin_camin,
        'este_student': este_student,
        'este_blocat': este_blocat,
        'nume_camin': nume_camin,
    }
    return render(request, 'dashboard/student/calendar_orar.html', context)


from django.core.mail import send_mail

@login_required
def creeaza_rezervare(request):
    if request.method == 'POST':
        user = request.user
        masina_id = request.POST.get('masina_id')
        data_str = request.POST.get('data')
        ora_start_str = request.POST.get('ora_start')
        ora_end_str = request.POST.get('ora_end')

        try:
            masina = Masina.objects.get(id=masina_id)
        except Masina.DoesNotExist:
            messages.error(request, "Mașina selectată nu există.")
            return redirect('calendar_rezervari')

        try:
            data_rezervare = datetime.strptime(data_str, '%Y-%m-%d').date()
            ora_start = datetime.strptime(ora_start_str, '%H:%M').time()
            ora_end = datetime.strptime(ora_end_str, '%H:%M').time()
        except ValueError:
            messages.error(request, "Format invalid pentru dată sau oră.")
            return redirect('calendar_rezervari')

        # Verificare dacă utilizatorul este blocat
        if Avertisment.objects.filter(utilizator=user, data__gte=date.today() - timedelta(days=30)).count() >= 2:
            messages.error(request, "Ai fost blocat(ă) temporar din cauza a 2 avertismente.")
            return redirect('calendar_rezervari')

        # Verificăm rezervările existente în acea săptămână
        start_sapt = data_rezervare - timedelta(days=data_rezervare.weekday())
        end_sapt = start_sapt + timedelta(days=6)

        rezervari_sapt = Rezervare.objects.filter(
            utilizator=user,
            data_rezervare__range=(start_sapt, end_sapt),
            anulata=False
        )

        nr_prioritare = rezervari_sapt.filter(prioritara=True).count()
        nr_fara_prioritate = rezervari_sapt.filter(prioritara=False).count()

        # Determinăm tipul rezervării
        if nr_prioritare < 2:
            prioritara = True
        elif nr_fara_prioritate < 3:
            prioritara = False
        else:
            messages.error(request, "Ai atins limita de rezervări pentru această săptămână.")
            return redirect('calendar_rezervari')

        # Căutăm dacă există deja o rezervare pe acel interval
        rezervari_existente = Rezervare.objects.filter(
            masina=masina,
            data_rezervare=data_rezervare,
            ora_start__lt=ora_end,
            ora_end__gt=ora_start,
            anulata=False
        )

        for rez in rezervari_existente:
            if rez.prioritara:
                # Intervalul e ocupat cu o rezervare prioritara, nu putem continua
                messages.error(request, "Intervalul este ocupat cu o rezervare prioritara.")
                return redirect('calendar_rezervari')
            else:
                # Anulăm rezervarea fără prioritate
                rez.anulata = True
                rez.save()

                # Trimitem email studentului afectat
                email_afectat = rez.utilizator.email
                send_mail(
                    'Rezervarea ta a fost anulată',
                    f'Rezervarea ta de la {rez.ora_start.strftime("%H:%M")} la {rez.ora_end.strftime("%H:%M")} din data de {rez.data_rezervare.strftime("%d.%m.%Y")} a fost anulată pentru a face loc unui student cu prioritate.',
                    'noreply@spalatorie.tuiasi.ro',
                    [email_afectat],
                    fail_silently=True
                )

        # Creăm rezervarea nouă
        Rezervare.objects.create(
            utilizator=user,
            masina=masina,
            data_rezervare=data_rezervare,
            ora_start=ora_start,
            ora_end=ora_end,
            prioritara=prioritara
        )

        messages.success(request, "Rezervarea a fost creată cu succes.")
        return redirect('calendar_rezervari')

    return redirect('calendar_rezervari')

@login_required
def programari_student_view(request):
    user = request.user
    azi = date.today()
    sapte_zile_in_urma = azi - timedelta(days=7)

    toate_rezervarile = Rezervare.objects.filter(utilizator=user, anulata=False)

    rezervari_urmatoare = toate_rezervarile.filter(data_rezervare__gte=azi).order_by('data_rezervare', 'ora_start')
    rezervari_incheiate = toate_rezervarile.filter(data_rezervare__lt=azi, data_rezervare__gte=sapte_zile_in_urma).order_by('-data_rezervare')

    context = {
        "rezervari_urmatoare": rezervari_urmatoare,
        "rezervari_incheiate": rezervari_incheiate,
    }
    return render(request, "dashboard/student/programari_student.html", context)




@login_required
def anuleaza_rezervare(request, rezervare_id):
    rezervare = get_object_or_404(Rezervare, id=rezervare_id, utilizator=request.user)

    if rezervare.data_rezervare < date.today():
        messages.error(request, "Nu poți anula o rezervare trecută.")
        return redirect('calendar_rezervari')

    rezervare.anulata = True
    rezervare.save()

    messages.success(request, "Rezervarea a fost anulată.")
    return redirect('calendar_rezervari')


def adauga_avertisment_din_calendar(request):
    if request.method == 'POST' and request.user.is_authenticated:
        rezervare_id = request.POST.get('rezervare_id')
        try:
            rezervare = Rezervare.objects.get(id=rezervare_id)
            # Verificăm dacă avertismentul nu a fost deja dat pentru această rezervare
            exista = Avertisment.objects.filter(utilizator=rezervare.utilizator, data=date.today()).exists()
            if not exista:
                Avertisment.objects.create(utilizator=rezervare.utilizator, motiv="Comportament necorespunzător (rezervare neutilizată)")
                messages.success(request, "Avertisment trimis cu succes.")
            else:
                messages.warning(request, "Ai trimis deja un avertisment astăzi.")
        except Rezervare.DoesNotExist:
            messages.error(request, "Rezervarea nu a fost găsită.")
    return redirect('calendar_rezervari')


@login_required
def calendar_rezervari_admin_view(request):
    return calendar_rezervari_view(request)  # folosim același view

@login_required
def programari_admin_camin_view(request):
    return programari_student_view(request)  # folosim același view



@login_required
def incarca_studenti_view(request):
    email = request.user.email
    try:
        admin = AdminCamin.objects.get(email=email)
    except AdminCamin.DoesNotExist:
        messages.error(request, "Acces interzis.")
        return redirect('home')

    camin = admin.camin
    studenti = ProfilStudent.objects.filter(camin=camin).select_related('utilizator')

    if request.method == 'POST' and request.FILES.get('fisier'):
        fisier = request.FILES['fisier']
        path = default_storage.save(f"temp/{fisier.name}", fisier)

        try:
            df = pd.read_excel(default_storage.path(path))
            df.columns = df.columns.str.strip().str.lower()

            required_cols = ['email', 'nume', 'prenume', 'camin', 'camera']
            for col in required_cols:
                if col not in df.columns:
                    raise ValueError(f"Coloana lipsă: {col}")

            # Șterge doar studenții din căminul adminului
            user_ids = studenti.values_list('utilizator__id', flat=True)
            User.objects.filter(id__in=user_ids).delete()

            for _, row in df.iterrows():
                email = str(row['email']).strip().lower()
                nume = str(row['nume']).strip().title()
                prenume = str(row['prenume']).strip().title()
                camera = str(row['camera']).strip()

                user, _ = User.objects.get_or_create(username=email, email=email, defaults={
                    'first_name': prenume,
                    'last_name': nume,
                })

                ProfilStudent.objects.update_or_create(
                    utilizator=user,
                    defaults={'camin': camin, 'numar_camera': camera}
                )

            messages.success(request, f"Lista de studenți din {camin.nume} a fost importată cu succes.")
            return redirect('incarca_studenti')

        except Exception as e:
            messages.error(request, f"Eroare la procesare: {e}")

    return render(request, 'dashboard/admin_camin/incarca_studenti.html', {
        'studenti': studenti,
        'camin': camin
    })

def adauga_student_view(request):
    email = request.session.get('email')
    admin = AdminCamin.objects.get(email=email)
    camin = admin.camin

    if request.method == 'POST':
        email = request.POST.get('email').strip().lower()
        nume = request.POST.get('nume').strip().title()
        prenume = request.POST.get('prenume').strip().title()
        camera = request.POST.get('camera').strip()

        user, _ = User.objects.get_or_create(
            username=email,
            email=email,
            defaults={
                'first_name': prenume,  # prenume = first_name
                'last_name': nume       # nume = last_name
            }
        )

        ProfilStudent.objects.update_or_create(
            utilizator=user,
            defaults={'camin': camin, 'numar_camera': camera}
        )
        messages.success(request, "Student adăugat cu succes.")
        return redirect('incarca_studenti')

    return render(request, 'dashboard/admin_camin/adauga_student.html', {'camin': camin})



def sterge_student_view(request, student_id):
    student = get_object_or_404(ProfilStudent, id=student_id)
    user = student.utilizator
    student.delete()
    user.delete()
    messages.success(request, "Studentul a fost șters.")
    return redirect('incarca_studenti')


def sterge_toti_studentii_view(request):
    email = request.session.get('email')
    admin = AdminCamin.objects.get(email=email)
    camin = admin.camin
    studenti = ProfilStudent.objects.filter(camin=camin)

    user_ids = studenti.values_list('utilizator__id', flat=True)
    studenti.delete()
    User.objects.filter(id__in=user_ids).delete()
    messages.success(request, f"Toți studenții din {camin.nume} au fost șterși.")
    return redirect('incarca_studenti')
