"""
Importul listelor de studenți din Excel.

Importul este în doi pași: întâi se citește fișierul și se construiește un plan
(cine se creează, cine se actualizează, cine se dezactivează), apoi planul e
arătat administratorului și abia după confirmare se scrie în baza de date.

Studenții care pleacă din cămin nu se șterg niciodată: ștergerea contului ar
duce, prin `on_delete=CASCADE`, la dispariția întregului lor istoric de
rezervări. Sunt doar marcați inactivi, ceea ce se poate anula oricând.
"""

import re
from dataclasses import dataclass, field

import pandas as pd
from django.contrib.auth.models import User
from django.db import transaction

from booking.models import Camin, ProfilStudent

COLOANE_OBLIGATORII = ["email", "nume", "prenume", "camin", "camera"]

# Suficient de permisiv cât să nu respingă adrese valide, dar sa prinda
# celulele goale si textul care nu e nici pe departe o adresa.
TIPAR_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


@dataclass
class RandStudent:
    """Un rând valid din fișier, deja normalizat."""

    linie: int
    email: str
    nume: str
    prenume: str
    camin: str
    camera: str


@dataclass
class Plan:
    """Ce urmează să se întâmple, dacă importul e confirmat."""

    de_creat: list = field(default_factory=list)
    de_actualizat: list = field(default_factory=list)
    neschimbate: list = field(default_factory=list)
    de_reactivat: list = field(default_factory=list)
    de_dezactivat: list = field(default_factory=list)
    erori: list = field(default_factory=list)
    avertismente: list = field(default_factory=list)
    camine_in_fisier: list = field(default_factory=list)

    @property
    def randuri_valide(self):
        return len(self.de_creat) + len(self.de_actualizat) + len(self.neschimbate)

    @property
    def are_de_lucru(self):
        return bool(
            self.de_creat or self.de_actualizat or self.de_dezactivat or self.de_reactivat
        )

    @property
    def total_afectati(self):
        return len(self.de_creat) + len(self.de_actualizat) + len(self.de_reactivat)


def _text(valoare):
    """Celulele goale ajung din pandas ca NaN, deci ca textul 'nan'."""
    if valoare is None:
        return ""
    text = str(valoare).strip()
    if text.lower() in ("nan", "nat", "none"):
        return ""
    return text


def citeste_fisier(cale):
    """
    Citește fișierul Excel și întoarce (randuri_valide, erori).

    Nu atinge baza de date.
    """
    df = pd.read_excel(cale)
    if df.empty:
        raise ValueError("Fișierul este gol sau nu conține date valide.")

    df.columns = df.columns.str.strip().str.lower()
    lipsa = [c for c in COLOANE_OBLIGATORII if c not in df.columns]
    if lipsa:
        raise ValueError(
            "Fișierul trebuie să conțină coloanele: "
            + ", ".join(COLOANE_OBLIGATORII)
            + f". Lipsesc: {', '.join(lipsa)}."
        )

    randuri = []
    erori = []
    vazute = {}

    for index, row in df.iterrows():
        # +2: pandas numără de la 0, iar prima linie din Excel e antetul.
        linie = index + 2
        email = _text(row["email"]).lower()
        nume = _text(row["nume"]).title()
        prenume = _text(row["prenume"]).title()
        camin = _text(row["camin"]).upper()
        camera = _text(row["camera"])

        if not email:
            erori.append((linie, "Lipsește adresa de email."))
            continue
        if not TIPAR_EMAIL.match(email):
            erori.append((linie, f"Adresa „{email}” nu este validă."))
            continue
        if not camin:
            erori.append((linie, f"Lipsește căminul pentru {email}."))
            continue
        if email in vazute:
            erori.append(
                (linie, f"Adresa „{email}” apare de mai multe ori (prima dată pe linia {vazute[email]}).")
            )
            continue

        vazute[email] = linie
        randuri.append(
            RandStudent(
                linie=linie,
                email=email,
                nume=nume,
                prenume=prenume,
                camin=camin,
                camera=camera,
            )
        )

    return randuri, erori


