import json
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
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.utils.timezone import now
from allauth.socialaccount import providers
from allauth.socialaccount.providers.google.views import oauth2_login
from allauth.socialaccount.models import SocialApp
from django.http import HttpRequest
from django.contrib.sites.models import Site
import pandas as pd
from django.core.files.storage import default_storage
from django.core.cache import cache



# =========================
# Pagina Home
# =========================


def home(request):
    return render(request, 'home.html')

# =========================
# Callback după autentificare Google
# =========================





from allauth.socialaccount.models import SocialAccount

@login_required
def callback(request):
    user = request.user
    email = user.email

    request.session['email'] = email

    # Verifică dacă e admin de cămin
    if AdminCamin.objects.filter(email=email).exists():
        request.session['rol'] = 'admin_camin'
        return redirect('dashboard_admin_camin')

    # Verifică dacă e student
    elif ProfilStudent.objects.filter(utilizator=user).exists():
        request.session['rol'] = 'student'
        return redirect('dashboard_student')
    
    # Verifică dacă există deja un cont cu acest email
    elif User.objects.filter(email=email).exists():
        # Conectează contul Google cu utilizatorul existent
        try:
            social_account = SocialAccount.objects.create(user=user, provider='google', uid=email)
            print(f"Cont Google conectat cu utilizatorul existent: {user.username}")
            request.session['rol'] = 'student'
            return redirect('dashboard_student')
        except Exception as e:
            print(f"Eroare la conectarea contului Google: {e}")
            return render(request, 'not_allowed.html', {'message': 'A apărut o eroare la conectarea contului Google. Contactați administratorul.'})

    # Dacă nu e nici în baza de date, creează profilul studentului
    elif email.endswith('@student.tuiasi.ro'):
        # Extrage numele și prenumele din email
        email_parts = email.split('@')[0].split('.')
        if len(email_parts) >= 2:
            nume_email = email_parts[-1].replace('-', ' ').title()
            prenume_email = email_parts[0].replace('-', ' ').title()

            # Creează profilul studentului
            profil = ProfilStudent.objects.create(
                utilizator=user,
                camin=None,  # Setează căminul la None sau la o valoare implicită
                email=email,
                nume=nume_email,
                prenume=prenume_email
            )
            request.session['rol'] = 'student'
            return redirect('dashboard_student')

    # Dacă nu are acces, arată pagina de acces interzis
    return render(request, 'not_allowed.html', {
        'message': 'Nu aveți acces la această aplicație. Contactați administratorul.'
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


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Camin, Masina, ProgramMasina, AdminCamin, ProfilStudent
from django.contrib.auth.models import User


@login_required
def detalii_camin_admin(request, camin_id):
    camin = get_object_or_404(Camin, id=camin_id)

    if request.method == 'POST':
        if 'email_nou_admin' in request.POST:
            email_nou = request.POST.get('email_nou_admin').strip().lower()
            if email_nou:
                if not AdminCamin.objects.filter(camin=camin, email=email_nou).exists():
                    AdminCamin.objects.create(camin=camin, email=email_nou)
                    messages.success(request, f"Adminul '{email_nou}' a fost adăugat cu succes.")
                else:
                    messages.warning(request, f"'{email_nou}' este deja admin la cămin.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'sterge_admin_id' in request.POST:
            admin_id = request.POST.get('sterge_admin_id')
            admin = get_object_or_404(AdminCamin, id=admin_id)
            admin.delete()
            messages.success(request, f"Adminul '{admin.email}' a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'nume_masina' in request.POST:
            nume = request.POST.get('nume_masina').strip()
            if nume:
                Masina.objects.create(camin=camin, nume=nume, activa=True)
                messages.success(request, f"Mașina '{nume}' a fost adăugată.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'sterge_masina_id' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['sterge_masina_id'])
            masina.delete()
            messages.success(request, f"Mașina '{masina.nume}' a fost ștearsă.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'toggle_masina_id' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['toggle_masina_id'])
            masina.activa = not masina.activa
            masina.save()
            messages.success(request, f"Statusul mașinii '{masina.nume}' a fost modificat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'edit_masina_id' in request.POST and 'nume_masina_nou' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['edit_masina_id'])
            nume_nou = request.POST.get('nume_masina_nou').strip()
            if nume_nou:
                masina.nume = nume_nou
                masina.save()
                messages.success(request, f"Numele mașinii a fost actualizat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'nume_uscator' in request.POST:
            nume = request.POST.get('nume_uscator').strip()
            if nume:
                Uscator.objects.create(camin=camin, nume=nume, activa=True)
                messages.success(request, f"Uscătorul '{nume}' a fost adăugat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'sterge_uscator_id' in request.POST:
            uscator = get_object_or_404(Uscator, id=request.POST['sterge_uscator_id'])
            uscator.delete()
            messages.success(request, f"Uscătorul '{uscator.nume}' a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'toggle_uscator_id' in request.POST:
            uscator = get_object_or_404(Uscator, id=request.POST['toggle_uscator_id'])
            uscator.activa = not uscator.activa
            uscator.save()
            messages.success(request, f"Statusul uscătorului '{uscator.nume}' a fost modificat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'edit_uscator_id' in request.POST and 'nume_uscator_nou' in request.POST:
            uscator = get_object_or_404(Uscator, id=request.POST['edit_uscator_id'])
            nume_nou = request.POST.get('nume_uscator_nou').strip()
            if nume_nou:
                uscator.nume = nume_nou
                uscator.save()
                messages.success(request, f"Numele uscătorului a fost actualizat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'adauga_program_masina' in request.POST or 'program_masina_id' in request.POST:
            masina_id = request.POST.get('program_masina_id')
            ora_start = request.POST.get('ora_start_masina')
            ora_end = request.POST.get('ora_end_masina')
            masina = get_object_or_404(Masina, id=masina_id)
            ProgramMasina.objects.create(masina=masina, ora_start=ora_start, ora_end=ora_end)
            messages.success(request, "Programul mașinii a fost adăugat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'adauga_program_uscator' in request.POST or 'program_uscator_id' in request.POST:
            uscator_id = request.POST.get('program_uscator_id')
            ora_start = request.POST.get('ora_start_uscator')
            ora_end = request.POST.get('ora_end_uscator')
            uscator = get_object_or_404(Uscator, id=uscator_id)
            ProgramUscator.objects.create(uscator=uscator, ora_start=ora_start, ora_end=ora_end)
            messages.success(request, "Programul uscătorului a fost adăugat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'sterge_program_masina_id' in request.POST:
            program_id = request.POST.get('sterge_program_masina_id')
            program = get_object_or_404(ProgramMasina, id=program_id)
            program.delete()
            messages.success(request, "Programul mașinii a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'sterge_program_uscator_id' in request.POST:
            program_id = request.POST.get('sterge_program_uscator_id')
            program = get_object_or_404(ProgramUscator, id=program_id)
            program.delete()
            messages.success(request, "Programul uscătorului a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

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

    # Verifică dacă e admin cămin
    admin_camin = AdminCamin.objects.filter(email=user.email).first()

    if admin_camin:
        camin = admin_camin.camin
        masini = Masina.objects.filter(camin=camin, activa=True)
        nume_camin = camin.nume
        este_admin_camin = True
    else:
        # Verifică dacă e student
        if user.email.endswith('@student.tuiasi.ro'):
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
                este_student = True
                camin = student.camin
                if camin:
                    masini = Masina.objects.filter(camin=camin, activa=True)
                    nume_camin = camin.nume
                    
                    # Actualizează email-ul studentului dacă e diferit
                    if student.utilizator.email != user.email:
                        student.utilizator.email = user.email
                        student.utilizator.username = user.email
                        student.utilizator.save()
                else:
                    masini = []
                    nume_camin = "Cămin necunoscut"
            else:
                masini = []
                nume_camin = "Cămin necunoscut"
        else:
            masini = []
            nume_camin = "Cămin necunoscut"

    # DEBUG
    print(f"DEBUG: este_admin_camin={este_admin_camin}, este_student={este_student}")
    print(f"DEBUG: user_email={user.email}")
    if 'student' in locals():
        print(f"DEBUG: student_found={student is not None}")
        if student:
            print(f"DEBUG: student_camin={student.camin}")
    print(f"MASINI: {masini}")

    # Restul codului rămâne la fel
    try:
        index_saptamana = int(request.GET.get('saptamana', 0))
    except ValueError:
        index_saptamana = 0

    azi = date.today()
    start_saptamana = azi - timedelta(days=azi.weekday()) + timedelta(weeks=index_saptamana)
    end_saptamana = start_saptamana + timedelta(days=6)
    zile_saptamana = [start_saptamana + timedelta(days=i) for i in range(7)]
    intervale_ore = list(range(8, 22, 2))

    rezervari = Rezervare.objects.filter(
        masina__in=masini,
        data_rezervare__range=(start_saptamana, end_saptamana),
        anulata=False
    )

    rezervari_dict = {
        masina.id: {zi: {} for zi in zile_saptamana}
        for masina in masini
    }

    for r in rezervari:
        start_hour = r.ora_start.hour
        r.avertizat = Avertisment.objects.filter(utilizator=r.utilizator, data__gte=r.data_rezervare).exists()
        rezervari_dict[r.masina.id][r.data_rezervare][start_hour] = r

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
            data_rezervare = datetime.strptime(data_str, '%Y-%m-%d').date()
            ora_start = datetime.strptime(ora_start_str, '%H:%M').time()
            ora_end = datetime.strptime(ora_end_str, '%H:%M').time()
            
            azi = date.today()

            # Verificare dacă utilizatorul este blocat
            avertismente = Avertisment.objects.filter(
                utilizator=user,
                data__gte=azi - timedelta(days=7)
            ).count()
            
            if avertismente >= 3:
                messages.error(request, "Cont blocat temporar din cauza avertismentelor.")
                return redirect('calendar_rezervari')

            # Verificare dacă data este în trecut
            if data_rezervare < azi:
                messages.error(request, "Nu poți face rezervări pentru date din trecut.")
                return redirect('calendar_rezervari')

            # Verificăm dacă este săptămâna curentă sau viitoare
            saptamana_curenta = azi.isocalendar()[1]
            saptamana_rezervare = data_rezervare.isocalendar()[1]
            an_curent = azi.isocalendar()[0]
            an_rezervare = data_rezervare.isocalendar()[0]

            if an_rezervare < an_curent or (an_rezervare == an_curent and saptamana_rezervare < saptamana_curenta):
                messages.error(request, "Nu poți face rezervări pentru săptămânile trecute.")
                return redirect('calendar_rezervari')

            # Pentru săptămâna curentă - doar azi și mâine
            if saptamana_rezervare == saptamana_curenta:
                if data_rezervare > azi + timedelta(days=1):
                    messages.error(request, "În săptămâna curentă poți face rezervări doar pentru ziua curentă sau următoarea zi.")
                    return redirect('calendar_rezervari')
            elif saptamana_rezervare > saptamana_curenta + 4:
                messages.error(request, "Nu poți face rezervări cu mai mult de 4 săptămâni în avans.")
                return redirect('calendar_rezervari')

            # Verificăm rezervările din săptămâna rezervării
            start_sapt = data_rezervare - timedelta(days=data_rezervare.weekday())
            end_sapt = start_sapt + timedelta(days=6)
            
            rezervari_sapt = Rezervare.objects.filter(
                utilizator=user,
                data_rezervare__range=(start_sapt, end_sapt),
                anulata=False
            ).order_by('data_rezervare', 'ora_start')
            
            nr_rezervari = rezervari_sapt.count()

            # Pentru săptămâna curentă
            if saptamana_rezervare == saptamana_curenta:
                if nr_rezervari >= 4:
                    messages.error(request, "Ai atins numărul maxim de rezervări pentru această săptămână.")
                    return redirect('calendar_rezervari')
            else:
                # Pentru săptămânile viitoare - doar o rezervare permisă
                if nr_rezervari >= 1:
                    messages.error(request, "Poți face doar o rezervare pe săptămână pentru săptămânile viitoare.")
                    return redirect('calendar_rezervari')

            # Verificăm rezervările existente în intervalul dorit
            rezervari_existente = Rezervare.objects.filter(
                masina=masina,
                data_rezervare=data_rezervare,
                ora_start__lt=ora_end,
                ora_end__gt=ora_start,
                anulata=False
            )

            # Verificăm dacă putem prelua rezervarea existentă
            for rez in rezervari_existente:
                rezervari_alt_user = Rezervare.objects.filter(
                    utilizator=rez.utilizator,
                    data_rezervare__range=(start_sapt, end_sapt),
                    anulata=False
                ).order_by('data_rezervare', 'ora_start')

                if len(rezervari_sapt) < len(rezervari_alt_user):
                    # Anulăm rezervarea existentă
                    rez.anulata = True
                    rez.save()

                    # Trimitem email utilizatorului afectat
                    try:
                        subject = 'Rezervarea ta a fost preluată'
                        message = f'''
                        Salut,

                        Rezervarea ta pentru data de {data_rezervare} între orele {ora_start}-{ora_end} 
                        la mașina {masina.nume} a fost preluată de către un alt student care avea prioritate mai mare.

                        Te rugăm să faci o nouă rezervare pentru alt interval disponibil.

                        Cu stimă,
                        Sistemul de rezervări - Spălătorie T5
                        '''
                        
                        send_mail(
                            subject=subject,
                            message=message,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[rez.utilizator.email],
                            fail_silently=True
                        )
                    except Exception as e:
                        print(f"Eroare la trimiterea emailului: {str(e)}")
                    break

                elif rez.nivel_prioritate <= nr_rezervari + 1:
                    messages.error(request, "Nu poți prelua această rezervare deoarece are prioritate mai mare sau egală.")
                    return redirect('calendar_rezervari')
                else:
                    # Anulăm rezervarea cu prioritate mai mică
                    rez.anulata = True
                    rez.save()
                    
                    # Trimitem email utilizatorului afectat
                    try:
                        subject = 'Rezervarea ta a fost anulată'
                        message = f'''
                        Salut,

                        Rezervarea ta pentru data de {data_rezervare} între orele {ora_start}-{ora_end} 
                        la mașina {masina.nume} a fost anulată deoarece un student cu prioritate mai mare a făcut o rezervare.

                        Te rugăm să faci o nouă rezervare pentru alt interval disponibil.

                        Cu stimă,
                        Sistemul de rezervări - Spălătorie T5
                        '''
                        
                        send_mail(
                            subject=subject,
                            message=message,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[rez.utilizator.email],
                            fail_silently=True
                        )
                    except Exception as e:
                        print(f"Eroare la trimiterea emailului: {str(e)}")
                    break

            # Creăm rezervarea nouă
            rezervare = Rezervare.objects.create(
                utilizator=user,
                masina=masina,
                data_rezervare=data_rezervare,
                ora_start=ora_start,
                ora_end=ora_end,
                nivel_prioritate=1  # temporar
            )

            # Actualizăm prioritățile pentru toate rezervările din săptămână
            rezervari_actualizare = Rezervare.objects.filter(
                utilizator=user,
                data_rezervare__range=(start_sapt, end_sapt),
                anulata=False
            ).order_by('data_rezervare', 'ora_start')

            for index, rez in enumerate(rezervari_actualizare, 1):
                rez.nivel_prioritate = index
                rez.save()

            messages.success(request, "Rezervare creată cu succes!")
            return redirect('calendar_rezervari')

        except Exception as e:
            messages.error(request, f"Eroare la creare rezervare: {str(e)}")

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

    # Actualizăm prioritățile pentru rezervările rămase
    Rezervare.actualizeaza_prioritati(request.user, rezervare.data_rezervare)

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

















from django.contrib.auth.decorators import login_required

from django.db import transaction, close_old_connections
from django.views.decorators.http import require_POST

@login_required
def incarca_studenti_view(request):
    # Închide conexiunile vechi la început
    close_old_connections()
    
    studenti_importati = []
    admin = AdminCamin.objects.get(email=request.user.email)
    camin = admin.camin
    camine = Camin.objects.all()

    if request.method == 'POST' and request.FILES.get('fisier'):
        fisier = request.FILES['fisier']
        path = default_storage.save(f"temp/{fisier.name}", fisier)

        try:
            # Verifică formatul fișierului
            if not path.endswith('.xlsx') and not path.endswith('.xls'):
                messages.error(request, "Fișierul trebuie să fie în format Excel (.xlsx sau .xls).")
                return redirect('incarca_studenti')

            # Încărcă datele din Excel
            df = pd.read_excel(default_storage.path(path))
            
            # Verificări preliminare
            if df.empty:
                raise ValueError("Fișierul este gol sau nu conține date valide.")
            
            df.columns = df.columns.str.strip().str.lower()
            required_cols = ['email', 'nume', 'prenume', 'camin', 'camera']
            
            if not all(col in df.columns for col in required_cols):
                raise ValueError("Fișierul trebuie să conțină coloanele: email, nume, prenume, camin, camera.")

            # Folosește o tranzacție pentru toate operațiunile pe baza de date
            with transaction.atomic():
                # Șterge studenții existenți (exceptând userul logat)
                ProfilStudent.objects.exclude(utilizator=request.user).delete()
                User.objects.exclude(id=request.user.id).filter(is_superuser=False).delete()

                # Procesează fiecare rând
                for _, row in df.iterrows():
                    email = str(row['email']).strip().lower()
                    nume = str(row['nume']).strip().title()
                    prenume = str(row['prenume']).strip().title()
                    camin_nume = str(row['camin']).strip().upper()
                    camera = str(row['camera']).strip()

                    # Creează sau actualizează căminul
                    camin, _ = Camin.objects.get_or_create(nume=camin_nume)
                    
                    # Actualizează sau creează utilizatorul
                    user, created = User.objects.update_or_create(
                        username=email,
                        defaults={
                            'email': email,
                            'first_name': prenume,
                            'last_name': nume,
                        }
                    )

                    # Actualizează sau creează profilul studentului
                    profil, _ = ProfilStudent.objects.update_or_create(
                        utilizator=user,
                        defaults={
                            'camin': camin,
                            'numar_camera': camera,
                            'email': email,  # Asigură-te că salvezi email-ul și în ProfilStudent
                            'nume': nume,    # Asigură-te că salvezi numele și prenumele
                            'prenume': prenume
                        }
                    )

                    studenti_importati.append({
                        'email': email,
                        'nume': nume,
                        'prenume': prenume,
                        'camin': camin_nume,
                        'camera': camera
                    })

            # Șterge fișierul temporar
            default_storage.delete(path)
            messages.success(request, "Lista de studenți a fost importată cu succes.")

        except Exception as e:
            messages.error(request, f"Eroare la procesare: {e}")
            if 'path' in locals():
                default_storage.delete(path)

    # Obține lista actualizată de studenți
    studenti = ProfilStudent.objects.filter(camin=camin)

    return render(request, 'dashboard/admin_camin/incarca_studenti.html', {
        'studenti_importati': studenti_importati,
        'camin': camin,
        'studenti': studenti,
        'camine': camine,  # Adaugă această linie
    })


@login_required
def adauga_student_view(request):


    admin = AdminCamin.objects.get(email=request.user.email)
    camin = admin.camin

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()  # Add default empty string
        # Verify that email is not empty
        if not email:
            messages.error(request, "Emailul este obligatoriu!")
            return redirect('adauga_student')
            
        nume = request.POST.get('nume', '').strip().title()
        prenume = request.POST.get('prenume', '').strip().title()
        camera = request.POST.get('camera', '').strip()
        

        try:
            # Create or get user first
            user, created = User.objects.get_or_create(
                username=email,
                defaults={
                    'email': email,
                    'first_name': prenume,
                    'last_name': nume
                }
            )
            
            # Then create or update the student profile
            profil, _ = ProfilStudent.objects.update_or_create(
                utilizator=user,
                defaults={
                    'email': email,
                    'camin': camin,
                    'numar_camera': camera,
                    'nume': nume,    # Asigură-te că salvezi numele și prenumele
                    'prenume': prenume
                }
            )
            
            messages.success(request, "Student adăugat cu succes.")
            return redirect('incarca_studenti')
            
        except Exception as e:
            messages.error(request, f"Eroare la adăugarea studentului: {str(e)}")
            return redirect('adauga_student')

    return render(request, 'dashboard/admin_camin/adauga_student.html', {'camin': camin})


@login_required
def sterge_student_view(request, student_id):
    student = get_object_or_404(ProfilStudent, id=student_id)
    user = student.utilizator
    student.delete()
    user.delete()
    messages.success(request, "Studentul a fost șters.")
    return redirect('incarca_studenti')


@login_required
def sterge_toti_studentii_view(request):

    admin = AdminCamin.objects.get(email=request.user.email)
    camin = admin.camin
    studenti = ProfilStudent.objects.filter(camin=camin)

    user_ids = studenti.values_list('utilizator__id', flat=True)
    studenti.delete()
    User.objects.filter(id__in=user_ids).delete()
    messages.success(request, f"Toți studenții din {camin.nume} au fost șterși.")
    return redirect('incarca_studenti')

@login_required
@require_POST
def update_student(request, student_id):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Autentificare necesară'})
    
    try:
        # Decodează datele JSON
        data = json.loads(request.body)
        
        # Găsește studentul
        student = ProfilStudent.objects.get(id=student_id)
        
        # Actualizează User
        user = student.utilizator
        user.email = data['email']
        user.username = data['email']  # Folosim email-ul ca username
        user.first_name = data['prenume']
        user.last_name = data['nume']
        user.save()
        
        # Actualizează ProfilStudent
        camin = Camin.objects.get(id=data['camin'])
        student.camin = camin
        student.numar_camera = data['camera']
        student.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Datele studentului au fost actualizate cu succes!'
        })
        
    except ProfilStudent.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Studentul nu a fost găsit.'
        })
    except Camin.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Căminul selectat nu există.'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Eroare la actualizare: {str(e)}'
        })
