from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta,date
from django.utils import timezone
from django.forms import ValidationError

# ------------------------------------------
# CĂMIN
# ------------------------------------------

class Camin(models.Model):
    nume = models.CharField(max_length=50)

    def __str__(self):
        return self.nume


class AdminCamin(models.Model):
    camin = models.ForeignKey(Camin, on_delete=models.CASCADE, related_name="admini")
    email = models.EmailField(max_length=100)

    def __str__(self):
        return f"{self.email} - {self.camin.nume}"
# ------------------------------------------
# MAȘINĂ DE SPĂLAT 
# ------------------------------------------
class Masina(models.Model):

    camin = models.ForeignKey(Camin, on_delete=models.CASCADE)
    nume = models.CharField(max_length=100)  # Ex: "Mașina 1", "Uscător 2"
    activa = models.BooleanField(default=True)  # activă sau dezactivată (ex: stricată)

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
    # Legătura cu Căminul
    # Aceasta este o legătură către modelul Camin
    nume = models.CharField(max_length=100)
    camin = models.ForeignKey('Camin', on_delete=models.CASCADE)
    # Câmp pentru a marca dacă uscătorul este activ sau dezactivat
    # Acest câmp poate fi util pentru a indica dacă uscătorul este
    # disponibil pentru utilizare sau dacă este închis pentru reparații
    # sau întreținere
    # De exemplu, dacă uscătorul este activ, atunci utilizatorii
    activa = models.BooleanField(default=True)  # activă sau dezactivată (ex: stricată)

    def __str__(self):
        return f"{self.nume} ({self.camin.nume})"

# ------------------------------------------
# PROGRAM SLOTURI USCATOARE
# ------------------------------------------
class ProgramUscator(models.Model):
    # Legătura cu uscătorul
    # Aceasta este o legătură către modelul Uscator
    uscator = models.ForeignKey('Uscator', on_delete=models.CASCADE)
    # Ora de început și de sfârșit pentru programul uscătorului
    # Acestea pot fi diferite de cele ale mașinilor de spălat
    # deoarece uscătoarele pot avea un program diferit
    ora_start = models.TimeField()
    # Ora de sfârșit pentru programul uscătorului
    # Acest câmp este util pentru a defini intervalul de timp
    # în care uscătorul este disponibil pentru utilizare
    # De exemplu, dacă uscătorul este disponibil de la 8:00 la 20:00,
    # atunci ora_start va fi 08:00 și ora_end va fi 20:00

    ora_end = models.TimeField()

    # Metoda __str__ pentru a afișa informații despre programul uscătorului
    # Aceasta va returna o reprezentare a programului   
    # sub forma "Nume Uscător - Ora Start - Ora End"
    # Aceasta este utilă pentru a afișa programul în interfața de utilizator
    # sau în rapoarte, astfel încât utilizatorii să poată vedea
    # rapid când este disponibil uscătorul  
    def __str__(self):
        return f"{self.uscator.nume} - {self.ora_start} - {self.ora_end}"

# ------------------------------------------
# PROFIL STUDENT (EXTINDERE USER)
# ------------------------------------------

class ProfilStudent(models.Model):
    utilizator = models.OneToOneField(User, on_delete=models.CASCADE)
    # Legătura cu Căminul
    camin = models.ForeignKey(Camin, on_delete=models.SET_NULL, null=True, blank=True)
    # Câmpuri suplimentare pentru profilul studentului
    # Emailul este preluat din User, dar îl adăugăm aici pentru validare
    # și pentru a putea fi folosit în formulare fără a accesa User direct

    email = models.EmailField(null=True)  # adaugă acest câmp temporar
    # Nume și prenume pot fi opționale, dar pot fi utile pentru afișare
    # în interfața de utilizator sau pentru rapoarte
    # Acestea pot fi preluate din User, dar le adăugăm aici pentru claritate
    # și pentru a putea fi modificate independent de User
    nume = models.CharField(max_length=50, blank=True, null=True)

    # Prenumele poate fi util pentru a personaliza mesajele
    # sau pentru a afișa numele complet al studentului  
    # în interfața de utilizator
    # Acestea pot fi preluate din User, dar le adăugăm aici pentru claritate
    # și pentru a putea fi modificate independent de User

    prenume = models.CharField(max_length=50, blank=True, null=True)
    # Câmp pentru a stoca numărul camerei studentului
    # Acest câmp poate fi util pentru a identifica camera
    # în care locuiește studentul, mai ales dacă există mai multe camere
    # în același cămin sau pentru a facilita rezervările
    numar_camera = models.CharField(max_length=10, blank=True, null=True)
    # Câmp pentru a marca dacă studentul este suspendat
    # de la rezervări (de exemplu, pentru neplată sau abuz)
    suspendat_pana_la = models.DateField(null=True, blank=True)

    def clean(self):
        if not self.utilizator.email:
            raise ValidationError({'utilizator': 'Emailul este obligatoriu!'})




    def save(self, *args, **kwargs):
        # Asigură-te că email-ul este sincronizat cu modelul User
        if self.utilizator:
            self.email = self.utilizator.email
            self.nume = self.utilizator.last_name
            self.prenume = self.utilizator.first_name
        super().save(*args, **kwargs)

    def __str__(self):
        return self.utilizator.email


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
        """
        Actualizează nivelurile de prioritate pentru toate rezervările unui utilizator
        din săptămâna specificată, în ordine cronologică
        """
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

    @staticmethod
    def este_blocat(utilizator):
        avertismente_recente = Avertisment.objects.filter(
            utilizator=utilizator,
            data__gte=date.today() - timedelta(days=30)
        )
        return avertismente_recente.count() >= 2
    
    