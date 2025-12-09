import json
from datetime import datetime, timedelta, date
import re
import pandas as pd
from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db import transaction, close_old_connections
from django.views.decorators.http import require_POST
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from booking.models import (
    Camin, ProfilStudent, AdminCamin,
    Rezervare, ProgramMasina, Masina,
    Avertisment, Uscator, ProgramUscator



)

from booking.utils import trimite_sms
from booking.utils import get_camin_curent


import logging, traceback
from .utils import trimite_sms
logger = logging.getLogger(__name__)

from booking.models import (
    Camin, ProfilStudent, AdminCamin,
    Rezervare, ProgramMasina, Masina,
    Avertisment, Uscator, ProgramUscator,
    IntervalDezactivare   # 🟡 asigură-te că ai acest import
)
from datetime import datetime, timedelta, date, time
from django.db.models import Min, Max
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages

from booking.models import (
    Camin, ProfilStudent, AdminCamin,
    Masina, Rezervare, Avertisment,
    IntervalDezactivare, ProgramMasina
)
from booking.utils import get_camin_curent



# =========================
# Decoratori pentru roluri
# =========================

def only_students(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not ProfilStudent.objects.filter(utilizator=request.user).exists():
            return render(request, 'not_allowed.html', {'message': 'Acces permis doar studenților.'})
        return view_func(request, *args, **kwargs)
    return wrapper

def only_admins(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not AdminCamin.objects.filter(email=request.user.email).exists():
            return render(request, 'not_allowed.html', {'message': 'Acces permis doar administratorilor de cămin.'})
        return view_func(request, *args, **kwargs)
    return wrapper

def only_super_admins(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_super_admin(request.user):
            return render(request, 'not_allowed.html', {'message': 'Acces permis doar super-adminilor.'})
        return view_func(request, *args, **kwargs)
    return wrapper



def is_super_admin(user):
    admin = AdminCamin.objects.filter(email=user.email).first()
    # acceptăm și staff/superuser ca fallback, dacă folosești adminul Django
    return (admin and admin.is_super_admin) or getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)



def is_student(user):
    return ProfilStudent.objects.filter(utilizator=user).exists()

def is_admin(user):
    return AdminCamin.objects.filter(email=user.email).exists()

# =========================
# Pagina Home
# =========================
def home(request):
    return render(request, 'home.html')


# =========================
# Callback după autentificare Google
# =========================
@login_required
def callback(request):
    user = request.user
    email = user.email.lower()

    # 🟢 1. Verificăm dacă e admin de cămin
    if AdminCamin.objects.filter(email=email).exists():
        return redirect('dashboard_admin_camin')

    # 🟢 2. Verificăm dacă e student valid în baza de date
    profil = ProfilStudent.objects.filter(email=email).first()
    if profil:
        # dacă există profil, dar nu e legat de userul curent → îl reatașăm
        if profil.utilizator != user:
            profil.utilizator = user
            profil.save()
        return redirect('dashboard_student')

    # 🔴 3. Dacă nu e găsit în baza de date → NU îl creăm, doar blocăm accesul
    logout(request)
    return render(request, 'not_allowed.html', {
        'message': (
            f'Adresa <b>{email}</b> nu este înregistrată în sistem.<br>'
            'Te rugăm să contactezi administratorul  pentru a fi adăugat în baza de date:<br>'
            '<b>Marcu Elena – +40 756 752 311</b>'
        )
    })





# =========================
# Logout personalizat
# =========================
def custom_logout(request):
    logout(request)
    return redirect('account_login')


# =========================
# Dashboard-uri după rol
# =========================
from datetime import date, timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from booking.models import ProfilStudent, Rezervare

from datetime import date, timedelta
from booking.models import Rezervare, ProfilStudent, Avertisment

@login_required 
@only_students
def dashboard_student(request):
    profil = ProfilStudent.objects.filter(utilizator=request.user).first()
    if not profil:
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar studenților.'
        })

    profil.refresh_from_db()

    azi = date.today()
    maine = azi + timedelta(days=1)
    rezervare_activa = Rezervare.objects.filter(
        utilizator=request.user,
        data_rezervare__range=(azi, maine),
        anulata=False
    ).order_by('data_rezervare', 'ora_start').first()

    # 🔍 Număr avertismente în ultimele 30 de zile
    data_limita = azi - timedelta(days=30)
    avertismente_active = Avertisment.objects.filter(
        utilizator=request.user,
        data__gte=data_limita
    ).count()

    context = {
        'profil': profil,
        'rezervare_activa': rezervare_activa,
        'avertismente_active': avertismente_active,
    }

    return render(request, 'dashboard/student.html', context)



# =========================
# Dashboard Admin Cămin
# =========================
from datetime import date, timedelta
from booking.models import AdminCamin, Rezervare

@login_required
@only_admins
def dashboard_admin_camin(request):
    admin = AdminCamin.objects.filter(email=request.user.email).first()
    if not admin:
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar administratorilor de cămin.'
        })

    # 🔁 Reîncărcăm datele reale din DB (ca să nu fie cache vechi)
    admin.refresh_from_db()

    # 🔍 Căutăm rezervarea activă (azi sau mâine)
    azi = date.today()
    maine = azi + timedelta(days=1)
    rezervare_activa = Rezervare.objects.filter(
        utilizator=request.user,
        data_rezervare__range=(azi, maine),
        anulata=False
    ).order_by('data_rezervare', 'ora_start').first()

    context = {
        'admin': admin,
        'rezervare_activa': rezervare_activa,
    }

    return render(request, 'dashboard/admin_camin.html', context)




