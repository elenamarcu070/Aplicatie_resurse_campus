import json
import logging
import traceback
from datetime import datetime, time, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.db import IntegrityError, close_old_connections, transaction
from django.db.models import F, Max, Min, Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from twilio.request_validator import RequestValidator

from booking.models import (
    AdminCamin,
    Avertisment,
    Camin,
    CerereCont,
    IntervalDezactivare,
    Masina,
    Notificare,
    NotificareLog,
    ProfilStudent,
    ProgramMasina,
    ProgramUscator,
    Rezervare,
    Uscator,
)
from booking.import_studenti import aplica_plan, citeste_fisier, construieste_plan
from booking.push import notifica_student, push_este_configurat
from booking.utils import (
    get_camin_curent,
    sefi_de_camin,
    normalizeaza_numar,
    notifica_admini_cerere,
    valideaza_numar,
)

logger = logging.getLogger(__name__)


def inapoi_la(request, implicit):
    """
    Redirect inapoi la pagina de unde a venit cererea.

    Foloseste Referer doar daca trimite catre acest site: altfel o pagina
    externa ar putea redirecta utilizatorul unde vrea ea.
    """
    referer = request.META.get("HTTP_REFERER")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(referer)
    return redirect(implicit)


MESAJ_CONT_INACTIV = (
    "Contul tău nu mai este activ. Dacă locuiești în continuare în cămin, "
    "contactează administratorul căminului."
)


def login_redirect_google(request):
    return redirect('/accounts/google/login/?process=login')
# =========================
# Decoratori pentru roluri
# =========================

