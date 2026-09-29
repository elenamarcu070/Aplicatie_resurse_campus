from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta,date
from django.utils import timezone
from django.forms import ValidationError

# ------------------------------------------
# CĂMIN
# ------------------------------------------

class Camin(models.Model):
    nume = models.CharField(max_length=100, unique=True)
    durata_interval = models.PositiveIntegerField(default=2, help_text="Durata fiecărui interval de rezervare (ore)")

    def __str__(self):
        return self.nume


class AdminCamin(models.Model):
    email = models.EmailField(unique=True)
    camin = models.ForeignKey(Camin, on_delete=models.CASCADE, null=True, blank=True)

    telefon = models.CharField(max_length=20, blank=True, null=True)
    is_super_admin = models.BooleanField(default=False)  # 🔥 nou

    def __str__(self):
        return f"{self.email} — {self.camin.nume if self.camin else 'Super Admin'}"


# ------------------------------------------
# MAȘINĂ DE SPĂLAT 
# ------------------------------------------
class Masina(models.Model):

    camin = models.ForeignKey(Camin, on_delete=models.CASCADE)
    nume = models.CharField(max_length=100) 
    activa = models.BooleanField(default=True) 

    def __str__(self):
        return f"{self.nume} ({self.camin.nume})"
# ------------------------------------------
# PROGRAM SLOTURI MAȘINI
# ------------------------------------------
class ProgramMasina(models.Model):
    masina = models.ForeignKey(Masina, on_delete=models.CASCADE)
    ora_start = models.TimeField()
    ora_end = models.TimeField()

    def __str__(self):
        return f"{self.masina.nume}: {self.ora_start}-{self.ora_end}"
    

# ------------------------------------------
# USCATOR
# ------------------------------------------
class Uscator(models.Model):
    nume = models.CharField(max_length=100)
    camin = models.ForeignKey('Camin', on_delete=models.CASCADE)
    activa = models.BooleanField(default=True)  # activă sau dezactivată (ex: stricată)

    def __str__(self):
        return f"{self.nume} ({self.camin.nume})"

# ------------------------------------------
# PROGRAM SLOTURI USCATOARE
# ------------------------------------------
class ProgramUscator(models.Model):
    uscator = models.ForeignKey('Uscator', on_delete=models.CASCADE)
    ora_start = models.TimeField()
    ora_end = models.TimeField()

    def __str__(self):
        return f"{self.uscator.nume} - {self.ora_start} - {self.ora_end}"

# ------------------------------------------
# PROFIL STUDENT (EXTINDERE USER)
# ------------------------------------------
class ProfilStudent(models.Model):
    utilizator = models.OneToOneField(User, on_delete=models.CASCADE)
    camin = models.ForeignKey(Camin, on_delete=models.SET_NULL, null=True, blank=True)
    email = models.EmailField(null=True)  
    nume = models.CharField(max_length=50, blank=True, null=True)
    prenume = models.CharField(max_length=50, blank=True, null=True)
    numar_camera = models.CharField(max_length=10, blank=True, null=True)
    suspendat_pana_la = models.DateField(null=True, blank=True)

    telefon = models.CharField(max_length=15, blank=True, null=True)
    fcm_token = models.TextField(null=True, blank=True)

    # Studenții care pleacă din cămin sunt marcați inactivi, nu șterși:
    # ștergerea contului ar duce, prin CASCADE, la pierderea întregului lor
    # istoric de rezervări. Un student inactiv nu se mai poate autentifica.
    activ = models.BooleanField(default=True)


    def clean(self):
        if not self.utilizator.email:
            raise ValidationError({'utilizator': 'Emailul este obligatoriu!'})
        
    def save(self, *args, **kwargs):
        if self.utilizator:
            self.email = self.utilizator.email
            self.nume = self.utilizator.last_name
            self.prenume = self.utilizator.first_name
        super().save(*args, **kwargs)

    def __str__(self):
        return self.utilizator.email
    
    def este_blocat(self):
        return self.suspendat_pana_la and self.suspendat_pana_la >= timezone.localdate()



# ------------------------------------------
# REZERVARE
# ------------------------------------------
class Rezervare(models.Model):
    PRIORITATE_CHOICES = [
        (1, 'Maximă'),     # Roșu - Prima rezervare
        (2, 'Înaltă'),     # Gri - A doua rezervare
        (3, 'Medie'),      # Albastru - A treia rezervare
        (4, 'Scăzută'),    # Maro deschis - A patra rezervare
    ]

    utilizator = models.ForeignKey(User, on_delete=models.CASCADE)
    masina = models.ForeignKey(Masina, on_delete=models.CASCADE)
    data_rezervare = models.DateField()
    ora_start = models.TimeField()
    ora_end = models.TimeField()
    nivel_prioritate = models.IntegerField(choices=PRIORITATE_CHOICES, default=1)
    anulata = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def get_rezervari_saptamana(user, data):
        start_sapt = data - timedelta(days=data.weekday())
        end_sapt = start_sapt + timedelta(days=6)
        return Rezervare.objects.filter(
            utilizator=user,
            data_rezervare__range=(start_sapt, end_sapt),
            anulata=False
        ).order_by('created_at')
    
    @staticmethod
    def actualizeaza_prioritati(user, data_rezervare):
        start_sapt = data_rezervare - timedelta(days=data_rezervare.weekday())
        end_sapt = start_sapt + timedelta(days=6)
        
        # Ia toate rezervările active din săptămână, ordonate după dată și oră
        rezervari = Rezervare.objects.filter(
            utilizator=user,
            data_rezervare__range=(start_sapt, end_sapt),
            anulata=False
        ).order_by('data_rezervare', 'ora_start')

        # Actualizează nivelul de prioritate pentru fiecare rezervare
        for index, rezervare in enumerate(rezervari, 1):
            if rezervare.nivel_prioritate != index:
                rezervare.nivel_prioritate = index
                rezervare.save()


    class Meta:
        ordering = ['data_rezervare', 'ora_start']
        constraints = [
            # Ultima linie de apărare împotriva dublei rezervări: chiar dacă două
            # cereri simultane trec de verificările din view, baza de date
            # respinge a doua inserare pe același slot activ.
            models.UniqueConstraint(
                fields=['masina', 'data_rezervare', 'ora_start'],
                condition=models.Q(anulata=False),
                name='rezervare_unica_pe_slot_activ',
            ),
        ]