# =========================
# Admin cămin - Administrare cămine
# =========================



@login_required
@only_admins
def administrare_camin(request):
    if not is_super_admin(request.user):
        admin = AdminCamin.objects.filter(email=request.user.email).select_related("camin").first()
        if admin and admin.camin_id:
            return redirect('detalii_camin_admin', camin_id=admin.camin_id)
        return render(request, 'not_allowed.html', {'message': 'Nu ai acces la administrarea tuturor căminelor.'})

    camine = Camin.objects.all()
    return render(request, 'dashboard/admin_camin/administrare_camin.html', {
        'camine': camine,
        'is_super_admin': True,   # pt. template
    })

# =========================
# Admin cămin - Lista cămine
# =========================
@login_required
@only_admins
def lista_camine_admin(request):
    camine = Camin.objects.all()
    return render(request, 'dashboard/admin_camin/lista_camine.html', {'camine': camine})


@login_required
@only_super_admins
def adauga_camin_view(request):
    if request.method == 'POST':
        nume = request.POST.get('nume', '').strip().upper()
        if nume:
            Camin.objects.get_or_create(nume=nume)
            messages.success(request, 'Cămin adăugat cu succes!')
            return redirect('administrare_camin')
    return render(request, 'dashboard/admin_camin/adauga_camin.html')

@login_required
@only_super_admins
def sterge_camin_view(request, camin_id):
    camin = get_object_or_404(Camin, id=camin_id)
    if request.method == "POST":
        camin.delete()
        messages.success(request, f'Căminul "{camin.nume}" a fost șters.')
    return redirect('administrare_camin')

# =========================
# Admin cămin - Detalii cămin
# =========================
import logging, traceback
logger = logging.getLogger(__name__)