def only_students(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        profil = ProfilStudent.objects.filter(utilizator=request.user).first()
        if not profil:
            return render(request, 'not_allowed.html', {'message': 'Acces permis doar studenților.'})
        if not profil.activ:
            return render(request, 'not_allowed.html', {'message': MESAJ_CONT_INACTIV})
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
        if not profil.activ:
            # Nu stergem nimic: contul si istoricul raman, doar accesul e oprit.
            logout(request)
            return render(request, 'not_allowed.html', {'message': MESAJ_CONT_INACTIV})
        # dacă există profil, dar nu e legat de userul curent → îl reatașăm
        if profil.utilizator != user:
            profil.utilizator = user
            profil.save()
        return redirect('dashboard_student')

    # 🔴 3. Dacă nu e găsit în baza de date → NU îl creăm, doar blocăm accesul.
    # Păstrăm însă datele venite de la Google, ca să poată cere un cont fără
    # să-și scrie adresa de mână: așa nimeni nu poate cere cont în numele
    # altuia, iar formularul nu poate fi completat de roboți.
    date_cerere = {
        "email": email,
        "prenume": (user.first_name or "").strip(),
        "nume": (user.last_name or "").strip(),
    }
    logout(request)
    try:
        user.delete()
    except Exception:
        logger.warning(f"Nu am putut sterge contul neautorizat {email}.")

    # După `logout` sesiunea e alta, goală: scriem în ea de-abia acum.
    request.session["cerere_cont"] = date_cerere
    return render(request, 'not_allowed.html', {
        'poate_cere_cont': True,
        # `request.user` e deja anonim aici, deci adresa trebuie dată explicit,
        # altfel propoziția rămâne cu un gol în mijloc.
        'email_incercat': email,
        'sefi': sefi_de_camin(),
    })





# =========================
# Logout personalizat
# =========================
def custom_logout(request):
    logout(request)
    # NU catre 'account_login': acea ruta e deturnata catre Google
    # (vezi rezervari_spalatorie/urls.py), iar Google re-autentifica tacut
    # utilizatorul cat timp sesiunea lui din browser e vie — deci apasarea
    # butonului de logout parea ca nu face nimic. `home` este chiar pagina
    # de autentificare, cu butonul de Google pe ea.
    return redirect('home')


# =========================
# Dashboard-uri după rol
# =========================


@login_required 
@only_students
def dashboard_student(request):
    profil = ProfilStudent.objects.filter(utilizator=request.user).first()
    if not profil:
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar studenților.'
        })

    profil.refresh_from_db()

    azi = timezone.localdate()
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

    # Daca ultima notificare catre el nu a ajuns, studentul trebuie sa afle:
    # altfel isi pierde rezervarile preluate fara sa stie de ce.
    ultima_notificare = NotificareLog.objects.filter(
        profil=profil, canal=NotificareLog.WHATSAPP
    ).first()
    notificare_esuata = (
        ultima_notificare if ultima_notificare and ultima_notificare.a_esuat else None
    )

    context = {
        'profil': profil,
        'rezervare_activa': rezervare_activa,
        'avertismente_active': avertismente_active,
        'notificare_esuata': notificare_esuata,
        # Butonul de activare apare doar daca serverul chiar poate trimite push,
        # ca studentul sa nu acorde permisiunea degeaba.
        'push_configurat': push_este_configurat(),
    }

    return render(request, 'dashboard/student.html', context)



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

    # 🔁 Reîncărcăm datele reale din DB (ca să nu fie cache vechi)
    admin.refresh_from_db()

    # 🔍 Căutăm rezervarea activă (azi sau mâine)
    azi = timezone.localdate()
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
        if ('email_nou_admin' in request.POST or 'sterge_admin_id' in request.POST
                or 'salveaza_admin_id' in request.POST):
            if not is_super_admin(request.user):
                messages.error(request, "Doar super-adminii pot modifica lista de administratori.")
                return redirect('detalii_camin_admin', camin_id=camin.id)

        # ✅ Datele de contact arătate studenților pe pagina de acces interzis
        if 'salveaza_admin_id' in request.POST:
            # Cautarea e limitata la caminul curent: altfel un id trimis de mana
            # ar lasa pe cineva sa editeze adminul altui camin.
            rand = get_object_or_404(
                AdminCamin, id=request.POST['salveaza_admin_id'], camin=camin
            )
            telefon = normalizeaza_numar(
                request.POST.get('telefon'), request.POST.get('tara')
            )
            if telefon:
                valid, eroare = valideaza_numar(telefon)
                if not valid:
                    messages.error(request, eroare)
                    return redirect('detalii_camin_admin', camin_id=camin.id)

            rand.nume = request.POST.get('nume', '').strip()[:100]
            rand.telefon = telefon
            rand.primeste_notificari = request.POST.get('primeste_notificari') == 'on'
            rand.save(update_fields=['nume', 'telefon', 'primeste_notificari'])

            messages.success(request, f"Datele pentru {rand.email} au fost salvate.")
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
                    data_rezervare__gte=timezone.localdate()
                ).exclude(anulata=True)

                numar_notificari = 0
                for rez in rezervari_viitoare:
                    try:
                        profil_vechi = ProfilStudent.objects.filter(utilizator=rez.utilizator).first()
                        if profil_vechi:
                            notifica_student(
                                profil_vechi,
                                "dezactivare_masina_complet",
                                {
                                    "2": rez.data_rezervare.strftime('%d %b %Y'),
                                    "3": rez.ora_start.strftime('%H:%M'),
                                    "4": rez.ora_end.strftime('%H:%M'),
                                    "1": rez.masina.nume,
                                },
                                titlu="Mașina a fost scoasă din uz",
                                corp=(
                                    f"Rezervarea ta la {rez.masina.nume} din "
                                    f"{rez.data_rezervare.strftime('%d %b')}, "
                                    f"{rez.ora_start.strftime('%H:%M')}, a fost anulată."
                                ),
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
                        if profil_vechi:
                            notifica_student(
                                profil_vechi,
                                "dezactivare_masina_interval",
                                {
                                    "2": rez.data_rezervare.strftime('%d %b %Y'),
                                    "3": rez.ora_start.strftime('%H:%M'),
                                    "4": rez.ora_end.strftime('%H:%M'),
                                    "1": rez.masina.nume,
                                },
                                titlu="Mașina e indisponibilă în intervalul tău",
                                corp=(
                                    f"Rezervarea ta la {rez.masina.nume} din "
                                    f"{rez.data_rezervare.strftime('%d %b')}, "
                                    f"{rez.ora_start.strftime('%H:%M')}, a fost anulată."
                                ),
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

def filtru_suprapunere(ora_start, ora_end):
    """
    Q pentru intervalele care se suprapun cu [ora_start, ora_end) dintr-o zi.

    Programul mașinilor trece de miezul nopții (07:00 → 01:00), deci ultimul
    slot al zilei are ora_end mai mică decât ora_start (ex. 22:00 → 01:00).
    Pentru astfel de intervale comparația directă `ora_start < ora_end` este
    mereu falsă, iar slotul ar putea fi rezervat de oricâte ori. Aici tratăm
    un interval care trece de miezul nopții ca ocupând ziua până la 24:00.
    """
    sfarsit_efectiv = ora_end if ora_end > ora_start else time(23, 59, 59)
    return Q(ora_start__lt=sfarsit_efectiv) & (
        Q(ora_end__gt=ora_start) | Q(ora_end__lte=F("ora_start"))
    )


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

    azi = timezone.localdate()
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
            ProfilStudent.objects.filter(utilizator=user, activ=True).exists()):
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar studenților sau administratorilor.'
        })

    camin = get_camin_curent(request)
    if camin is None:
        messages.error(request, "Nu ai un cămin asociat. Contactează administratorul.")
        return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

    profil = ProfilStudent.objects.filter(utilizator=user).first()
    if profil and profil.suspendat_pana_la and profil.suspendat_pana_la >= timezone.localdate():
        messages.error(request, f"Contul tău este blocat până la {profil.suspendat_pana_la.strftime('%d %B %Y')}.")
        return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')
    
    if profil and not profil.telefon:
        # Formularul de telefon este pe dashboard-ul studentului; `adauga_telefon`
        # accepta doar POST, deci un redirect acolo ar fi aruncat utilizatorul
        # pe pagina de start, fara niciun formular.
        messages.warning(request, "Trebuie să adaugi un număr de telefon înainte de a face o rezervare.")
        return redirect('dashboard_student')


    if request.method == 'POST':
        masina_id = request.POST.get('masina_id')
        data_str = request.POST.get('data')
        ora_start_str = request.POST.get('ora_start')


        try:
            # 🔒 Mașina trebuie să aparțină căminului curent — altfel un masina_id
            # modificat în browser ar permite rezervarea într-un alt cămin.
            masina = Masina.objects.filter(id=masina_id, camin=camin).first()
            if masina is None:
                messages.error(request, "Mașina selectată nu există în căminul tău.")
                return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')
            if not masina.activa:
                messages.error(request, "Mașina selectată este dezactivată.")
                return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

            data_rezervare = datetime.strptime(data_str, '%Y-%m-%d').date()
            ora_start = datetime.strptime(ora_start_str, '%H:%M').time()
            durata = timedelta(hours=camin.durata_interval)
            ora_end = (datetime.combine(timezone.localdate(), ora_start) + durata).time()
            azi = timezone.localdate()

            # 🟡 Verificăm dacă intervalul cerut este într-un interval dezactivat
            exista_blocaj = IntervalDezactivare.objects.filter(
                filtru_suprapunere(ora_start, ora_end),
                masina=masina,
                data=data_rezervare,
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

            # 🔒 Verificarea intervalului și crearea rezervării trebuie să fie
            # atomice: fără asta, două cereri simultane pot trece amândouă de
            # verificarea de suprapunere și pot ocupa același interval.
            with transaction.atomic():
                masina = Masina.objects.select_for_update().get(id=masina.id)

                rezervari_existente = Rezervare.objects.filter(
                    filtru_suprapunere(ora_start, ora_end),
                    masina=masina,
                    data_rezervare=data_rezervare,
                    anulata=False,
                )

                if rezervari_existente.exists():
                    # dacă nu e preluare validă → STOP
                        poate_prelua = False
                        for rez in rezervari_existente:
                            if rez.nivel_prioritate > nr_rezervari + 1:
                               poate_prelua = True
                           
                        if not poate_prelua:
                            messages.error(request, "Intervalul este deja ocupat.")
                            return redirect(f"{reverse('calendar_rezervari')}?saptamana={saptamana}")
                # 🔁 Logica de preluare rezervare existentă
                for rez in rezervari_existente:
                    if rez.nivel_prioritate > nr_rezervari + 1:
                        rez.anulata = True
                        rez.save()

                        # 📲 Notificare — WhatsApp dacă are nr., altfel fallback
                        try:
                            profil_vechi = ProfilStudent.objects.filter(utilizator=rez.utilizator).first()
                            if profil_vechi:
                                notifica_student(
                                    profil_vechi,
                                    "rezervare_preluata_student",
                                    {
                                        "1": rez.data_rezervare.strftime('%d %b %Y'),
                                        "2": rez.ora_start.strftime('%H:%M'),
                                        "3": rez.ora_end.strftime('%H:%M'),
                                        "4": rez.masina.nume,
                                        "5": rez.nivel_prioritate,
                                        "6": nr_rezervari + 1,
                                    },
                                    titlu="Rezervarea ta a fost preluată",
                                    corp=(
                                        f"{rez.masina.nume}, {rez.data_rezervare.strftime('%d %b')} "
                                        f"la {rez.ora_start.strftime('%H:%M')}. "
                                        "Poți alege alt interval din calendar."
                                    ),
                                )
                            else:
                                logger.warning(f"Fara profil de student pentru {rez.utilizator.email}")
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

        except IntegrityError:
            # Constrângerea din baza de date a prins o rezervare simultană
            # pe același interval.
            logger.warning(
                f"Rezervare simultana respinsa: masina={masina_id} "
                f"data={data_str} ora={ora_start_str}"
            )
            messages.error(request, "Intervalul tocmai a fost ocupat de altcineva. Alege alt interval.")
            return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

        except Exception as e:
            logger.error(f"Eroare la creare rezervare: {e}\n{traceback.format_exc()}")
            messages.error(request, "A apărut o eroare la crearea rezervării. Încearcă din nou.")
            return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

    return redirect(f'{reverse("calendar_rezervari")}?saptamana={saptamana}')

@login_required
def programari_student_view(request):
    user = request.user

    if not (
        AdminCamin.objects.filter(email=user.email).exists() or
        ProfilStudent.objects.filter(utilizator=user).exists()
    ):
        return render(request, 'not_allowed.html', {
            'message': 'Acces permis doar studenților sau administratorilor.'
        })

    azi = timezone.localdate()
    acum = timezone.localtime().time()

    toate = Rezervare.objects.filter(utilizator=user, anulata=False)

    rezervari_urmatoare = []
    rezervari_incheiate = []

    for r in toate:
        # 🔹 ZI VIITOARE
        if r.data_rezervare > azi:
            rezervari_urmatoare.append(r)
            continue

        # 🔹 ZI TRECUTĂ
        if r.data_rezervare < azi:
            rezervari_incheiate.append(r)
            continue

        # 🔹 AZI
        if r.ora_start < r.ora_end:
            # interval normal (ex 07–10, 13–16)
            if r.ora_end > acum:
                rezervari_urmatoare.append(r)
            else:
                rezervari_incheiate.append(r)
        else:
            # interval peste miezul nopții (ex 22–01)
            rezervari_urmatoare.append(r)

    rezervari_urmatoare = sorted(
        rezervari_urmatoare,
        key=lambda r: (r.data_rezervare, r.ora_start)
    )

    rezervari_incheiate = sorted(
        rezervari_incheiate,
        key=lambda r: (r.data_rezervare, r.ora_start),
        reverse=True
    )

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
    if rezervare.data_rezervare < timezone.localdate():
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": "Nu poți anula o rezervare trecută."}, status=400)
        messages.error(request, "Nu poți anula o rezervare trecută.")
        return redirect('calendar_rezervari')

    acum = timezone.localtime().time()
    
    if rezervare.data_rezervare == timezone.localdate() and rezervare.ora_start <= acum:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "success": False,
                "error": "Rezervarea a început deja și nu mai poate fi anulată."
                }, status=400)
        messages.error(request, "Rezervarea a început deja și nu mai poate fi anulată.")
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
    if profil:
        notifica_student(
            profil,
            "advertisment_rezervare",
            {
                "1": utilizator.get_full_name() or utilizator.username,
                "2": rezervare.data_rezervare.strftime('%d %b %Y'),
                "3": f"{rezervare.ora_start.strftime('%H:%M')}–{rezervare.ora_end.strftime('%H:%M')}",
                "4": rezervare.masina.nume,
            },
            titlu="Ai primit un avertisment",
            corp=(
                f"Rezervare neutilizată: {rezervare.masina.nume}, "
                f"{rezervare.data_rezervare.strftime('%d %b')}, "
                f"{rezervare.ora_start.strftime('%H:%M')}."
            ),
        )
        messages.success(request, "Avertisment trimis și notificare către student.")
    else:
        messages.warning(request, "Avertisment trimis, dar studentul nu are profil.")

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
def _curata_import(request):
    """Șterge fișierul rămas de la un import început și neterminat."""
    cale = request.session.pop("import_studenti_cale", None)
    if cale and default_storage.exists(cale):
        default_storage.delete(cale)


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

    plan = None
    camine = Camin.objects.all()

    # 🧩 Importul Excel e doar pentru super-admin, în doi pași:
    # întâi previzualizare, abia după confirmare se scrie în baza de date.
    if admin_camin.is_super_admin and request.method == 'POST':
        actiune = request.POST.get('actiune', 'previzualizeaza')

        if actiune == 'anuleaza':
            _curata_import(request)
            messages.info(request, "Importul a fost anulat. Nu s-a modificat nimic.")
            return redirect('incarca_studenti')

        if actiune == 'confirma':
            cale = request.session.get("import_studenti_cale")
            if not cale or not default_storage.exists(cale):
                _curata_import(request)
                messages.error(request, "Fișierul nu mai este disponibil. Încarcă-l din nou.")
                return redirect('incarca_studenti')

            dezactiveaza = request.POST.get('dezactiveaza') == 'on'
            try:
                randuri, _ = citeste_fisier(default_storage.path(cale))
                rezultat = aplica_plan(randuri, dezactiveaza=dezactiveaza)
            except Exception as e:
                logger.error(f"Eroare la importul de studenti: {e}\n{traceback.format_exc()}")
                messages.error(request, "Importul nu a putut fi finalizat. Nu s-a modificat nimic.")
                return redirect('incarca_studenti')

            _curata_import(request)
            messages.success(request, (
                f"Import finalizat: {len(rezultat.de_creat)} adăugați, "
                f"{len(rezultat.de_actualizat)} actualizați, "
                f"{len(rezultat.de_reactivat)} reactivați, "
                f"{len(rezultat.de_dezactivat)} dezactivați."
            ))
            return redirect('incarca_studenti')

        fisier = request.FILES.get('fisier')
        if fisier:
            if not fisier.name.lower().endswith(('.xlsx', '.xls')):
                messages.error(request, "Fișierul trebuie să fie în format Excel (.xlsx sau .xls).")
                return redirect('incarca_studenti')

            _curata_import(request)
            cale = default_storage.save(f"temp/{fisier.name}", fisier)
            try:
                randuri, erori = citeste_fisier(default_storage.path(cale))
                plan = construieste_plan(randuri, erori=erori)
            except Exception as e:
                default_storage.delete(cale)
                logger.error(f"Eroare la citirea fisierului de import: {e}")
                messages.error(request, f"Nu am putut citi fișierul: {e}")
                return redirect('incarca_studenti')

            # Calea sta in sesiune, nu intr-un camp ascuns din formular:
            # altfel utilizatorul ar putea cere citirea oricarui fisier.
            request.session["import_studenti_cale"] = cale

    # 🧩 Adminii de cămin văd doar lista studenților lor
    if admin_camin.is_super_admin:
        if camin:
            studenti = ProfilStudent.objects.filter(camin=camin)
        else:
            studenti = ProfilStudent.objects.all()
    else:
        studenti = ProfilStudent.objects.filter(camin=admin_camin.camin)

    studenti = studenti.select_related('utilizator', 'camin').order_by(
        'activ', 'nume', 'prenume'
    )

    # Cererile de cont: super-adminul le vede pe toate, indiferent de căminul
    # selectat în bara de sus; șeful de cămin doar pe ale lui.
    cereri = CerereCont.objects.select_related('camin')
    if not admin_camin.is_super_admin:
        cereri = cereri.filter(camin=admin_camin.camin)

    return render(request, 'dashboard/admin_camin/incarca_studenti.html', {
        'plan': plan,
        'camin': camin,
        'studenti': studenti,
        'camine': camine,
        'is_super_admin': admin_camin.is_super_admin,
        'cereri': cereri.filter(stare=CerereCont.IN_ASTEPTARE),
        'cereri_rezolvate': cereri.exclude(stare=CerereCont.IN_ASTEPTARE)[:15],
    })


