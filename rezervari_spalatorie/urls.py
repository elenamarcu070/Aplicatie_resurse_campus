# rezervari_sali/urls.py

from django.contrib import admin
from django.urls import path, include
from booking import views as booking_views
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('booking.urls')),  # home, callback etc
    path('accounts/', include('allauth.urls')), 
    path('logout/', booking_views.custom_logout, name='custom_logout'),
    path('i18n/', include('django.conf.urls.i18n')),
    
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# urlpatterns += i18n_patterns(
#     # path('admin/', admin.site.urls),
#     # path('', include('booking.urls')),
#     prefix_default_language=False,
# ) 

# if settings.DEBUG:
#     urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)