from booking.utils import trimite_whatsapp

            
@login_required
@only_admins
def detalii_camin_admin(request, camin_id):
    camin = get_object_or_404(Camin, id=camin_id)
    current_admin = AdminCamin.objects.filter(email=request.user.email).first()

    # ✅ 1. Verificăm drepturile
    # super-adminii văd tot, ceilalți doar căminul lor
    if not is_super_admin(request.user):
        if not current_admin or current_admin.camin_id != camin.id:
            return render(request, 'not_allowed.html', {
                'message': 'Nu ai acces la acest cămin.'
            })

    # ✅ 2. Blocăm modificările de admini pentru non-super-admini
    if request.method == 'POST':
        if 'email_nou_admin' in request.POST or 'sterge_admin_id' in request.POST:
            if not is_super_admin(request.user):
                messages.error(request, "Doar super-adminii pot modifica lista de administratori.")
                return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Adăugare admin
        if 'email_nou_admin' in request.POST:
            email_nou = request.POST.get('email_nou_admin', '').strip().lower()
            if email_nou:
                if not AdminCamin.objects.filter(camin=camin, email=email_nou).exists():
                    AdminCamin.objects.create(camin=camin, email=email_nou)
                    messages.success(request, f"Adminul '{email_nou}' a fost adăugat cu succes.")
                else:
                    messages.warning(request, f"'{email_nou}' este deja admin la acest cămin.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Ștergere admin
        if 'sterge_admin_id' in request.POST:
            admin_id = request.POST.get('sterge_admin_id')
            admin = get_object_or_404(AdminCamin, id=admin_id)
            admin.delete()
            messages.success(request, f"Adminul '{admin.email}' a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)
        

        # ✅ în detalii_camin_admin (sub alte if-uri din POST)
        if 'update_durata_interval' in request.POST:
            try:
                durata = int(request.POST.get('durata_interval', 2))
                camin.durata_interval = durata
                camin.save()
                messages.success(request, f"Durata intervalului a fost actualizată la {durata} ore.")
            except Exception as e:
                messages.error(request, f"Eroare la actualizarea duratei: {e}")
            return redirect('detalii_camin_admin', camin_id=camin.id)


        # ✅ Adăugare mașină
        if 'nume_masina' in request.POST:
            nume = request.POST.get('nume_masina', '').strip()
            if nume:
                Masina.objects.create(camin=camin, nume=nume, activa=True)
                messages.success(request, f"Mașina '{nume}' a fost adăugată.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Ștergere mașină
        if 'sterge_masina_id' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['sterge_masina_id'])
            masina.delete()
            messages.success(request, f"Mașina '{masina.nume}' a fost ștearsă.")
            return redirect('detalii_camin_admin', camin_id=camin.id)
        # ✅ Editare nume mașină
        if 'edit_masina_id' in request.POST:
            masina_id = request.POST.get('edit_masina_id')
            nume_nou = request.POST.get('nume_masina_nou', '').strip()
            masina = get_object_or_404(Masina, id=masina_id)
            if nume_nou:
                masina.nume = nume_nou
                masina.save()
                messages.success(request, f"Numele mașinii a fost actualizat la '{nume_nou}'.")
            else:
                messages.warning(request, "Numele nu poate fi gol.")
            return redirect('detalii_camin_admin', camin_id=camin.id)


        # ✅ Activare / Dezactivare completă mașină
        if 'toggle_masina_id' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['toggle_masina_id'])
            masina.activa = not masina.activa
            masina.save()

            if not masina.activa:
                rezervari_viitoare = Rezervare.objects.filter(
                    masina=masina,
                    data_rezervare__gte=date.today()
                ).exclude(anulata=True)

                numar_notificari = 0
                for rez in rezervari_viitoare:
                    try:
                        profil_vechi = ProfilStudent.objects.filter(utilizator=rez.utilizator).first()
                        if profil_vechi and profil_vechi.telefon:
                            trimite_whatsapp(
                                destinatar=profil_vechi.telefon,
                                template_name="dezactivare_masina_complet",
                                variabile={
                                    "2": rez.data_rezervare.strftime('%d %b %Y'),
                                    "3": rez.ora_start.strftime('%H:%M'),
                                    "4": rez.ora_end.strftime('%H:%M'),
                                    "1": rez.masina.nume,
                                }
                            )
                            numar_notificari += 1
                        rez.anulata = True
                        rez.save()
                    except Exception as e:
                        logger.error(f"Eroare trimitere WhatsApp la dezactivare mașină: {e}")

                messages.success(
                    request,
                    f"Mașina '{masina.nume}' a fost dezactivată complet. "
                    f"{numar_notificari} rezervări anulate și notificate."
                )
            else:
                messages.success(request, f"Mașina '{masina.nume}' a fost activată.")

            return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Dezactivare mașină pe interval ⏰
        if 'dezactiveaza_masina_id' in request.POST:
            masina_id = request.POST.get('dezactiveaza_masina_id')
            data_str = request.POST.get('data_dezactivare')
            ora_start_str = request.POST.get('ora_start_dezactivare')
            ora_end_str = request.POST.get('ora_end_dezactivare')

            try:
                masina = Masina.objects.get(id=masina_id)
                data_selectata = datetime.strptime(data_str, '%Y-%m-%d').date()
                ora_start = datetime.strptime(ora_start_str, '%H:%M').time()
                ora_end = datetime.strptime(ora_end_str, '%H:%M').time()

                rezervari_afectate = Rezervare.objects.filter(
                    masina=masina,
                    data_rezervare=data_selectata,
                    ora_start__lt=ora_end,
                    ora_end__gt=ora_start
                ).exclude(anulata=True)

                numar_notificari = 0
                for rez in rezervari_afectate:
                    try:
                        profil_vechi = ProfilStudent.objects.filter(utilizator=rez.utilizator).first()
                        if profil_vechi and profil_vechi.telefon:
                            trimite_whatsapp(
                                destinatar=profil_vechi.telefon,
                                template_name="dezactivare_masina_interval",
                                variabile={
                                    "2": rez.data_rezervare.strftime('%d %b %Y'),
                                    "3": rez.ora_start.strftime('%H:%M'),
                                    "4": rez.ora_end.strftime('%H:%M'),
                                    "1": rez.masina.nume,
                                }
                            )
                            numar_notificari += 1
                        rez.anulata = True
                        rez.save()
                    except Exception as e:
                        logger.error(f"Eroare trimitere WhatsApp la dezactivare interval: {e}")

                IntervalDezactivare.objects.create(
                    masina=masina,
                    data=data_selectata,
                    ora_start=ora_start,
                    ora_end=ora_end
                )

                messages.success(
                    request,
                    f"Mașina '{masina.nume}' a fost dezactivată pe {data_selectata.strftime('%d %b %Y')} "
                    f"între orele {ora_start.strftime('%H:%M')}–{ora_end.strftime('%H:%M')}. "
                    f"{numar_notificari} rezervări anulate și notificate."
                )

            except Exception as e:
                logger.error(f"Eroare la dezactivare mașină: {e}\n{traceback.format_exc()}")
                messages.error(request, f"Eroare la dezactivare: {e}")

            return redirect('detalii_camin_admin', camin_id=camin.id)
        
                # ✅ Adăugare program pentru mașină
        if 'adauga_program_masina' in request.POST:
            masina_id = request.POST.get('program_masina_id')
            ora_start_str = request.POST.get('ora_start_masina')
            ora_end_str = request.POST.get('ora_end_masina')

            try:
                masina = get_object_or_404(Masina, id=masina_id)

                if not ora_start_str or not ora_end_str:
                    messages.error(request, "Completează orele de început și sfârșit.")
                    return redirect('detalii_camin_admin', camin_id=camin.id)

                ora_start = datetime.strptime(ora_start_str, '%H:%M').time()
                ora_end = datetime.strptime(ora_end_str, '%H:%M').time()

                # Verificare dacă deja există un program similar
                exista = ProgramMasina.objects.filter(
                    masina=masina,
                    ora_start=ora_start,
                    ora_end=ora_end
                ).exists()

                if exista:
                    messages.warning(request, "Acest program există deja pentru mașină.")
                else:
                    ProgramMasina.objects.create(
                        masina=masina,
                        ora_start=ora_start,
                        ora_end=ora_end
                    )
                    messages.success(
                        request,
                        f"Program adăugat pentru {masina.nume}: {ora_start.strftime('%H:%M')} - {ora_end.strftime('%H:%M')}."
                    )

            except Exception as e:
                messages.error(request, f"Eroare la adăugarea programului: {e}")

            return redirect('detalii_camin_admin', camin_id=camin.id)
                # ✅ Ștergere program mașină
        if 'sterge_program_masina_id' in request.POST:
            prog_id = request.POST.get('sterge_program_masina_id')
            try:
                program = get_object_or_404(ProgramMasina, id=prog_id)
                program.delete()
                messages.success(request, "Programul a fost șters cu succes.")
            except Exception as e:
                messages.error(request, f"Eroare la ștergerea programului: {e}")
            return redirect('detalii_camin_admin', camin_id=camin.id)



    # ✅ Date pentru template
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
        'is_super_admin': is_super_admin(request.user),
    })