# ------------------------------------------
# AVERTISMENTE
# ------------------------------------------
class Avertisment(models.Model):
    utilizator = models.ForeignKey(User, on_delete=models.CASCADE)
    data = models.DateField(auto_now_add=True)
    motiv = models.TextField(default="Rezervare neutilizată")
    
    def __str__(self):
        return f"Avertisment pentru {self.utilizator.email} - {self.data}"

# models.py
class IntervalDezactivare(models.Model):
    masina = models.ForeignKey(Masina, on_delete=models.CASCADE, related_name="intervale_dezactivate")
    data = models.DateField()
    ora_start = models.TimeField()
    ora_end = models.TimeField()


# ------------------------------------------
# JURNAL DE NOTIFICĂRI
# ------------------------------------------
class NotificareLog(models.Model):
    """
    Urma unei notificări trimise prin Twilio.

    Fără asta, aplicația nu are cum să știe dacă un mesaj a ajuns: Twilio
    stabilește livrarea asincron, iar apelul de trimitere se întoarce cu
    starea „queued". Starea finală vine mai târziu, prin webhook-ul de status,
    și se scrie aici.
    """

    # Stările sunt cele raportate de Twilio, plus una proprie pentru cazul în
    # care apelul către Twilio nici nu a reușit.
    EROARE_TRIMITERE = "eroare_trimitere"
    STARI_ESUATE = ("undelivered", "failed", EROARE_TRIMITERE)

    WHATSAPP = "whatsapp"
    PUSH = "push"
    CANALE = [(WHATSAPP, "WhatsApp"), (PUSH, "Push în browser")]

    profil = models.ForeignKey(
        ProfilStudent, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="notificari",
    )
    canal = models.CharField(max_length=16, choices=CANALE, default=WHATSAPP)
    destinatar = models.CharField(max_length=20)
    sablon = models.CharField(max_length=64)
    message_sid = models.CharField(max_length=64, blank=True, db_index=True)
    stare = models.CharField(max_length=24, default="in_asteptare")
    cod_eroare = models.CharField(max_length=16, blank=True)
    detaliu = models.TextField(blank=True)
    creat_la = models.DateTimeField(auto_now_add=True)
    actualizat_la = models.DateTimeField(auto_now=True)

    class Meta:
        # `-id` departajeaza notificarile trimise in aceeasi secunda, altfel
        # „ultima notificare" ar fi imprevizibila.
        ordering = ["-creat_la", "-id"]

    def __str__(self):
        return f"{self.canal}: {self.sablon} → {self.destinatar} ({self.stare})"

    @property
    def a_esuat(self):
        return self.stare in self.STARI_ESUATE

    def explicatie(self):
        """Ce să-i spui studentului, pe înțelesul lui."""
        if self.canal == self.PUSH:
            return ("Notificarea din browser nu a putut fi livrată. Probabil ai "
                    "schimbat browserul sau ai retras permisiunea.")
        if self.cod_eroare == "63024":
            return ("Numărul nu poate primi mesaje pe WhatsApp. Verifică dacă ai "
                    "WhatsApp instalat pe acest număr și dacă ai acceptat termenii aplicației.")
        if self.cod_eroare == "21211":
            return "Numărul de telefon pare incomplet sau greșit."
        if self.stare in self.STARI_ESUATE:
            return "Mesajul nu a putut fi livrat la acest număr."
        return ""


# ------------------------------------------
# NOTIFICĂRI ÎN APLICAȚIE
# ------------------------------------------
class Notificare(models.Model):
    """
    Notificarea așa cum o vede studentul în aplicație.

    `NotificareLog` spune dacă mesajul a plecat pe WhatsApp sau push și dacă a
    ajuns; aici stă evenimentul în sine, o singură dată, indiferent pe câte
    canale a fost trimis. Așa rămâne vizibil chiar dacă studentul a ratat
    notificarea de sistem sau nu are WhatsApp.
    """

    profil = models.ForeignKey(
        ProfilStudent, on_delete=models.CASCADE, related_name="notificari_primite"
    )
    titlu = models.CharField(max_length=120)
    corp = models.TextField(blank=True)
    link = models.CharField(max_length=200, blank=True)
    citita = models.BooleanField(default=False)
    creat_la = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creat_la", "-id"]

    def __str__(self):
        return f"{self.titlu} → {self.profil.email}"