# =========================
# Notificari in aplicatie
# =========================
@login_required
@require_POST
def marcheaza_notificari_citite(request):
    """Apelat cand studentul deschide clopotelul din bara de sus."""
    profil = ProfilStudent.objects.filter(utilizator=request.user).first()
    if not profil:
        return JsonResponse({"error": "Profil inexistent"}, status=404)

    numar = Notificare.objects.filter(profil=profil, citita=False).update(citita=True)
    return JsonResponse({"marcate": numar})


# =========================
# Twilio - starea notificarilor
# =========================
@csrf_exempt
@require_POST
def twilio_status_callback(request):
    """
    Twilio anunta aici starea finala a fiecarui mesaj trimis.

    Apelul de trimitere se intoarce cu starea „queued", deci livrarea reala se
    afla abia de aici. Endpoint-ul este public, asa ca fiecare cerere este
    verificata cu semnatura Twilio inainte sa modifice ceva.
    """
    token = settings.TWILIO_AUTH_TOKEN
    semnatura = request.headers.get("X-Twilio-Signature", "")
    if not token or not RequestValidator(token).validate(
        request.build_absolute_uri(), request.POST.dict(), semnatura
    ):
        logger.warning("Callback Twilio respins: semnatura invalida")
        return HttpResponseForbidden("Semnatura invalida")

    sid = request.POST.get("MessageSid", "")
    jurnal = NotificareLog.objects.filter(message_sid=sid).first()
    if not jurnal:
        # Mesaj trimis inainte de introducerea jurnalului, sau din alt sistem.
        return HttpResponse(status=204)

    jurnal.stare = request.POST.get("MessageStatus") or jurnal.stare
    cod = request.POST.get("ErrorCode") or ""
    if cod:
        jurnal.cod_eroare = cod
        jurnal.detaliu = (request.POST.get("ErrorMessage") or "")[:500]
    jurnal.save(update_fields=["stare", "cod_eroare", "detaliu", "actualizat_la"])

    if jurnal.a_esuat:
        logger.warning(
            f"Notificare nelivrata: sablon={jurnal.sablon} "
            f"stare={jurnal.stare} cod={jurnal.cod_eroare}"
        )
    return HttpResponse(status=204)