def genereaza_intervale(ora_start, ora_end, durata):
    """
    Generează intervale chiar dacă ora_end trece peste miezul nopții.
    Exemplu:
      ora_start = 7:00
      ora_end   = 01:00 (a doua zi)
    """
    start_minute = ora_start.hour * 60 + ora_start.minute
    end_minute = ora_end.hour * 60 + ora_end.minute

    # Dacă orele depășesc ziua (ex: 22 → 01)
    if end_minute <= start_minute:
        end_minute += 24 * 60  # trece în ziua următoare

    intervale = []
    current = start_minute

    while current < end_minute:
        intervale.append(current)
        current += durata * 60

    return intervale


# =========================
# Rezervarea mașinilor
# =========================
@login_required
def calendar_rezervari_view(request):
    user = request.user


    # verificăm dacă e student sau admin
    admin_camin = AdminCamin.objects.filter(email=user.email).first()
    student = ProfilStudent.objects.filter(utilizator=user).first()
    
    camin = get_camin_curent(request)

       # ✅ folosim căminul curent din funcția comună
    if not camin:
        return render(request, 'not_allowed.html', {
            'message': 'Nu ești asociat niciunui cămin sau nu ai selectat unul activ.'
        })

    # 🔹 determinăm automat rolul
    este_admin_camin = AdminCamin.objects.filter(email=user.email, camin=camin).exists()
    este_student = ProfilStudent.objects.filter(utilizator=user, camin=camin).exists()

    # 🔹 mașinile active din căminul curent
    masini = Masina.objects.filter(camin=camin, activa=True)
    nume_camin = camin.nume


    try:
        index_saptamana = int(request.GET.get('saptamana', 0))
    except ValueError:
        index_saptamana = 0

    azi = date.today()
    now = datetime.now()
    now_hour = timezone.localtime().hour  # ← folosim acest întreg în template


    start_saptamana = azi - timedelta(days=azi.weekday()) + timedelta(weeks=index_saptamana)
    end_saptamana = start_saptamana + timedelta(days=6)
    zile_saptamana = [start_saptamana + timedelta(days=i) for i in range(7)]


    # Găsim cel mai devreme început și cel mai târziu sfârșit al programului mașinilor din cămin
    program = ProgramMasina.objects.filter(masina__in=masini)

    ora_start_min = program.aggregate(Min("ora_start"))["ora_start__min"] or time(8, 0)
    ora_end_max  = program.aggregate(Max("ora_end"))["ora_end__max"]   or time(22, 0)
    raw_intervals = genereaza_intervale(ora_start_min, ora_end_max, camin.durata_interval)
    intervale_ore = []
    
    for minute in raw_intervals:
        ora_start = minute // 60
        ora_end = (ora_start + camin.durata_interval) % 24

        intervale_ore.append((ora_start, ora_end))




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
        r.avertizat = Avertisment.objects.filter(
            utilizator=r.utilizator,
            data__gte=r.data_rezervare
        ).exists()
        rezervari_dict[r.masina.id][r.data_rezervare][start_hour] = r

    profil = ProfilStudent.objects.filter(utilizator=user).first()
    este_blocat = profil.este_blocat() if profil else False

    intervale_blocate = IntervalDezactivare.objects.filter(
        masina__in=masini,
        data__range=(start_saptamana, end_saptamana)
    )

    # ✅ Aici adăugăm logica pentru afișarea numărului de telefon
    telefon = None
    if student and student.telefon:
        telefon = student.telefon
    elif admin_camin and admin_camin.telefon:
        telefon = admin_camin.telefon

    are_telefon = profil.telefon if profil else None


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
        'intervale_blocate': intervale_blocate,
        'telefon': telefon,  # 🟢 adăugat aici pentru bara din dreapta
        'now_hour': now_hour,
        'are_telefon': bool(profil and profil.telefon),
        'durata_interval': camin.durata_interval,

    }

    return render(request, 'dashboard/student/calendar_orar.html', context)









