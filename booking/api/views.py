from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

from booking.models import Masina, Rezervare


# =========================
# MASINI - COLLECTION
# =========================

def masini_list(request):
    if request.method == 'GET':
        masini = list(Masina.objects.values())
        return JsonResponse(masini, safe=False, status=200)

    if request.method == 'POST':
        data = json.loads(request.body)

        masina = Masina.objects.create(
            nume=data.get('nume'),
            camin_id=data.get('camin_id'),
            activa=data.get('activa', True)
        )

        return JsonResponse({
            "message": "Masina creata",
            "id": masina.id
        }, status=201)

    if request.method == 'DELETE':
        Masina.objects.all().delete()
        return JsonResponse({"message": "Toate masinile sterse"}, status=200)


# =========================
# MASINI - ITEM
# =========================

@csrf_exempt
def masina_detail(request, id):
    try:
        masina = Masina.objects.get(id=id)
    except Masina.DoesNotExist:
        return JsonResponse({"error": "Masina nu exista"}, status=404)

    if request.method == 'GET':
        return JsonResponse({
            "id": masina.id,
            "nume": masina.nume,
            "activa": masina.activa
        }, status=200)

    if request.method == 'PUT':
        data = json.loads(request.body)
        masina.nume = data.get('nume', masina.nume)
        masina.activa = data.get('activa', masina.activa)
        masina.save()

        return JsonResponse({"message": "Masina actualizata"}, status=200)

    if request.method == 'DELETE':
        masina.delete()
        return JsonResponse({"message": "Masina stearsa"}, status=200)


# =========================
# REZERVARI - COLLECTION
# =========================

@csrf_exempt
def rezervari_list(request):
    if request.method == 'GET':
        rezervari = list(Rezervare.objects.values())
        return JsonResponse(rezervari, safe=False, status=200)

    if request.method == 'POST':
        data = json.loads(request.body)

        rezervare = Rezervare.objects.create(
            utilizator_id=data.get('utilizator_id'),
            masina_id=data.get('masina_id'),
            data_rezervare=data.get('data_rezervare'),
            ora_start=data.get('ora_start'),
            ora_end=data.get('ora_end'),
            nivel_prioritate=1
        )

        return JsonResponse({
            "message": "Rezervare creata",
            "id": rezervare.id
        }, status=201)

    if request.method == 'DELETE':
        Rezervare.objects.all().delete()
        return JsonResponse({"message": "Toate rezervarile sterse"}, status=200)


# =========================
# REZERVARI - ITEM
# =========================

@csrf_exempt
def rezervare_detail(request, id):
    try:
        rezervare = Rezervare.objects.get(id=id)
    except Rezervare.DoesNotExist:
        return JsonResponse({"error": "Rezervare nu exista"}, status=404)

    if request.method == 'GET':
        return JsonResponse({
            "id": rezervare.id,
            "masina": rezervare.masina_id,
            "data": rezervare.data_rezervare,
            "ora_start": rezervare.ora_start,
            "ora_end": rezervare.ora_end
        }, status=200)

    if request.method == 'PUT':
        data = json.loads(request.body)

        rezervare.ora_start = data.get('ora_start', rezervare.ora_start)
        rezervare.ora_end = data.get('ora_end', rezervare.ora_end)
        rezervare.save()

        return JsonResponse({"message": "Rezervare actualizata"}, status=200)

    if request.method == 'DELETE':
        rezervare.delete()
        return JsonResponse({"message": "Rezervare stearsa"}, status=200)


# =========================
# BONUS (🔥 puncte extra)
# =========================

def statistici_top_masini(request):
    data = {}

    for r in Rezervare.objects.all():
        mid = r.masina_id
        data[mid] = data.get(mid, 0) + 1

    return JsonResponse(data, status=200)