# =========================
# Admin cămin - Activare / dezactivare student
# =========================
@login_required
@require_POST
@only_admins
def comuta_activ_student(request, student_id):
    student = get_object_or_404(ProfilStudent, id=student_id)
    admin = AdminCamin.objects.filter(email=request.user.email).first()

    if not is_super_admin(request.user):
        if not admin or not admin.camin or student.camin_id != admin.camin_id:
            return render(request, 'not_allowed.html', {
                'message': 'Nu ai acces la acest student.'
            })

    student.activ = not student.activ
    student.save()

    if student.activ:
        messages.success(request, f"{student.nume} {student.prenume} a fost reactivat.")
    else:
        messages.success(
            request,
            f"{student.nume} {student.prenume} a fost dezactivat. "
            "Contul si istoricul raman in baza de date."
        )
    return redirect('incarca_studenti')


# =========================
# Cereri de cont
# =========================
def cerere_cont_view(request):
    """
    Formularul prin care un student negăsit în liste cere un cont.

    Nu e o pagină publică: se ajunge aici doar după o autentificare Google
    reușită al cărei email nu a fost găsit. `callback` lasă atunci datele în
    sesiune, iar fără ele formularul nu se deschide. Adresa nu se poate
    schimba, deci cererea vine sigur de la cine spune că vine.
    """
    date_sesiune = request.session.get("cerere_cont") or {}
    email = (date_sesiune.get("email") or "").strip().lower()
    if not email:
        messages.info(request, "Autentifică-te întâi cu Google, apoi poți cere un cont.")
        return redirect("home")

    # S-ar putea să fi fost adăugat de admin între timp.
    if ProfilStudent.objects.filter(email__iexact=email, activ=True).exists():
        request.session.pop("cerere_cont", None)
        messages.success(request, "Ai deja cont. Autentifică-te din nou.")
        return redirect("home")

    in_asteptare = CerereCont.objects.filter(
        email__iexact=email, stare=CerereCont.IN_ASTEPTARE
    ).select_related("camin").first()

    context = {
        "email": email,
        "nume": date_sesiune.get("nume", ""),
        "prenume": date_sesiune.get("prenume", ""),
        "camine": Camin.objects.filter(accepta_cereri=True).order_by("nume"),
        "cerere": in_asteptare,
    }

    if request.method != "POST" or in_asteptare:
        return render(request, "cerere_cont.html", context)

    # `filter(id=...)` arunca ValueError pe orice nu e numar, inclusiv pe
    # optiunea goala „Alege caminul…"; aia e o completare lipsa, nu o eroare.
    ales = request.POST.get("camin", "").strip()
    camin = (Camin.objects.filter(id=ales, accepta_cereri=True).first()
             if ales.isdigit() else None)
    nume = request.POST.get("nume", "").strip().title()
    prenume = request.POST.get("prenume", "").strip().title()
    camera = request.POST.get("numar_camera", "").strip()
    telefon = normalizeaza_numar(request.POST.get("telefon"), request.POST.get("tara"))

    erori = []
    if not camin:
        erori.append("Alege căminul în care stai.")
    if not nume or not prenume:
        erori.append("Completează numele și prenumele.")
    if not camera:
        erori.append("Completează numărul camerei.")
    # Numarul e obligatoriu: fara el, studentul aprobat n-are cum sa afle.
    # Notificarea din aplicatie il asteapta, dar nu stie sa se uite acolo.
    if not telefon:
        erori.append(
            "Completează numărul de telefon. Pe el primești mesajul "
            "când contul tău e aprobat."
        )
    else:
        valid, mesaj = valideaza_numar(telefon)
        if not valid:
            erori.append(mesaj)

    if erori:
        for eroare in erori:
            messages.error(request, eroare)
        # Ce a apucat să scrie rămâne în formular.
        context.update({"nume": nume, "prenume": prenume, "numar_camera": camera,
                        "telefon": request.POST.get("telefon", ""),
                        "camin_ales": camin.id if camin else None})
        return render(request, "cerere_cont.html", context)

    try:
        cerere = CerereCont.objects.create(
            email=email, nume=nume, prenume=prenume, camin=camin,
            numar_camera=camera[:10], telefon=telefon[:15],
        )
    except IntegrityError:
        # A trimis cererea de două ori la rând; constrângerea din baza de date
        # a oprit-o pe a doua.
        messages.info(request, "Cererea ta a fost deja trimisă.")
        return redirect("cerere_cont")

    notifica_admini_cerere(cerere)
    logger.info(f"Cerere de cont noua: {email} pentru {camin.nume}.")
    messages.success(
        request,
        "Cererea a fost trimisă șefului de cămin. Vei putea intra în aplicație "
        "imediat ce o aprobă.",
    )
    return redirect("cerere_cont")


