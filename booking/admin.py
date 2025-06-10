from django.contrib import admin
from .models import Camin, Masina, ProgramMasina, ProfilStudent, Rezervare, Avertisment

admin.site.register(Camin)
admin.site.register(Masina)
admin.site.register(ProgramMasina)



@admin.register(ProfilStudent)
class ProfilStudentAdmin(admin.ModelAdmin):
    list_display = ('email', 'nume', 'prenume', 'camin', 'numar_camera')
    search_fields = ('utilizator__email', 'utilizator__first_name', 'utilizator__last_name')
    list_filter = ('camin',)

    def email(self, obj):
        return obj.utilizator.email

    def nume(self, obj):
        return obj.utilizator.last_name

    def prenume(self, obj):
        return obj.utilizator.first_name

@admin.register(Avertisment)
class AvertismentAdmin(admin.ModelAdmin):
    list_display = ('utilizator', 'data', 'motiv')
    search_fields = ('utilizator__email',)
    



@admin.register(Rezervare)
class RezervareAdmin(admin.ModelAdmin):
    list_display = ('utilizator', 'masina', 'data_rezervare', 'ora_start', 'ora_end', 'prioritara', 'anulata')
    list_filter = ('masina', 'data_rezervare', 'anulata', 'prioritara')
    actions = ['sterge_rezervari_anulate']

    @admin.action(description="Șterge rezervările anulate")
    def sterge_rezervari_anulate(self, request, queryset):
        count = queryset.filter(anulata=True).delete()
        self.message_user(request, f"{count[0]} rezervări anulate au fost șterse.")
