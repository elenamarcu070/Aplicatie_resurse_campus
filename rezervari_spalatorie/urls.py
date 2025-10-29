# rezervari_sali/urls.py

from django.views.generic import TemplateView

from django.contrib import admin
from django.urls import path, include
from booking import views as booking_views
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.conf import settings
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('booking.urls')),  # home, callback etc
    path("accounts/signup/", RedirectView.as_view(pattern_name="account_login", permanent=False)),  # blocăm signup
    path('accounts/', include('allauth.urls')),
    path('logout/', booking_views.custom_logout, name='custom_logout'),

    
    path(
        "firebase-messaging-sw.js",
        TemplateView.as_view(
            template_name="firebase-messaging-sw.js",
            content_type="application/javascript"
        ),
        name="firebase_sw",
    ),
]