@login_required
def creeaza_rezervare(request):
    user = request.user
    saptamana = request.POST.get('saptamana', 0)

    # ✅ Verificare drepturi acces
    if not (AdminCamin.objects.filter(email=user.email).exists() or
            ProfilStudent.objects.filter(utilizator=user).exists()):
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar studenților sau administratorilor.'
        })
    
    camin = get_camin_curent(request)



    profil = ProfilStudent.objects.filter(utilizator=user).first()
    if profil and profil.suspendat_pana_la and profil.suspendat_pana_la >= date.today():
        messages.error(request, f"Contul tău este blocat până la {profil.suspendat_pana_la.strftime('%d %B %Y')}.")
        return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')
    
    if profil and not profil.telefon:
        messages.warning(request, "Trebuie să adaugi un număr de telefon înainte de a face o rezervare.")
        return redirect('adauga_telefon')


    if request.method == 'POST':
        masina_id = request.POST.get('masina_id')
        data_str = request.POST.get('data')
        ora_start_str = request.POST.get('ora_start')


        try:
            masina = Masina.objects.get(id=masina_id)
            data_rezervare = datetime.strptime(data_str, '%Y-%m-%d').date()
            ora_start = datetime.strptime(ora_start_str, '%H:%M').time()
            durata = timedelta(hours=camin.durata_interval)
            ora_end = (datetime.combine(date.today(), ora_start) + durata).time()
            azi = date.today()

            # 🟡 Verificăm dacă intervalul cerut este într-un interval dezactivat
            exista_blocaj = IntervalDezactivare.objects.filter(
                masina=masina,
                data=data_rezervare,
                ora_start__lt=ora_end,
                ora_end__gt=ora_start
            ).exists()

            if exista_blocaj:
                messages.error(request, "Mașina este dezactivată în intervalul selectat. Alege alt interval.")
                return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

            # ✅ Verificare avertismente recente
            avertismente = Avertisment.objects.filter(
                utilizator=user,
                data__gte=azi - timedelta(days=7)
            ).count()
            if avertismente >= 3:
                messages.error(request, "Cont blocat temporar din cauza avertismentelor.")
                return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

            # ✅ Verificări de date
            if data_rezervare < azi:
                messages.error(request, "Nu poți face rezervări pentru date din trecut.")
                return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

            sapt_curenta = azi.isocalendar()[1]
            sapt_rezervare = data_rezervare.isocalendar()[1]
            an_curent = azi.isocalendar()[0]
            an_rezervare = data_rezervare.isocalendar()[0]

            if an_rezervare < an_curent or (an_rezervare == an_curent and sapt_rezervare < sapt_curenta):
                messages.error(request, "Nu poți face rezervări pentru săptămânile trecute.")
                return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

            start_sapt = data_rezervare - timedelta(days=data_rezervare.weekday())
            end_sapt = start_sapt + timedelta(days=6)

            rezervari_sapt = Rezervare.objects.filter(
                utilizator=user,
                data_rezervare__range=(start_sapt, end_sapt),
                anulata=False
            ).order_by('data_rezervare', 'ora_start')

            nr_rezervari = rezervari_sapt.count()

            # 🔒 Restricții pe săptămână
            if sapt_rezervare == sapt_curenta:
                if nr_rezervari >= 1 and data_rezervare > azi + timedelta(days=1):
                    messages.error(request, "În săptămâna curentă doar prima rezervare poate fi făcută oricând, restul doar pentru azi și mâine.")
                    return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')
            elif sapt_rezervare > sapt_curenta + 4:
                messages.error(request, "Nu poți face rezervări cu mai mult de 4 săptămâni în avans.")
                return redirect('calendar_rezervari')

            if sapt_rezervare == sapt_curenta and nr_rezervari >= 4:
                messages.error(request, "Ai atins numărul maxim de rezervări pentru această săptămână.")
                return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')
            elif sapt_rezervare != sapt_curenta and nr_rezervari >= 1:
                messages.error(request, "Poți face doar o rezervare pe săptămână pentru săptămânile viitoare.")
                return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

            rezervari_existente = Rezervare.objects.filter(
                masina=masina,
                data_rezervare=data_rezervare,
                ora_start__lt=ora_end,
                ora_end__gt=ora_start,
                anulata=False
            )

            # 🔁 Logica de preluare rezervare existentă
            for rez in rezervari_existente:
                rezervari_alt_user = Rezervare.objects.filter(
                    utilizator=rez.utilizator,
                    data_rezervare__range=(start_sapt, end_sapt),
                    anulata=False
                )

                if rez.nivel_prioritate > nr_rezervari + 1:
                    rez.anulata = True
                    rez.save()

                    # 📲 Notificare — WhatsApp dacă are nr., altfel fallback
                    try:
                        profil_vechi = ProfilStudent.objects.filter(utilizator=rez.utilizator).first()
                        if profil_vechi and profil_vechi.telefon:
                            trimite_whatsapp(
                                destinatar=profil_vechi.telefon,
                                template_name="rezervare_preluata_student",
                                variabile={
                                    "1": rez.data_rezervare.strftime('%d %b %Y'),
                                    "2": rez.ora_start.strftime('%H:%M'),
                                    "3": rez.ora_end.strftime('%H:%M'),
                                    "4": rez.masina.nume,
                                    "5": rez.nivel_prioritate,
                                    "6": nr_rezervari + 1,
                                }
                            )
                            logger.info(f"✅ WhatsApp trimis către {profil_vechi.telefon}")
                        else:
                            logger.warning(f"Niciun număr de telefon pentru {rez.utilizator.email}")
                            # opțional fallback trimite_sms(...) sau email aici
                    except Exception as e:
                        logger.error(f"Eroare trimitere WhatsApp: {e}")

                    break
                else:
                    messages.error(request, "Nu poți prelua această rezervare (prioritate egală sau mai mică).")
                    return redirect(f"{reverse('calendar_rezervari')}?saptamana={saptamana}")

            # 🆕 Creăm rezervarea nouă
            rezervare = Rezervare.objects.create(
                utilizator=user,
                masina=masina,
                data_rezervare=data_rezervare,
                ora_start=ora_start,
                ora_end=ora_end,
                nivel_prioritate=1
            )

            # 🔄 Actualizăm prioritățile după creare
            rezervari_actualizare = Rezervare.objects.filter(
                utilizator=user,
                data_rezervare__range=(start_sapt, end_sapt),
                anulata=False
            ).order_by('data_rezervare', 'ora_start')

            for index, rez in enumerate(rezervari_actualizare, 1):
                rez.nivel_prioritate = index
                rez.save()

            messages.success(request, "Rezervare creată cu succes!")
            return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

        except Exception as e:
            logger.error(f"Eroare la creare rezervare: {e}\n{traceback.format_exc()}")
            messages.error(request, f"Eroare la creare rezervare: {e}")
            return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

    return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')






