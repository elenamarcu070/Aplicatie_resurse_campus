from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta,date

# ------------------------------------------
# CĂMIN
# ------------------------------------------

class Camin(models.Model):
    nume = models.CharField(max_length=50)

    def __str__(self):
        return self.nume

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
    numar_camera = models.CharField(max_length=10, blank=True, null=True)
    suspendat_pana_la = models.DateField(null=True, blank=True)

    def este_suspendat(self):
        from django.utils.timezone import now
        return self.suspendat_pana_la and self.suspendat_pana_la >= now().date()

    def __str__(self):
        return self.utilizator.email

# ------------------------------------------
# REZERVARE
# ------------------------------------------
class Rezervare(models.Model):
    utilizator = models.ForeignKey(User, on_delete=models.CASCADE)
    masina = models.ForeignKey(Masina, on_delete=models.CASCADE)
    data_rezervare = models.DateField()
    ora_start = models.TimeField()
    ora_end = models.TimeField()
    prioritara = models.BooleanField(default=True)  # True = prioritară, False = non-prioritară
    anulata = models.BooleanField(default=False)
    avertisment_dat = models.BooleanField(default=False)  # avertisment dat pentru nefolosire

    def __str__(self):
        return f"{self.utilizator.email} - {self.masina.nume} - {self.data_rezervare} {self.ora_start}-{self.ora_end}"

# ------------------------------------------
# AVERTISMENTE
# ------------------------------------------



# ------------------------------------------
# ADMINI CAMINE
# ------------------------------------------

class AdminCamin(models.Model):
    camin = models.ForeignKey(Camin, on_delete=models.CASCADE, related_name="admini")
    email = models.EmailField(max_length=100)

    def __str__(self):
        return f"{self.email} - {self.camin.nume}"
    
    
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
    
    