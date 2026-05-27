from datetime import date, timedelta

from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from booking.models import Camin, Masina, Rezervare

from .utils import (
    ensure_camin_test,
    masina_to_dict,
    method_not_allowed,
    parse_json_body,
)


def api_root(request):
    if request.method != "GET":
        return method_not_allowed(["GET"])

    return JsonResponse(
        {
            "name": "TAD REST API - Spalatorie Camin",
            "version": "1.0",
            "resources": {
                "masini_collection": {
                    "url": "/api/masini/",
                    "methods": ["GET", "POST", "PUT", "DELETE"],
                },
                "masini_item": {
                    "url": "/api/masini/<id>/",
                    "methods": ["GET", "POST", "PUT", "DELETE"],
                },
                "camine": {
                    "url": "/api/camine/",
                    "methods": ["GET"],
                },
                "masini_camin": {
                    "url": "/api/masini-camin/?camin_id=<id>",
                    "methods": ["GET"],
                },
                "statistici": {
                    "url": "/api/statistici/avansate/?camin_id=&masina_id=&zi=",
                    "methods": ["GET"],
                },
            },
            "dashboard": "/api-dashboard/",
        },
        status=200,
    )


@csrf_exempt
def masini_list(request):
    camin_test = ensure_camin_test()

    if request.method == "GET":
        masini = list(Masina.objects.filter(camin=camin_test).values())
        return JsonResponse(masini, safe=False, status=200)

    if request.method == "POST":
        data, err = parse_json_body(request)
        if err:
            return err
        nume = (data.get("nume") or "").strip()
        if not nume:
            return JsonResponse({"error": "Campul 'nume' este obligatoriu"}, status=400)
        masina = Masina.objects.create(
            nume=nume,
            camin=camin_test,
            activa=data.get("activa", True),
        )
        return JsonResponse(
            {"message": "Masina creata (TEST)", "masina": masina_to_dict(masina)},
            status=201,
        )

    if request.method == "PUT":
        data, err = parse_json_body(request)
        if err:
            return err
        if not isinstance(data, list):
            return JsonResponse(
                {"error": "Se asteapta o lista de obiecte [{\"nume\": \"...\"}, ...]"},
                status=400,
            )

        Masina.objects.filter(camin=camin_test).delete()
        masini_create = []
        for item in data:
            nume = (item.get("nume") or "").strip()
            if not nume:
                continue
            masina = Masina.objects.create(
                nume=nume,
                camin=camin_test,
                activa=item.get("activa", True),
            )
            masini_create.append(masina_to_dict(masina))

        return JsonResponse(
            {
                "message": "Lista inlocuita",
                "masini": masini_create,
            },
            status=200,
        )

    if request.method == "DELETE":
        deleted, _ = Masina.objects.filter(camin=camin_test).delete()
        return JsonResponse(
            {"message": "Toate masinile TEST au fost sterse", "deleted": deleted},
            status=200,
        )

    return method_not_allowed(["GET", "POST", "PUT", "DELETE"])


@csrf_exempt
def masina_detail(request, id):
    camin_test = ensure_camin_test()

    if request.method == "GET":
        try:
            masina = Masina.objects.get(id=id, camin=camin_test)
        except Masina.DoesNotExist:
            return JsonResponse({"error": "Masina nu exista"}, status=404)
        return JsonResponse(masina_to_dict(masina), status=200)

    if request.method == "POST":
        data, err = parse_json_body(request)
        if err:
            return err
        if Masina.objects.filter(id=id).exists():
            return JsonResponse(
                {"error": "Masina cu acest ID exista deja. Foloseste PUT pentru update."},
                status=409,
            )
        nume = (data.get("nume") or "").strip()
        if not nume:
            return JsonResponse({"error": "Campul 'nume' este obligatoriu"}, status=400)
        masina = Masina.objects.create(
            id=id,
            nume=nume,
            camin=camin_test,
            activa=data.get("activa", True),
        )
        return JsonResponse(
            {"message": "Masina creata (TEST)", "masina": masina_to_dict(masina)},
            status=201,
        )

    if request.method == "PUT":
        data, err = parse_json_body(request)
        if err:
            return err
        nume = (data.get("nume") or "").strip()
        if not nume:
            return JsonResponse({"error": "Campul 'nume' este obligatoriu"}, status=400)

        masina, created = Masina.objects.update_or_create(
            id=id,
            defaults={
                "nume": nume,
                "camin": camin_test,
                "activa": data.get("activa", True),
            },
        )
        return JsonResponse(
            {
                "message": "Masina creata" if created else "Masina actualizata",
                "masina": masina_to_dict(masina),
            },
            status=201 if created else 200,
        )

    if request.method == "DELETE":
        try:
            masina = Masina.objects.get(id=id, camin=camin_test)
        except Masina.DoesNotExist:
            return JsonResponse({"error": "Masina nu exista"}, status=404)
        masina.delete()
        return JsonResponse({"message": "Masina stearsa"}, status=200)

    return method_not_allowed(["GET", "POST", "PUT", "DELETE"])


@require_http_methods(["GET"])
def statistici_avansate(request):
    camin_id = request.GET.get("camin_id")
    masina_id = request.GET.get("masina_id")
    zi = request.GET.get("zi")

    azi = date.today()
    start_sapt = azi - timedelta(days=azi.weekday())
    end_sapt = start_sapt + timedelta(days=6)

    rezervari = Rezervare.objects.filter(
        data_rezervare__range=(start_sapt, end_sapt),
        anulata=False,
    )

    if camin_id:
        rezervari = rezervari.filter(masina__camin_id=camin_id)
    if masina_id:
        rezervari = rezervari.filter(masina_id=masina_id)
    if zi:
        rezervari = rezervari.filter(data_rezervare=zi)

    total = rezervari.count()
    prioritati = rezervari.values("nivel_prioritate").annotate(count=Count("id"))

    return JsonResponse(
        {"total": total, "prioritati": list(prioritati)},
        status=200,
    )


@require_http_methods(["GET"])
def get_camine(request):
    data = list(Camin.objects.values("id", "nume"))
    return JsonResponse(data, safe=False, status=200)


@require_http_methods(["GET"])
def get_masini(request):
    camin_id = request.GET.get("camin_id")
    if not camin_id:
        return JsonResponse({"error": "Parametrul camin_id este obligatoriu"}, status=400)
    masini = Masina.objects.filter(camin_id=camin_id)
    data = list(masini.values("id", "nume", "activa"))
    return JsonResponse(data, safe=False, status=200)