# =========================
# Programările utilizatorului (student/admin)
# =========================
@login_required
def programari_student_view(request):
    user = request.user

    if not (AdminCamin.objects.filter(email=user.email).exists() or 
            ProfilStudent.objects.filter(utilizator=user).exists()):
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar studenților sau administratorilor.'
        })

    azi = date.today()
    acum = datetime.now().time()

    toate = Rezervare.objects.filter(utilizator=user, anulata=False)

    # 🔥 1) Rezervările viitoare
    rezervari_urmatoare = toate.filter(
        Q(data_rezervare__gt=azi) |
        Q(data_rezervare=azi, ora_end__gt=acum)
    ).order_by('data_rezervare', 'ora_start')

    # 🔥 2) Rezervările încheiate
    rezervari_incheiate = toate.filter(
        Q(data_rezervare__lt=azi) |
        Q(data_rezervare=azi, ora_end__lte=acum)
    ).order_by('-data_rezervare')

    context = {
        "rezervari_urmatoare": rezervari_urmatoare,
        "rezervari_incheiate": rezervari_incheiate,
        "today": azi,
        "now_hour": acum,
    }
    return render(request, "dashboard/student/programari_student.html", context)



# =========================
# Anularea rezervării
# =========================

@login_required
@require_POST

def anuleaza_rezervare(request, rezervare_id): 
    user = request.user
    try:
        rezervare = Rezervare.objects.get(id=rezervare_id, utilizator=user)
    except Rezervare.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": "Rezervarea nu există sau nu îți aparține."}, status=404)
        messages.error(request, "Rezervarea nu există sau nu îți aparține.")
        return redirect('calendar_rezervari')

    # ❌ 1. Blocăm rezervările din zile trecute
    if rezervare.data_rezervare < date.today():
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": "Nu poți anula o rezervare trecută."}, status=400)
        messages.error(request, "Nu poți anula o rezervare trecută.")
        return redirect('calendar_rezervari')

    # ❌ 2. Blocăm rezervările de AZI care s-au terminat deja
    if rezervare.data_rezervare == date.today() and rezervare.ora_end <= datetime.now().time():
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": "Nu poți anula o rezervare care s-a încheiat deja."}, status=400)
        messages.error(request, "Nu poți anula o rezervare care s-a încheiat deja.")
        return redirect('calendar_rezervari')

    # ✅ Dacă trece de ambele verificări → poate fi anulată
    rezervare.anulata = True
    rezervare.save()
    Rezervare.actualizeaza_prioritati(user, rezervare.data_rezervare)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True})

    messages.success(request, "Rezervarea a fost anulată.")
    return redirect('calendar_rezervari')

 


# =========================
# Avertisment pentru rezervări neutilizate
# =========================
from django.utils import timezone
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404

@login_required
@only_admins
def adauga_avertisment_din_calendar(request):
    if request.method != 'POST':
        return redirect('calendar_rezervari_admin')

    rezervare_id = request.POST.get('rezervare_id')
    rezervare = get_object_or_404(Rezervare, id=rezervare_id)
    utilizator = rezervare.utilizator
    admin = AdminCamin.objects.filter(email=request.user.email).first()

    if not admin or rezervare.masina.camin_id != admin.camin_id:
        messages.error(request, "Nu poți trimite avertismente pentru alt cămin.")
        return redirect('calendar_rezervari_admin')

    azi = timezone.localdate()

    if Avertisment.objects.filter(utilizator=utilizator, data=azi).exists():
        messages.warning(request, "Ai trimis deja un avertisment acestui utilizator astăzi.")
        return redirect('calendar_rezervari_admin')

    Avertisment.objects.create(utilizator=utilizator, motiv="Rezervare neutilizată")

    avertismente_recente = Avertisment.objects.filter(
        utilizator=utilizator,
        data__gte=azi - timedelta(days=30)
    ).count()

    profil = ProfilStudent.objects.filter(utilizator=utilizator).first()
    data_blocare_pana = None

    if avertismente_recente >= 3 and profil:
        data_blocare_pana = azi + timedelta(days=7)
        profil.suspendat_pana_la = data_blocare_pana
        profil.save()

    # 🔥 Trimitere WhatsApp dacă studentul are număr
    if profil and profil.telefon:
        try:
            trimite_whatsapp(
                destinatar=profil.telefon,
                template_name="advertisment_rezervare",
                
                variabile={
                    "1": utilizator.get_full_name() or utilizator.username,
                    "2": rezervare.data_rezervare.strftime('%d %b %Y'),
                    "3": f"{rezervare.ora_start.strftime('%H:%M')}–{rezervare.ora_end.strftime('%H:%M')}",
                    "4": rezervare.masina.nume,
                }
            )
            messages.success(request, "Avertisment trimis și notificare WhatsApp către student.")
        except Exception as e:
            messages.warning(request, f"Avertisment creat, dar nu s-a putut trimite mesajul WhatsApp: {e}")
    else:
        messages.warning(request, "Avertisment trimis, dar studentul nu are număr de telefon.")

    return redirect('calendar_rezervari_admin')