def _cerere_accesibila(request, cerere):
    """Super-adminul vede toate cererile; șeful de cămin doar pe ale lui."""
    if is_super_admin(request.user):
        return True
    admin = AdminCamin.objects.filter(email=request.user.email).first()
    return bool(admin and admin.camin_id and admin.camin_id == cerere.camin_id)


def _cerere_de_procesat(request, cerere_id):
    """
    Întoarce (cerere, raspuns_de_oprire).

    Cele două verificări — dreptul de acces și faptul că cererea e încă
    deschisă — sunt identice la aprobare și la respingere.
    """
    cerere = get_object_or_404(CerereCont, id=cerere_id)

    if not _cerere_accesibila(request, cerere):
        return cerere, render(request, "not_allowed.html", {
            "message": "Nu ai acces la cererile acestui cămin."
        })

    if cerere.stare != CerereCont.IN_ASTEPTARE:
        messages.info(request, "Cererea fusese deja rezolvată de altcineva.")
        return cerere, redirect("incarca_studenti")

    return cerere, None


@login_required
@require_POST
@only_admins
def aproba_cerere_cont(request, cerere_id):
    """Aprobarea creează contul pe aceeași cale ca adăugarea manuală."""
    cerere, oprire = _cerere_de_procesat(request, cerere_id)
    if oprire:
        return oprire

    with transaction.atomic():
        # Căutarea se face după email, nu după username: conturile create la
        # autentificare au username-ul fără domeniu, iar o căutare după
        # username ar crea un al doilea cont pentru același om.
        utilizator = User.objects.filter(email__iexact=cerere.email).order_by("id").first()
        if utilizator is None:
            utilizator = User(username=cerere.email)
        utilizator.email = cerere.email
        utilizator.first_name = cerere.prenume
        utilizator.last_name = cerere.nume
        utilizator.save()

        profil, _ = ProfilStudent.objects.update_or_create(
            utilizator=utilizator,
            defaults={
                "camin": cerere.camin,
                "numar_camera": cerere.numar_camera,
                "activ": True,
            },
        )
        if cerere.telefon:
            profil.telefon = cerere.telefon
            profil.save(update_fields=["telefon"])

        cerere.stare = CerereCont.APROBATA
        cerere.procesat_la = timezone.now()
        cerere.procesat_de = request.user.email
        cerere.save(update_fields=["stare", "procesat_la", "procesat_de"])

    # Anuntul pleaca dupa ce contul e scris de-a binelea: altfel un WhatsApp
    # care esueaza ar anula crearea contului, iar studentul ar ramane fara si
    # cu cererea inchisa. Notificarea din aplicatie il asteapta oricum la
    # prima autentificare, chiar daca nu si-a lasat numarul.
    notifica_student(
        profil,
        "cerere_aprobata",
        {
            "1": cerere.prenume or cerere.nume,
            "2": cerere.camin.nume,
            "3": cerere.numar_camera or "-",
        },
        titlu="Cererea ta a fost aprobată",
        corp=(
            f"Ai acum cont pentru căminul {cerere.camin.nume}"
            f"{', camera ' + cerere.numar_camera if cerere.numar_camera else ''}. "
            "Poți rezerva o mașină."
        ),
        link="/dashboard/student/",
    )

    messages.success(
        request,
        f"{cerere.nume_complet} are acum cont în {cerere.camin.nume}, camera "
        f"{cerere.numar_camera or '—'}.",
    )
    return redirect("incarca_studenti")


