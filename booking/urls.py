from django.urls import path
from . import views
from django.conf import settings
from django.contrib.auth.decorators import login_required  


urlpatterns = [
    # ...
    path("webhook/twilio-sms/", twilio_sms_status_webhook, name="twilio_sms_webhook"),
]


urlpatterns = [
    # Autentificare și înregistrare
    path('', views.home, name='home'),
    path('callback/', views.callback, name='callback'),

    # Dashboard Student
    path('dashboard/student/', views.dashboard_student, name='dashboard_student'),
    # Dashboard Admin Cămin
    path('dashboard/admin_camin/', views.dashboard_admin_camin, name='dashboard_admin_camin'),



    # Admin cămin - Detalii cămin
    path('dashboard/admin_camin/camine/<int:camin_id>/', views.detalii_camin_admin, name='detalii_camin_admin'),
    path('dashboard/admin_camin/camine/', views.administrare_camin, name='administrare_camin'),
    path('dashboard/admin_camin/adauga/', views.adauga_camin_view, name='adauga_camin'),
    path('dashboard/admin_camin/sterge/<int:camin_id>/', views.sterge_camin_view, name='sterge_camin'),


    # Dashboard Student - Programări
    path('dashboard/student/calendar/', views.calendar_rezervari_view, name='calendar_rezervari'),
    path('dashboard/student/programari/', views.programari_student_view, name='programari_student'),
    path('dashboard/student/anuleaza/<int:rezervare_id>/', views.anuleaza_rezervare, name='anuleaza_rezervare'),
    path('dashboard/student/creeaza/', views.creeaza_rezervare, name='creeaza_rezervare'),
    path('calendar/adauga-avertisment/', views.adauga_avertisment_din_calendar, name='adauga_avertisment_din_calendar'),
    path("dashboard/student/adauga-telefon/", views.adauga_telefon, name="adauga_telefon"),
    
    # Dashboard Admin Cămin - Programări
    path('dashboard/admin_camin/calendar/', views.calendar_rezervari_admin_view, name='calendar_rezervari_admin'),
    path('dashboard/admin_camin/programari/', views.programari_admin_camin_view, name='programari_admin_camin'),
    path("adauga_telefon_admin/", views.adauga_telefon_admin, name="adauga_telefon_admin"),


    # Dashboard Admin Cămin - Import studenți
    path('dashboard/admin_camin/incarca-studenti/', views.incarca_studenti_view, name='incarca_studenti'),
    path('dashboard/admin_camin/studenti/adauga/', views.adauga_student_view, name='adauga_student'),
    path('dashboard/admin_camin/studenti/sterge/<int:student_id>/', views.sterge_student_view, name='sterge_student'),
    path('dashboard/admin_camin/studenti/sterge-toti/', views.sterge_toti_studentii_view, name='sterge_toti_studentii'),
    path('dashboard/admin_camin/student/<int:student_id>/update/', views.update_student, name='update_student'),
    
 

]

