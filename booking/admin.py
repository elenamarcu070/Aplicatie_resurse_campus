from django.contrib import admin
from .models import Camin, Masina, ProgramMasina, ProfilStudent, Rezervare, Avertisment
from .models import AdminCamin
from django.contrib.auth.models import User 
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _


@admin.register(Masina)
class MasinaAdmin(admin.ModelAdmin):
    list_display = ('nume', 'camin', 'activa')
    search_fields = ('nume', 'camin__nume')
    list_filter = ('camin', 'activa')



@admin.register(ProgramMasina)   
class ProgramMasinaAdmin(admin.ModelAdmin):
    list_display = ('masina', 'ora_start', 'ora_end')
    search_fields = ('masina__nume',)
    list_filter = ('masina',)


@admin.register(Camin)
class CaminAdmin(admin.ModelAdmin):
    list_display = ('nume',)
    search_fields = ('nume',)
    ordering = ('nume',)



@admin.register(AdminCamin)
class AdminCaminAdmin(admin.ModelAdmin):
    list_display = ('email', 'camin')
    search_fields = ('email',)
    list_filter = ('camin',)


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
    list_display = ('utilizator', 'masina', 'data_rezervare', 'ora_start', 'ora_end', 
                   'get_nivel_prioritate_display', 'anulata', 'created_at')
    list_filter = ('masina', 'data_rezervare', 'anulata', 'nivel_prioritate')
    search_fields = ('utilizator__email', 'utilizator__first_name', 'utilizator__last_name', 
                    'masina__nume')
    date_hierarchy = 'data_rezervare'
    ordering = ('-data_rezervare', 'ora_start')
    actions = ['sterge_rezervari_anulate']

    def get_nivel_prioritate_display(self, obj):
        return obj.get_nivel_prioritate_display()
    get_nivel_prioritate_display.short_description = 'Nivel Prioritate'

    @admin.action(description="Șterge rezervările anulate")
    def sterge_rezervari_anulate(self, request, queryset):
        count = queryset.filter(anulata=True).delete()
        self.message_user(request, f"{count[0]} rezervări anulate au fost șterse.")