def construieste_plan(randuri, erori=None):
    """
    Compară rândurile din fișier cu baza de date și întoarce planul.

    Candidații la dezactivare sunt calculați întotdeauna, ca administratorul
    să vadă numărul înainte de a decide. Nu scrie nimic.
    """
    plan = Plan(erori=list(erori or []))
    plan.camine_in_fisier = sorted({r.camin for r in randuri})

    emailuri = [r.email for r in randuri]
    profiluri = {
        p.email.lower(): p
        for p in ProfilStudent.objects.filter(email__in=emailuri).select_related("camin")
        if p.email
    }

    for rand in randuri:
        domeniu = rand.email.split("@")[-1]
        if "." not in domeniu:
            plan.avertismente.append(
                (rand.email, f"Domeniul „{domeniu}” nu pare valid — studentul nu se va putea autentifica.")
            )

        profil = profiluri.get(rand.email)
        if profil is None:
            plan.de_creat.append(rand)
            continue

        modificari = {}
        if (profil.camin.nume if profil.camin else "") != rand.camin:
            modificari["cămin"] = (profil.camin.nume if profil.camin else "—", rand.camin)
        if (profil.numar_camera or "") != rand.camera:
            modificari["cameră"] = (profil.numar_camera or "—", rand.camera)
        if (profil.nume or "") != rand.nume:
            modificari["nume"] = (profil.nume or "—", rand.nume)
        if (profil.prenume or "") != rand.prenume:
            modificari["prenume"] = (profil.prenume or "—", rand.prenume)

        if not profil.activ:
            plan.de_reactivat.append(rand)

        if modificari:
            plan.de_actualizat.append((rand, modificari))
        elif profil.activ:
            plan.neschimbate.append(rand)

    if plan.camine_in_fisier:
        plan.de_dezactivat = list(
            ProfilStudent.objects.filter(
                camin__nume__in=plan.camine_in_fisier, activ=True
            )
            .exclude(email__in=emailuri)
            .select_related("camin")
            .order_by("camin__nume", "nume", "prenume")
        )

    return plan


@transaction.atomic
def aplica_plan(randuri, dezactiveaza=False):
    """
    Scrie în baza de date și întoarce planul efectiv aplicat.

    Se recalculează planul aici, ca să nu depindem de datele trimise de
    browser și ca cifrele raportate să fie cele chiar aplicate.
    """
    plan = construieste_plan(randuri)

    camine = {}
    for nume_camin in plan.camine_in_fisier:
        camine[nume_camin], _ = Camin.objects.get_or_create(nume=nume_camin)

    for rand in randuri:
        # Cautarea se face dupa email, nu dupa username: conturile create la
        # login au username-ul fara domeniu, iar o cautare dupa username ar
        # crea un al doilea cont pentru acelasi om.
        utilizator = User.objects.filter(email__iexact=rand.email).order_by("id").first()
        if utilizator is None:
            profil_existent = (
                ProfilStudent.objects.filter(email__iexact=rand.email)
                .select_related("utilizator")
                .order_by("id")
                .first()
            )
            utilizator = profil_existent.utilizator if profil_existent else None

        if utilizator is None:
            utilizator = User(username=rand.email)

        utilizator.email = rand.email
        utilizator.first_name = rand.prenume
        utilizator.last_name = rand.nume
        utilizator.save()

        # ProfilStudent.save() isi ia email/nume/prenume din utilizator, deci
        # utilizatorul trebuie salvat inainte.
        ProfilStudent.objects.update_or_create(
            utilizator=utilizator,
            defaults={
                "camin": camine[rand.camin],
                "numar_camera": rand.camera,
                "activ": True,
            },
        )

    if dezactiveaza and plan.de_dezactivat:
        ProfilStudent.objects.filter(
            id__in=[p.id for p in plan.de_dezactivat]
        ).update(activ=False)
    elif not dezactiveaza:
        # Nu au fost dezactivați, deci nu apar în ce raportăm ca aplicat.
        plan.de_dezactivat = []

    return plan
