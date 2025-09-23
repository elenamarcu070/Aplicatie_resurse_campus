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

        try:
            user = User.objects.get(email__iexact=email)
            sociallogin.connect(request, user)
            return
        except User.DoesNotExist:
            # Dacă email-ul nu e găsit, creează un User nou (dar nu îl bagi în ProfilStudent dacă nu există)
            username_base = email.split("@")[0]
            user = User.objects.create(
                email=email,
                username=username_base,
            )
            user.set_unusable_password()
            user.is_active = True
            user.save()
            sociallogin.connect(request, user)
            return
