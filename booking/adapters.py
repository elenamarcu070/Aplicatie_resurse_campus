from allauth.account.adapter import DefaultAccountAdapter

class MyAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Permitem signup-ul automat, fără să fie nevoie de formular
        return True

    def save_user(self, request, user, form, commit=True):
        # Salvăm automat userul fără date suplimentare
        user.email = request.session.get('socialaccount_email', user.email)
        user.username = user.email
        if commit:
            user.save()
        return user
