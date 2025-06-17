from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.exceptions import ImmediateHttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.models import User

class MyAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Permite înregistrarea chiar dacă există deja un cont cu același email
        return True

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # Accept only @student.tuiasi.ro accounts
        allowed_domain = 'student.tuiasi.ro'
        if sociallogin.user.email.split('@')[-1] != allowed_domain:
            raise ImmediateHttpResponse(render(request, 'not_allowed.html', {'message': f'Ne pare rău, dar doar adresele de email cu domeniul <code>@{domain}</code> sunt permise.'}))

        # Check if user already exists
        try:
            user = User.objects.get(email=sociallogin.user.email)
            sociallogin.connect(request, user)
            raise ImmediateHttpResponse(redirect('dashboard_student'))
        except User.DoesNotExist:
            pass
