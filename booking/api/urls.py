from django.urls import path
from . import views

urlpatterns = [
    path('masini/', views.masini_list),
    path('masini/<int:id>/', views.masina_detail),

    path('rezervari/', views.rezervari_list),
    path('rezervari/<int:id>/', views.rezervare_detail),

    path('statistici/top-masini/', views.statistici_top_masini),
    path('statistici/avansate/', views.statistici_avansate),
]