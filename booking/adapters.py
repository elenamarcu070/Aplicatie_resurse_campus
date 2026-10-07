# booking/adapters.py
from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.exceptions import ImmediateHttpResponse
from django.http import HttpResponseForbidden
from django.contrib.auth import get_user_model

# Modelele tale custom (student + admin)
try:
    from booking.models import ProfilStudent, AdminCamin
except Exception:
    ProfilStudent = None
    AdminCamin = None


# ===============================
# Helper: verifică dacă email-ul e în baza de date
# ===============================
def email_is_allowed(email: str) -> bool:
    e = (email or "").strip().lower()
    if not e:
        return False

    User = get_user_model()

    in_user = User.objects.filter(email__iexact=e).exists()
    in_student = bool(ProfilStudent and ProfilStudent.objects.filter(email__iexact=e).exists())
    in_admin = bool(AdminCamin and AdminCamin.objects.filter(email__iexact=e).exists())

    return in_user or in_student or in_admin


# ===============================
# Adaptor pentru login clasic (email/parolă)
# ===============================
class MyAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        """Blochează sign-up liber. Permite doar dacă email-ul e în DB."""
        email = (request.POST.get("email") or "").strip()
        return email_is_allowed(email)

    def clean_email(self, email):
        """Validează că email-ul e în whitelist înainte de creare cont."""
        email = super().clean_email(email)
        if not email_is_allowed(email):
            from django.core.exceptions import ValidationError
            from django.utils.translation import gettext_lazy as _
            raise ValidationError(_("Emailul nu este în baza de date. Contactează administratorul."))
        return email


# ===============================
# Adaptor pentru login cu Google
# ===============================
class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        """Permite login doar dacă emailul există în baza de date."""
        email = (getattr(sociallogin.user, "email", "") or "").strip().lower()
        # dacă ai nevoie să accepți și conturi noi pentru prezentare:
        return True if email else False

    def pre_social_login(self, request, sociallogin):
        """Leagă login-ul Google de User existent sau creează unul nou dacă nu există."""
        email = (getattr(sociallogin.user, "email", "") or "").strip().lower()
        if not email:
            return

        User = get_user_model()
        prenume = (getattr(sociallogin.user, "first_name", "") or "").strip()
        nume = (getattr(sociallogin.user, "last_name", "") or "").strip()

        try:
            user = User.objects.get(email__iexact=email)
            # Conturile vechi au fost create fără nume; îl completăm acum, dar
            # nu suprascriem unul pus de administrator în listele căminului.
            campuri = []
            if prenume and not user.first_name:
                user.first_name = prenume
                campuri.append("first_name")
            if nume and not user.last_name:
                user.last_name = nume
                campuri.append("last_name")
            if campuri:
                user.save(update_fields=campuri)
            sociallogin.connect(request, user)
            return
        except User.DoesNotExist:
            # Dacă email-ul nu e găsit, creează un User nou (dar nu îl bagi în
            # ProfilStudent dacă nu există). Numele vine de la Google: fără el,
            # formularul de cerere de cont ar porni gol, iar recunoașterea
            # studentului care are deja cont pe altă adresă n-ar avea cu ce
            # lucra — ea se sprijină chiar pe numele complet.
            username_base = email.split("@")[0]
            user = User.objects.create(
                email=email,
                username=username_base,
                first_name=prenume,
                last_name=nume,
            )
            user.set_unusable_password()
            user.is_active = True
            user.save()
            sociallogin.connect(request, user)
            return