@login_required
@require_POST
@only_admins
def respinge_cerere_cont(request, cerere_id):
    """Respingerea nu creează și nu șterge nimic; cererea rămâne ca istoric."""
    cerere, oprire = _cerere_de_procesat(request, cerere_id)
    if oprire:
        return oprire

    cerere.stare = CerereCont.RESPINSA
    cerere.motiv = request.POST.get("motiv", "").strip()[:500]
    cerere.procesat_la = timezone.now()
    cerere.procesat_de = request.user.email
    cerere.save(update_fields=["stare", "motiv", "procesat_la", "procesat_de"])

    messages.info(request, f"Cererea lui {cerere.nume_complet} a fost respinsă.")
    return redirect("incarca_studenti")


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



@login_required
def adauga_telefon(request):
    # Accept doar POST; altfel, întoarce utilizatorul înapoi.
    if request.method != "POST":
        return inapoi_la(request, "home")

    # 1) Colectare & normalizare
    telefon_raw = (request.POST.get("telefon") or "").strip()
    tara = (request.POST.get("tara") or "ro").strip().lower()

    # Curățare + prefix de țară, aceeași regulă ca la cererea de cont.
    num = normalizeaza_numar(telefon_raw, tara)

    # Validarea tine cont si de lungimea ceruta de prefixul de tara: regula
    # generala E.164 lasa sa treaca un numar romanesc cu o cifra lipsa, iar
    # acela nu primeste niciodata mesaje.
    valid, eroare = valideaza_numar(num)
    if not valid:
        messages.error(request, eroare)
        return inapoi_la(request, "home")

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
    return inapoi_la(request, "home")



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



@login_required
@require_POST
def save_fcm_token(request):
    """Salveaza token-ul de notificari al browserului pentru studentul logat."""
    try:
        date = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Cerere invalidă"}, status=400)

    token = (date.get("token") or "").strip()
    if not token:
        return JsonResponse({"error": "Token lipsă"}, status=400)

    profil = ProfilStudent.objects.filter(utilizator=request.user).first()
    if not profil:
        return JsonResponse({"error": "Profil inexistent"}, status=404)

    profil.fcm_token = token
    profil.save(update_fields=["fcm_token"])
    logger.info(f"Token push salvat pentru {profil.email}")
    return JsonResponse({"success": True})



@login_required
def selecteaza_camin(request):
    if request.method == "POST":
        camin_id = request.POST.get("camin_id")
        if camin_id:
            request.session["camin_selectat"] = camin_id
    return inapoi_la(request, "dashboard_admin_camin")


@login_required
def api_dashboard(request):
    return render(request, 'api/dashboard.html')