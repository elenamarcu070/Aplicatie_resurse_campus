from django.urls import path
from . import views
from django.contrib.auth.decorators import login_required  # Importă decoratorul

urlpatterns = [
    path('', views.home, name='home'),
    path('callback/', views.callback, name='callback'),

    # Dashboard-uri
    path('dashboard/student/', views.dashboard_student, name='dashboard_student'),
    path('dashboard/admin_camin/', views.dashboard_admin_camin, name='dashboard_admin_camin'),
    
    # Admin cămin - Vizualizare cămine
    path('dashboard/admin_camin/camine/<int:camin_id>/', views.detalii_camin_admin, name='detalii_camin_admin'),
    path('dashboard/admin_camin/adauga/', views.adauga_camin_view, name='adauga_camin'),
    path('dashboard/admin_camin/sterge/<int:camin_id>/', views.sterge_camin_view, name='sterge_camin'),

    path('dashboard/student/calendar/', login_required(views.calendar_rezervari_view), name='calendar_rezervari'), # Adaugă login_required
    path('dashboard/student/programari/', login_required(views.programari_student_view), name='programari_student'), # Adaugă login_required
    path('dashboard/student/anuleaza/<int:rezervare_id>/', login_required(views.anuleaza_rezervare), name='anuleaza_rezervare'), # Adaugă login_required
    path('dashboard/student/creeaza/', login_required(views.creeaza_rezervare), name='creeaza_rezervare'), # Adaugă login_required
    path('calendar/adauga-avertisment/', login_required(views.adauga_avertisment_din_calendar), name='adauga_avertisment_din_calendar'), # Adaugă login_required
    
    path('dashboard/admin_camin/calendar/', login_required(views.calendar_rezervari_admin_view), name='calendar_rezervari_admin'), # Adaugă login_required
    path('dashboard/admin_camin/programari/', login_required(views.programari_admin_camin_view), name='programari_admin_camin'), # Adaugă login_required

    path('dashboard/admin_camin/incarca-studenti/', login_required(views.incarca_studenti_view), name='incarca_studenti'), # Adaugă login_required
    path('dashboard/admin_camin/studenti/adauga/', login_required(views.adauga_student_view), name='adauga_student'), # Adaugă login_required
    path('dashboard/admin_camin/studenti/sterge/<int:student_id>/', login_required(views.sterge_student_view), name='sterge_student'), # Adaugă login_required
    path('dashboard/admin_camin/studenti/sterge-toti/', login_required(views.sterge_toti_studentii_view), name='sterge_toti_studentii'), # Adaugă login_required
    path('dashboard/admin_camin/student/<int:student_id>/update/', login_required(views.update_student), name='update_student'), # Adaugă login_required
]
