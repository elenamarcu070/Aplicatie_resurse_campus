# booking/utils.py
import json
import re

from twilio.rest import Client
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def trimite_sms(numar, mesaj):
    """Trimite SMS prin Twilio cu expeditor alfanumeric WASHTUIASI."""
    if not numar:
        logger.warning("❌ Lipsă număr destinatar.")
        return
    if not numar.startswith("+"):
        logger.warning(f"❌ Număr fără prefix internațional: {numar}")
        return

    try:
        logger.info(f"📤 Trimit SMS către {numar} cu sender WASHTUIASI")
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            to=numar,
            messaging_service_sid=settings.TWILIO_MESSAGING_SERVICE_SID,  # ← nu 'WASHTUIASI'
            body=mesaj,
        )
        logger.info(f"✅ Twilio: SID={msg.sid}, STATUS={msg.status}")
    except Exception as e:
        logger.error(f"💥 Eroare Twilio SMS: {e}")

#"twilio-domain-verification=aeef8bb394851e10b5e36ff12d8721f3"

def _url_status_callback():
    """Adresa pe care Twilio o apeleaza cand stie starea finala a mesajului."""
    domeniu = (settings.SITE_DOMAIN or "").rstrip("/")
    if not domeniu:
        return None
    from django.urls import reverse
    return f"{domeniu}{reverse('twilio_status')}"


def valideaza_numar(numar):
    """
    Intoarce (valid, mesaj_de_eroare).

    Regula generala E.164 accepta 9-15 cifre, ceea ce pentru un numar romanesc
    lasa sa treaca si unul caruia ii lipseste o cifra. Numerele astfel salvate
    nu primesc niciodata mesaje, iar Twilio raspunde cu eroarea 21211.
    """
    if not re.fullmatch(r"\+\d{9,15}", numar or ""):
        return False, "Numărul introdus nu este valid. Verifică și încearcă din nou."
    if numar.startswith("+40") and not re.fullmatch(r"\+40\d{9}", numar):
        return False, ("Un număr de telefon românesc are 9 cifre după prefixul +40. "
                       "Verifică dacă nu lipsește sau nu e în plus o cifră.")
    if numar.startswith("+373") and not re.fullmatch(r"\+373\d{8}", numar):
        return False, ("Un număr de telefon din Republica Moldova are 8 cifre după "
                       "prefixul +373. Verifică numărul.")
    return True, ""