# =========================
# Admin cămin - Calendar rezervări
# =========================
@login_required
@only_admins
def calendar_rezervari_admin_view(request):
    return calendar_rezervari_view(request)  # folosim același view

# =========================
# Admin cămin - Programări studenți
# =========================
@login_required
@only_admins
def programari_admin_camin_view(request):
    return programari_student_view(request)  # folosim același view


# =========================
# Admin cămin - Încărcare studenți din Excel
# =========================
@login_required
@only_admins
def incarca_studenti_view(request):
    user = request.user
    admin_camin = AdminCamin.objects.filter(email=user.email).first()

    # 🧱 Verifică dacă e admin înregistrat
    if not admin_camin:
        return render(request, 'not_allowed.html', {
            'message': 'Nu ai drepturi de administrator.'
        })

    # 🧱 Obține căminul selectat / curent
    camin = get_camin_curent(request)
    if not camin and not admin_camin.is_super_admin:
        return render(request, 'not_allowed.html', {
            'message': 'Nu ești asociat niciunui cămin sau nu ai selectat unul activ.'
        })

    # 🧱 Închide conexiunile vechi
    close_old_connections()

    studenti_importati = []
    camine = Camin.objects.all()

    # 🧩 Dacă e super-admin — are voie să importe Excel
    if admin_camin.is_super_admin and request.method == 'POST' and request.FILES.get('fisier'):
        fisier = request.FILES['fisier']
        path = default_storage.save(f"temp/{fisier.name}", fisier)

        try:
            # ✅ Verifică formatul fișierului
            if not (path.endswith('.xlsx') or path.endswith('.xls')):
                messages.error(request, "Fișierul trebuie să fie în format Excel (.xlsx sau .xls).")
                return redirect('incarca_studenti')

            df = pd.read_excel(default_storage.path(path))

            if df.empty:
                raise ValueError("Fișierul este gol sau nu conține date valide.")

            df.columns = df.columns.str.strip().str.lower()
            required_cols = ['email', 'nume', 'prenume', 'camin', 'camera']
            if not all(col in df.columns for col in required_cols):
                raise ValueError("Fișierul trebuie să conțină coloanele: email, nume, prenume, camin, camera.")

            with transaction.atomic():
                for _, row in df.iterrows():
                    email = str(row['email']).strip().lower()
                    nume = str(row['nume']).strip().title()
                    prenume = str(row['prenume']).strip().title()
                    camin_nume = str(row['camin']).strip().upper()
                    camera = str(row['camera']).strip()

                    camin_obj, _ = Camin.objects.get_or_create(nume=camin_nume)

                    user, _ = User.objects.update_or_create(
                        username=email,
                        defaults={'email': email, 'first_name': prenume, 'last_name': nume}
                    )

                    ProfilStudent.objects.update_or_create(
                        utilizator=user,
                        defaults={
                            'email': email,
                            'nume': nume,
                            'prenume': prenume,
                            'camin': camin_obj,
                            'numar_camera': camera
                        }
                    )

                    studenti_importati.append({
                        'email': email,
                        'nume': nume,
                        'prenume': prenume,
                        'camin': camin_nume,
                        'camera': camera
                    })

            default_storage.delete(path)
            messages.success(request, "Lista de studenți a fost importată cu succes.")
        except Exception as e:
            messages.error(request, f"Eroare la procesare: {e}")
            if 'path' in locals():
                default_storage.delete(path)



    # 🧩 Adminii de cămin văd doar lista studenților lor
    if admin_camin.is_super_admin:
        if camin:  # dacă super-adminul a selectat un cămin din dropdown
            studenti = ProfilStudent.objects.filter(camin=camin)
        else:
           studenti = ProfilStudent.objects.all()
    else:
        studenti = ProfilStudent.objects.filter(camin=admin_camin.camin)


    return render(request, 'dashboard/admin_camin/incarca_studenti.html', {
        'studenti_importati': studenti_importati,
        'camin': camin,
        'studenti': studenti,
        'camine': camine,
        'is_super_admin': admin_camin.is_super_admin
    })



