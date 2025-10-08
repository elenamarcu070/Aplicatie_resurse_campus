import json
from datetime import datetime, timedelta, date
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

    # Admin de cămin
    if AdminCamin.objects.filter(email=email).exists():
        return redirect('dashboard_admin_camin')

    # Student existent
    if ProfilStudent.objects.filter(utilizator=user).exists():
        return redirect('dashboard_student')

    # Dacă nu are profil încă → creează unul de bază
    email_parts = email.split('@')[0].split('.')
    nume_email = email_parts[-1].replace('-', ' ').title() if len(email_parts) >= 2 else ""
    prenume_email = email_parts[0].replace('-', ' ').title() if len(email_parts) >= 1 else ""

    ProfilStudent.objects.create(
        utilizator=user,
        camin=None,
        email=email,
        nume=nume_email,
        prenume=prenume_email
    )
    return redirect('dashboard_student')




# =========================
# Logout personalizat
# =========================
def custom_logout(request):
    logout(request)
    return redirect('account_login')


# =========================
# Dashboard-uri după rol
# =========================
@login_required
@only_students
def dashboard_student(request):
    if not ProfilStudent.objects.filter(utilizator=request.user).exists():
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar studenților.'
        })
    return render(request, 'dashboard/student.html')


# =========================
# Dashboard Admin Cămin
# =========================
@login_required
@only_admins
def dashboard_admin_camin(request):
    admin = AdminCamin.objects.filter(email=request.user.email).first()
    if not admin:
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar administratorilor de cămin.'
        })
    return render(request, 'dashboard/admin_camin.html', {'admin': admin})
# =========================
# Admin cămin - Administrare cămine
# =========================
@login_required
@only_admins
def administrare_camin(request):
    camine = Camin.objects.all()
    return render(request, 'dashboard/admin_camin/administrare_camin.html', {
        'camine': camine
    })


# =========================
# Admin cămin - Lista cămine
# =========================
@login_required
@only_admins
def lista_camine_admin(request):
    camine = Camin.objects.all()
    return render(request, 'dashboard/admin_camin/lista_camine.html', {'camine': camine})


# =========================
# Admin cămin - Adăugare cămin
# =========================
@login_required
@only_admins
def adauga_camin_view(request):
    if request.method == 'POST':
        nume = request.POST.get('nume')
        if nume:
            Camin.objects.create(nume=nume)
            messages.success(request, 'Cămin adăugat cu succes!')
            return redirect('administrare_camin')
    return render(request, 'dashboard/admin_camin/adauga_camin.html')


# =========================
# Admin cămin - Ștergere cămin
# =========================
@login_required
@only_admins
def sterge_camin_view(request, camin_id):
    camin = get_object_or_404(Camin, id=camin_id)
    camin.delete()
    messages.success(request, f'Căminul "{camin.nume}" a fost șters.')
    return redirect('administrare_camin')


