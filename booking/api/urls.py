from django.urls import path
from . import views

urlpatterns = [
    path('masini/', views.masini_list),
    path('masini/<int:id>/', views.masina_detail),
    path('masini-all/', views.get_toate_masinile),

    path('camine/', views.get_camine),
    path('masini-camin/', views.get_masini),  # 🔥 IMPORTANT
    path('statistici/avansate/', views.statistici_avansate),  # 🔥 lipsea
]