# =========================
# Admin cămin - Adăugare student
# =========================
@login_required
@only_admins
def adauga_student_view(request):
    user = request.user
    admin = AdminCamin.objects.filter(email=user.email).first()
    camin = get_camin_curent(request)  # 🟢 acum și super-adminul are cămin selectat

    # dacă e admin normal — forțăm căminul propriu
    if admin and not admin.is_super_admin:
        camin = admin.camin

    if not camin:
        messages.error(request, "Selectează mai întâi un cămin din bara de sus.")
        return redirect('incarca_studenti')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        nume = request.POST.get('nume', '').strip().title()
        prenume = request.POST.get('prenume', '').strip().title()
        camera = request.POST.get('numar_camera', '').strip()

        if not email:
            messages.error(request, "Emailul este obligatoriu!")
            return redirect('adauga_student')

        try:
            # 👤 Creăm sau actualizăm utilizatorul
            user, _ = User.objects.get_or_create(
                username=email,
                defaults={'email': email, 'first_name': prenume, 'last_name': nume}
            )

            # 🧩 Creăm sau actualizăm profilul studentului
            ProfilStudent.objects.update_or_create(
                utilizator=user,
                defaults={
                    'email': email,
                    'nume': nume,
                    'prenume': prenume,
                    'camin': camin,
                    'numar_camera': camera
                }
            )

            messages.success(request, f"Studentul a fost adăugat cu succes în {camin.nume}.")
            return redirect('incarca_studenti')

        except Exception as e:
            messages.error(request, f"Eroare la adăugarea studentului: {str(e)}")
            return redirect('adauga_student')

    return render(request, 'dashboard/admin_camin/adauga_student.html', {
        'camin': camin,
        'is_super_admin': admin.is_super_admin if admin else False,
    })



# views.py
import re
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

from booking.models import ProfilStudent, AdminCamin  # ajustează importul dacă ai alt app

@login_required
def adauga_telefon(request):
    # Accept doar POST; altfel, întoarce utilizatorul înapoi.
    if request.method != "POST":
        return redirect(request.META.get("HTTP_REFERER") or "home")

    # 1) Colectare & normalizare
    telefon_raw = (request.POST.get("telefon") or "").strip()
    tara = (request.POST.get("tara") or "ro").strip().lower()

    # elimină spații/liniuțe/paranteze/puncte, păstrând + și cifre
    num = re.sub(r"[^\d+]", "", telefon_raw)

    # prefix implicit după țară
       # 2️⃣ Mapare prefixe pentru mai multe țări
    prefix_map = {
        "ro": "+40",   # România
        "md": "+373",  # Moldova
        "bg": "+359",  # Bulgaria
        "hu": "+36",   # Ungaria
        "de": "+49",   # Germania
        "it": "+39",   # Italia
        "fr": "+33",   # Franța
        "es": "+34",   # Spania
        "uk": "+44",   # Marea Britanie
        "gr": "+30",   # Grecia
    }
    prefix = prefix_map.get(tara, "+40")  # fallback la România

    # dacă nu începe cu +, adaugă prefixul și taie 0 din față (ex: 07xx…)
    if not num.startswith("+"):
        num = prefix + num.lstrip("0")

    # validare simplă E.164: + urmat de 9–15 cifre
    if not re.fullmatch(r"^\+\d{9,15}$", num):
        messages.error(request, "Numărul introdus nu este valid. Verifică și încearcă din nou.")
        return redirect(request.META.get("HTTP_REFERER") or "home")

    # 2) Actualizare în toate locurile unde poate fi stocat
    updated = 0

    # — AdminCamin: pot exista mai multe rânduri pentru același email (cămine diferite)
    updated += AdminCamin.objects.filter(email=request.user.email).update(telefon=num)

    # — ProfilStudent: de obicei unic; folosim update pentru consistență
    updated += ProfilStudent.objects.filter(utilizator=request.user).update(telefon=num)

    # 3) Feedback
    if updated:
        messages.success(request, f"Numărul de telefon a fost actualizat la {num}.")
    else:
        messages.warning(request, "Nu am găsit un profil de student sau admin asociat utilizatorului curent.")

    # 4) Înapoi la pagina de unde a venit utilizatorul
    return redirect(request.META.get("HTTP_REFERER") or "home")



# =========================
# Admin cămin - Ștergere student
# =========================
@login_required
@only_admins
def sterge_student_view(request, student_id):
    student = get_object_or_404(ProfilStudent, id=student_id)
    user = student.utilizator
    student.delete()
    user.delete()
    messages.success(request, "Studentul a fost șters.")
    return redirect('incarca_studenti')


# =========================
# Admin cămin - Ștergere toți studenții
# =========================
@login_required
@only_admins
def sterge_toti_studentii_view(request):

    admin = AdminCamin.objects.get(email=request.user.email)
    camin = admin.camin
    studenti = ProfilStudent.objects.filter(camin=camin)

    user_ids = studenti.values_list('utilizator__id', flat=True)
    studenti.delete()
    User.objects.filter(id__in=user_ids).delete()
    messages.success(request, f"Toți studenții din {camin.nume} au fost șterși.")
    return redirect('incarca_studenti')


# =========================
# Admin cămin - Actualizare student
# =========================
@login_required
@require_POST
@only_admins
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



from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from booking.models import ProfilStudent

@csrf_exempt
def save_fcm_token(request):
    if request.method == "POST" and request.user.is_authenticated:
        try:
            data = json.loads(request.body)
            token = data.get("token")
            if not token:
                return JsonResponse({"error": "Token lipsă"}, status=400)
            
            profil = ProfilStudent.objects.filter(utilizator=request.user).first()
            if profil:
                profil.fcm_token = token
                profil.save()
                return JsonResponse({"success": True})
            else:
                return JsonResponse({"error": "Profil inexistent"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Metodă invalidă sau utilizator neautentificat"}, status=400)



@login_required
def selecteaza_camin(request):
    if request.method == "POST":
        camin_id = request.POST.get("camin_id")
        if camin_id:
            request.session["camin_selectat"] = camin_id
    return redirect(request.META.get("HTTP_REFERER", "dashboard_admin_camin"))