# Prefixele acceptate la introducerea unui număr fără prefix internațional.
PREFIXE_TARA = {
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


def normalizeaza_numar(telefon_brut, tara="ro"):
    """
    Curăță un număr scris de om și îi pune prefixul de țară dacă lipsește.

    Studenții scriu numărul cu spații, liniuțe sau începând cu 0. Fără pasul
    ăsta, validarea ar respinge numere perfect bune.
    """
    numar = re.sub(r"[^\d+]", "", (telefon_brut or "").strip())
    if not numar:
        return ""
    if not numar.startswith("+"):
        prefix = PREFIXE_TARA.get((tara or "ro").strip().lower(), "+40")
        numar = prefix + numar.lstrip("0")
    return numar


def trimite_whatsapp(destinatar, template_name, variabile, profil=None):
    """
    Trimite o notificare WhatsApp si inregistreaza incercarea in NotificareLog.

    Intoarce randul de jurnal. Nu arunca exceptii: o notificare care nu pleaca
    nu trebuie sa opreasca actiunea care a declansat-o.

    Starea intoarsa aici este cea initiala („queued"). Starea finala vine mai
    tarziu, prin webhook-ul de status, si se scrie peste.
    """
    content_sid = (settings.WHATSAPP_TEMPLATES or {}).get(template_name)
    if not content_sid:
        logger.error(f"Sablon WhatsApp necunoscut sau neconfigurat: {template_name}")
        return None

    destinatar = (destinatar or "").replace(" ", "")
    variabile = {str(k): str(v) for k, v in variabile.items()}

    jurnal = NotificareLog.objects.create(
        profil=profil, destinatar=destinatar, sablon=template_name
    )

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        argumente = {
            "from_": f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            "to": f"whatsapp:{destinatar}",
            "content_sid": content_sid,
            "content_variables": json.dumps(variabile),
        }
        callback = _url_status_callback()
        if callback:
            argumente["status_callback"] = callback

        mesaj = client.messages.create(**argumente)
        jurnal.message_sid = mesaj.sid or ""
        jurnal.stare = mesaj.status or "queued"
        jurnal.save(update_fields=["message_sid", "stare", "actualizat_la"])
        logger.info(
            f"Notificare {template_name} trimisa: SID={mesaj.sid} stare={mesaj.status}"
        )
    except Exception as e:
        jurnal.stare = NotificareLog.EROARE_TRIMITERE
        jurnal.detaliu = str(e)[:500]
        jurnal.save(update_fields=["stare", "detaliu", "actualizat_la"])
        logger.error(f"Eroare la trimiterea notificarii {template_name}: {e}")

    return jurnal


from booking.models import Camin, AdminCamin, NotificareLog, ProfilStudent


def _cu_telefon(interogare):
    return interogare.exclude(telefon__isnull=True).exclude(telefon="")


def destinatari_cerere_cont(camin):
    """
    Cine trebuie anunțat că s-a depus o cerere de cont pentru căminul dat:
    administratorii căminului și super-adminii.

    Sunt lăsați deoparte cei fără telefon — nu se poate trimite nimic către ei —
    și cei cărora li s-a scos `primeste_notificari`: un cămin are un singur șef
    responsabil, ceilalți au cont doar ca să vadă aplicația. Cererea apare
    oricum în pagina de studenți, la toți.
    """
    from django.db.models import Q

    randuri = _cu_telefon(
        AdminCamin.objects.filter(
            Q(camin=camin) | Q(is_super_admin=True), primeste_notificari=True
        )
    ).distinct().order_by("id")

    # Acelasi om poate avea mai multe randuri de admin — adresa institutionala
    # si cea personala, sau doua camine — cu acelasi numar de telefon.
    # `distinct()` le vede ca randuri diferite, iar omul primea acelasi mesaj
    # de doua ori. Destinatarul e numarul, nu randul.
    vazute = set()
    destinatari = []
    for rand in randuri:
        numar = (rand.telefon or "").replace(" ", "")
        if numar in vazute:
            continue
        vazute.add(numar)
        destinatari.append(rand)
    return destinatari


def sefi_de_camin():
    """
    Șefii de afișat studentului pe pagina de acces interzis, câte unul de cămin.

    Se iau din baza de date, nu scriși de mână în șablon: altfel fiecare
    schimbare de șef la început de an cere o modificare de cod. Super-adminii
    nu apar — ei nu sunt persoana de contact a unui cămin anume.
    """
    return list(
        _cu_telefon(
            AdminCamin.objects.filter(
                camin__isnull=False,
                camin__accepta_cereri=True,
                primeste_notificari=True,
                is_super_admin=False,
            )
        )
        .select_related("camin")
        .order_by("camin__nume", "id")
    )


def notifica_admini_cerere(cerere):
    """
    Anunță pe WhatsApp adminii care au de-a face cu o cerere nouă de cont.

    Nu aruncă excepții: mesajul e o curtoazie, cererea e deja salvată și
    vizibilă în listă, deci un WhatsApp care nu pleacă nu trebuie să-i arate
    studentului un ecran de eroare.
    """
    trimise = []
    for admin in destinatari_cerere_cont(cerere.camin):
        try:
            jurnal = trimite_whatsapp(
                admin.telefon,
                "cerere_cont_noua",
                {
                    "1": cerere.nume_complet or cerere.email,
                    "2": cerere.camin.nume,
                    "3": cerere.numar_camera or "-",
                    "4": cerere.email,
                },
            )
            if jurnal:
                trimise.append(jurnal)
        except Exception as e:
            logger.error(f"Nu am putut anunta adminul {admin.email} de cererea {cerere.id}: {e}")

    if not trimise:
        logger.warning(
            f"Cererea de cont {cerere.id} ({cerere.email}, {cerere.camin.nume}) "
            "nu a ajuns pe WhatsApp la niciun admin."
        )
    return trimise

def masca_email(email):
    """
    `an•••••@gmail.com` — destul cât omul să-și recunoască propria adresă,
    nu cât să afle altcineva adresa unui coleg cu nume asemănător.
    """
    local, separator, domeniu = (email or "").partition("@")
    if not separator:
        return ""
    vizibil = local[:2] if len(local) > 3 else local[:1]
    return f"{vizibil}{'•' * max(3, len(local) - len(vizibil))}@{domeniu}"


def gaseste_cont_asemanator(email, prenume="", nume=""):
    """
    Caută un cont activ care pare să fie al aceleiași persoane, pe altă adresă.

    Bobocii se înscriu cu adresa personală și primesc adresa instituțională
    în anul următor. Când încearcă să intre cu cea nouă, aplicația nu-i
    cunoaște și ei depun o cerere — deși au deja cont. Așa îi putem trimite
    înapoi la adresa lor, în loc să ajungă pe un drum ocolit.

    Întoarce (profil, motiv) sau (None, ""). Nu întoarce nimic când sunt mai
    mulți candidați: o potrivire nesigură e mai rea decât niciuna.
    """
    from booking.import_studenti import cheie_nume

    email = (email or "").strip().lower()
    if "@" not in email:
        return None, ""

    local = email.split("@")[0]
    activi = ProfilStudent.objects.filter(activ=True).exclude(email__iexact=email)

    # 1. Aceeași parte dinaintea lui @, alt domeniu: ana.pop@gmail.com și
    #    ana.pop@student.tuiasi.ro. Semnalul cel mai clar.
    dupa_local = list(activi.filter(email__istartswith=f"{local}@")[:2])
    if len(dupa_local) == 1:
        return dupa_local[0], "local"

    # 2. Același nume complet, scris oricum. Numai dacă e unic: doi omonimi
    #    nu pot fi deosebiți, iar o potrivire greșită ar arăta adresa altuia.
    if not (prenume or nume):
        return None, ""

    cautat = cheie_nume(nume, prenume)
    potriviri = [
        p for p in activi.only("id", "email", "nume", "prenume", "camin")
        if cheie_nume(p.nume, p.prenume) == cautat
    ]
    if len(potriviri) == 1:
        return potriviri[0], "nume"

    return None, ""


def get_camin_curent(request):
    """
    Returnează căminul asociat utilizatorului logat:
     - Super-admin  → căminul selectat din dropdown (sesiune)
     - Admin cămin  → căminul asociat contului
     - Student      → căminul în care e cazat
     - Altfel       → None
    """
    user = request.user
    if not user.is_authenticated:
        return None

    # Verificăm dacă este admin
    admin = AdminCamin.objects.filter(email=user.email).first()
    if admin:
        if admin.is_super_admin:
            camin_id = request.session.get("camin_selectat")
            return Camin.objects.filter(id=camin_id).first() if camin_id else None
        return admin.camin

    # Verificăm dacă este student
    profil = ProfilStudent.objects.filter(utilizator=user).first()
    if profil and profil.camin:
        return profil.camin

    return None
