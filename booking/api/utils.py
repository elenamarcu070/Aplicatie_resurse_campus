import json
from functools import wraps

from django.http import JsonResponse

from booking.models import Camin

API_TEST_CAMIN_NAME = "API_TEST"

def ensure_camin_test():
    camin, _ = Camin.objects.get_or_create(
        nume=API_TEST_CAMIN_NAME,
        defaults={"durata_interval": 2},
    )
    return camin

def parse_json_body(request):
    if not request.body:
        return {}, None
    try:
        return json.loads(request.body), None
    except json.JSONDecodeError:
        return None, JsonResponse(
            {"error": "JSON invalid in corpul cererii"},
            status=400,
        )

def method_not_allowed(allowed_methods):
    return JsonResponse(
        {
            "error": "Metoda HTTP nepermisa",
            "allowed": allowed_methods,
        },
        status=405,
    )

def masina_to_dict(masina):
    return {
        "id": masina.id,
        "nume": masina.nume,
        "activa": masina.activa,
        "camin_id": masina.camin_id,
    }


def necesita_autentificare(view):
    """
    Raspunde 401 JSON daca utilizatorul nu e autentificat.

    Nu folosim `login_required`, care ar raspunde cu un redirect 302 catre
    pagina de login — greu de interpretat pentru un client care asteapta JSON.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"error": "Autentificare necesara pentru acest endpoint"},
                status=401,
            )
        return view(request, *args, **kwargs)

    return wrapper
