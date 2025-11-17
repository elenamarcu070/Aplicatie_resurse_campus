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
        return self.suspendat_pana_la and self.suspendat_pana_la >= date.today()



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