# =========================
# Admin cămin - Detalii cămin
# =========================
@login_required
@only_admins
def detalii_camin_admin(request, camin_id):
    camin = get_object_or_404(Camin, id=camin_id)

    if request.method == 'POST':
        # ✅ Adăugare admin
        if 'email_nou_admin' in request.POST:
            email_nou = request.POST.get('email_nou_admin').strip().lower()
            if email_nou:
                if not AdminCamin.objects.filter(camin=camin, email=email_nou).exists():
                    AdminCamin.objects.create(camin=camin, email=email_nou)
                    messages.success(request, f"Adminul '{email_nou}' a fost adăugat cu succes.")
                else:
                    messages.warning(request, f"'{email_nou}' este deja admin la acest cămin.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Ștergere admin
        elif 'sterge_admin_id' in request.POST:
            admin_id = request.POST.get('sterge_admin_id')
            admin = get_object_or_404(AdminCamin, id=admin_id)
            admin.delete()
            messages.success(request, f"Adminul '{admin.email}' a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Adăugare mașină
        elif 'nume_masina' in request.POST:
            nume = request.POST.get('nume_masina').strip()
            if nume:
                Masina.objects.create(camin=camin, nume=nume, activa=True)
                messages.success(request, f"Mașina '{nume}' a fost adăugată.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Ștergere mașină
        elif 'sterge_masina_id' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['sterge_masina_id'])
            masina.delete()
            messages.success(request, f"Mașina '{masina.nume}' a fost ștearsă.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Activare / dezactivare completă mașină
        elif 'toggle_masina_id' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['toggle_masina_id'])
            masina.activa = not masina.activa
            masina.save()
            status = "activată" if masina.activa else "dezactivată"
            messages.success(request, f"Mașina '{masina.nume}' a fost {status}.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Editare nume mașină
        elif 'edit_masina_id' in request.POST and 'nume_masina_nou' in request.POST:
            masina = get_object_or_404(Masina, id=request.POST['edit_masina_id'])
            nume_nou = request.POST.get('nume_masina_nou').strip()
            if nume_nou:
                masina.nume = nume_nou
                masina.save()
                messages.success(request, f"Numele mașinii a fost actualizat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Dezactivare mașină pe interval ⏰
        elif 'dezactiveaza_masina_id' in request.POST:
            masina_id = request.POST.get('dezactiveaza_masina_id')
            data_str = request.POST.get('data_dezactivare')
            ora_start_str = request.POST.get('ora_start')
            ora_end_str = request.POST.get('ora_end')

            try:
                masina = Masina.objects.get(id=masina_id)
                data_selectata = datetime.strptime(data_str, '%Y-%m-%d').date()
                ora_start = datetime.strptime(ora_start_str, '%H:%M').time()
                ora_end = datetime.strptime(ora_end_str, '%H:%M').time()

                rezervari_afectate = Rezervare.objects.filter(
                    masina=masina,
                    data_rezervare=data_selectata,
                    ora_start__lt=ora_end,
                    ora_end__gt=ora_start,
                    anulata=False
                )

                numar_notificari = 0
                for rez in rezervari_afectate:
                    # Notificare SMS
                    mesaj = (
                        f"[WashTuiasi] Rezervarea ta din {rez.data_rezervare.strftime('%d %b %Y')} "
                        f"({rez.ora_start.strftime('%H:%M')} - {rez.ora_end.strftime('%H:%M')}) "
                        f"la mașina '{masina.nume}' a fost anulată deoarece mașina este dezactivată în acel interval."
                    )

                    profil_student = ProfilStudent.objects.filter(utilizator=rez.utilizator).first()
                    if profil_student and profil_student.telefon:
                        trimite_sms(profil_student.telefon, mesaj)
                        numar_notificari += 1

                    rez.anulata = True
                    rez.save()

                messages.success(request, f"Mașina '{masina.nume}' a fost dezactivată pentru intervalul selectat. "
                                          f"{numar_notificari} rezervări au fost anulate și notificate.")
            except Exception as e:
                messages.error(request, f"Eroare la dezactivarea pe interval: {e}")

            return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Programe mașini
        elif 'adauga_program_masina' in request.POST or 'program_masina_id' in request.POST:
            masina_id = request.POST.get('program_masina_id')
            ora_start = request.POST.get('ora_start_masina')
            ora_end = request.POST.get('ora_end_masina')
            masina = get_object_or_404(Masina, id=masina_id)
            ProgramMasina.objects.create(masina=masina, ora_start=ora_start, ora_end=ora_end)
            messages.success(request, "Programul mașinii a fost adăugat.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

        elif 'sterge_program_masina_id' in request.POST:
            program_id = request.POST.get('sterge_program_masina_id')
            program = get_object_or_404(ProgramMasina, id=program_id)
            program.delete()
            messages.success(request, "Programul mașinii a fost șters.")
            return redirect('detalii_camin_admin', camin_id=camin.id)

    # ✅ date pentru template
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
# Rezervarea mașinilor
# =========================
@login_required
def calendar_rezervari_view(request):
    user = request.user

    # verificăm dacă e student sau admin
    admin_camin = AdminCamin.objects.filter(email=user.email).first()
    student = ProfilStudent.objects.filter(utilizator=user).first()

    if not admin_camin and not student:
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar studenților sau administratorilor.'
        })

    masini = []
    nume_camin = "Cămin necunoscut"
    este_admin_camin = False
    este_student = False

    if admin_camin:
        camin = admin_camin.camin
        masini = Masina.objects.filter(camin=camin, activa=True)
        nume_camin = camin.nume
        este_admin_camin = True
    elif student and student.camin:
        camin = student.camin
        masini = Masina.objects.filter(camin=camin, activa=True)
        nume_camin = camin.nume
        este_student = True

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
        r.avertizat = Avertisment.objects.filter(
            utilizator=r.utilizator,
            data__gte=r.data_rezervare
        ).exists()
        rezervari_dict[r.masina.id][r.data_rezervare][start_hour] = r

    profil = ProfilStudent.objects.filter(utilizator=user).first()
    este_blocat = profil.este_blocat() if profil else False

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







import logging, traceback


from .utils import trimite_sms

logger = logging.getLogger(__name__)





@login_required
def creeaza_rezervare(request):
    user = request.user
    saptamana = request.POST.get('saptamana', 0)

    # verificare drepturi acces
    if not (AdminCamin.objects.filter(email=user.email).exists() or
            ProfilStudent.objects.filter(utilizator=user).exists()):
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar studenților sau administratorilor.'
        })

    profil = ProfilStudent.objects.filter(utilizator=user).first()
    if profil and profil.suspendat_pana_la and profil.suspendat_pana_la >= date.today():
        messages.error(request, f"Contul tău este blocat până la {profil.suspendat_pana_la.strftime('%d %B %Y')}.")
        return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

    if request.method == 'POST':
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

            # avertismente recente
            avertismente = Avertisment.objects.filter(
                utilizator=user,
                data__gte=azi - timedelta(days=7)
            ).count()
            if avertismente >= 3:
                messages.error(request, "Cont blocat temporar din cauza avertismentelor.")
                return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

            # verificări de date
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

            # logica de preluare rezervare
            for rez in rezervari_existente:
                rezervari_alt_user = Rezervare.objects.filter(
                    utilizator=rez.utilizator,
                    data_rezervare__range=(start_sapt, end_sapt),
                    anulata=False
                )

                if len(rezervari_sapt) < len(rezervari_alt_user) or rez.nivel_prioritate > nr_rezervari + 1:
                    rez.anulata = True
                    rez.save()

                    mesaj_notificare = (
                        f"[WashTuiasi] Rezervarea ta din {rez.data_rezervare.strftime('%d %b %Y')}, "
                        f"interval {rez.ora_start.strftime('%H:%M')} - {rez.ora_end.strftime('%H:%M')} "
                        f"la mașina '{rez.masina.nume}' a fost preluată de alt student. "
                        f"Prioritatea ta a fost {rez.nivel_prioritate}, iar a lui {nr_rezervari + 1}. "
                        f"Reprogramează-te pe washtuiasi."
                    )

                    # 🔔 Trimitere SMS – pentru student sau admin
                    try:
                        profil_vechi = ProfilStudent.objects.filter(utilizator=rez.utilizator).first()
                        if profil_vechi and profil_vechi.telefon:
                            trimite_sms(profil_vechi.telefon, mesaj_notificare)
                            logger.info(f"📲 SMS notificare trimis către {profil_vechi.telefon} ({rez.utilizator.email})")
                        else:
                            admin_camin = AdminCamin.objects.filter(email=rez.utilizator.email).first()
                            if admin_camin and admin_camin.telefon:
                                trimite_sms(admin_camin.telefon, mesaj_notificare)
                            else:
                                logger.warning(f"User {rez.utilizator.email} fără telefon în profil sau admin — nu se trimite SMS.")
                    except Exception as e:
                        logger.error(f"Eroare trimitere SMS: {e}")

                    break
                else:
                    messages.error(request, "Nu poți prelua această rezervare (prioritate mai mare sau egală).")
                    return redirect(f"{reverse('calendar_rezervari')}?saptamana={saptamana}")

            # creăm rezervarea nouă
            rezervare = Rezervare.objects.create(
                utilizator=user,
                masina=masina,
                data_rezervare=data_rezervare,
                ora_start=ora_start,
                ora_end=ora_end,
                nivel_prioritate=1
            )

            # actualizare priorități
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
    toate_rezervarile = Rezervare.objects.filter(utilizator=user, anulata=False)

    rezervari_urmatoare = toate_rezervarile.filter(data_rezervare__gte=azi).order_by('data_rezervare', 'ora_start')
    rezervari_incheiate = toate_rezervarile.filter(data_rezervare__lt=azi).order_by('-data_rezervare')

    context = {
        "rezervari_urmatoare": rezervari_urmatoare,
        "rezervari_incheiate": rezervari_incheiate,
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
        # Răspuns corect pentru fetch()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": "Rezervarea nu există sau nu îți aparține."}, status=404)
        messages.error(request, "Rezervarea nu există sau nu îți aparține.")
        return redirect('calendar_rezervari')

    if rezervare.data_rezervare < date.today():
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": "Nu poți anula o rezervare trecută."}, status=400)
        messages.error(request, "Nu poți anula o rezervare trecută.")
        return redirect('calendar_rezervari')

    rezervare.anulata = True
    rezervare.save()
    Rezervare.actualizeaza_prioritati(user, rezervare.data_rezervare)

    # Dacă e AJAX, întoarcem JSON; altfel păstrăm fluxul vechi
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
        return redirect('calendar_rezervari')

    rezervare_id = request.POST.get('rezervare_id')
    rezervare = get_object_or_404(Rezervare, id=rezervare_id)
    utilizator = rezervare.utilizator

    # verifică dacă adminul e din același cămin
    admin = AdminCamin.objects.filter(email=request.user.email).first()
    if not admin or rezervare.masina.camin_id != admin.camin_id:
        messages.error(request, "Nu poți trimite avertismente pentru alt cămin.")
        return redirect('calendar_rezervari')

    azi = timezone.localdate()

    # vezi dacă deja există avertisment azi
    if Avertisment.objects.filter(utilizator=utilizator, data=azi).exists():
        messages.warning(request, "Ai trimis deja un avertisment acestui utilizator astăzi.")
        return redirect('calendar_rezervari')

    # creează avertisment
    Avertisment.objects.create(
        utilizator=utilizator,
        motiv="Rezervare neutilizată"
    )

    # număr total avertismente în ultimele 30 zile
    avertismente_recente = Avertisment.objects.filter(
        utilizator=utilizator,
        data__gte=azi - timedelta(days=30)
    ).count()

    profil = ProfilStudent.objects.filter(utilizator=utilizator).first()
    data_blocare_pana = None

    # dacă e al 3-lea avertisment → blocare 7 zile
    if avertismente_recente >= 3 and profil:
        data_blocare_pana = azi + timedelta(days=7)
        profil.suspendat_pana_la = data_blocare_pana
        profil.save()

    # compunem email
    data_str = rezervare.data_rezervare.strftime("%d %b %Y")
    interval_str = f"{rezervare.ora_start.strftime('%H:%M')} - {rezervare.ora_end.strftime('%H:%M')}"
    subject = "Avertisment pentru rezervare neutilizată"

    text_body = (
        f"Bună {utilizator.get_full_name() or utilizator.username},\n\n"
        f"Ai primit un avertisment pentru rezervarea din {data_str}, interval {interval_str}, "
        f"la mașina '{rezervare.masina.nume}'.\n\n"
    )

    if data_blocare_pana:
        text_body += (
            f"Acesta este al treilea avertisment din ultima perioadă. "
            f"Contul tău a fost blocat până la {data_blocare_pana.strftime('%d %b %Y')}.\n"
        )
    else:
        text_body += (
            "Dacă acumulezi 3 avertismente într-o lună, contul tău va fi blocat temporar.\n"
        )

    html_body = text_body.replace("\n", "<br>")

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[utilizator.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
        messages.success(request, "Avertisment trimis și notificare prin email.")
    except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Eroare la trimiterea emailului: {e}")
            messages.warning(request, f"Avertisment creat, dar emailul nu a putut fi trimis: {e}")

    return redirect('calendar_rezervari')



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
    if not AdminCamin.objects.filter(email=request.user.email).exists():
        return render(request, 'not_allowed.html', {
            'message': 'Nu ai drepturi de administrator.'
        })
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
        'camine': camine
    })


# =========================
# Admin cămin - Adăugare student
# =========================
@login_required
@only_admins
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

def adauga_telefon(request):
    if request.method == "POST":
        telefon = request.POST.get("telefon")
        profil = request.user.profilstudent
        profil.telefon = telefon
        profil.save()
        messages.success(request, "Numărul de telefon a fost actualizat.")
    return redirect("dashboard_student")


@login_required
def adauga_telefon_admin(request):
    if request.method == "POST":
        telefon = request.POST.get("telefon")
        admin = AdminCamin.objects.filter(email=request.user.email).first()
        if admin:
            admin.telefon = telefon
            admin.save()
            messages.success(request, "Numărul de telefon a fost actualizat.")
    return redirect("dashboard_admin_camin")



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
