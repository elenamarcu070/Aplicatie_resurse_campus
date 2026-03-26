from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

from booking.models import Masina, Rezervare, Camin


# =========================
# UTIL
# =========================

def get_camin_test():
    try:
        return Camin.objects.get(nume="API_TEST")
    except Camin.DoesNotExist:
        return None


# =========================
# MASINI - COLLECTION
# =========================

@csrf_exempt
def masini_list(request):
    camin_test = get_camin_test()

    if not camin_test:
        return JsonResponse({"error": "Camin API_TEST nu exista"}, status=400)

    if request.method == 'GET':
        masini = list(
            Masina.objects.filter(camin=camin_test).values()
        )
        return JsonResponse(masini, safe=False, status=200)

    if request.method == 'POST':
        data = json.loads(request.body)

        masina = Masina.objects.create(
            nume=data.get('nume'),
            camin=camin_test,
            activa=True
        )

        return JsonResponse({
            "message": "Masina creata (TEST)",
            "id": masina.id
        }, status=201)

    if request.method == 'DELETE':
        Masina.objects.filter(camin=camin_test).delete()
        return JsonResponse({"message": "Masini TEST sterse"}, status=200)


# =========================
# MASINI - ITEM
# =========================

@csrf_exempt
def masina_detail(request, id):
    camin_test = get_camin_test()

    try:
        masina = Masina.objects.get(id=id)
    except Masina.DoesNotExist:
        return JsonResponse({"error": "Masina nu exista"}, status=404)

    # 🔥 protecție
    if masina.camin != camin_test:
        return JsonResponse({"error": "Acces doar pe date TEST"}, status=403)

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
    camin_test = get_camin_test()

    if not camin_test:
        return JsonResponse({"error": "Camin API_TEST nu exista"}, status=400)

    if request.method == 'GET':
        rezervari = list(
            Rezervare.objects.filter(masina__camin=camin_test).values()
        )
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
            "message": "Rezervare creata (TEST)",
            "id": rezervare.id
        }, status=201)

    if request.method == 'DELETE':
        Rezervare.objects.filter(masina__camin=camin_test).delete()
        return JsonResponse({"message": "Rezervari TEST sterse"}, status=200)


# =========================
# REZERVARI - ITEM
# =========================

@csrf_exempt
def rezervare_detail(request, id):
    camin_test = get_camin_test()

    try:
        rezervare = Rezervare.objects.get(id=id)
    except Rezervare.DoesNotExist:
        return JsonResponse({"error": "Rezervare nu exista"}, status=404)

    # 🔥 protecție
    if rezervare.masina.camin != camin_test:
        return JsonResponse({"error": "Acces doar pe date TEST"}, status=403)

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
# BONUS
# =========================

def statistici_top_masini(request):
    camin_test = get_camin_test()

    data = {}

    rezervari = Rezervare.objects.filter(masina__camin=camin_test)

    for r in rezervari:
        mid = r.masina_id
        data[mid] = data.get(mid, 0) + 1

    return JsonResponse(data, status=200)

from django.db.models import Count
from datetime import date, timedelta
from booking.models import Rezervare, Camin, Masina


def statistici_avansate(request):
    camin_id = request.GET.get('camin_id')
    masina_id = request.GET.get('masina_id')
    zi = request.GET.get('zi')

    azi = date.today()
    start_sapt = azi - timedelta(days=azi.weekday())
    end_sapt = start_sapt + timedelta(days=6)

    rezervari = Rezervare.objects.filter(
        data_rezervare__range=(start_sapt, end_sapt),
        anulata=False
    )

    # 🔹 filtrare cămin
    if camin_id:
        rezervari = rezervari.filter(masina__camin_id=camin_id)

    # 🔹 filtrare mașină
    if masina_id:
        rezervari = rezervari.filter(masina_id=masina_id)

    # 🔹 filtrare zi
    if zi:
        rezervari = rezervari.filter(data_rezervare=zi)

    total = rezervari.count()

    # 🔥 statistici pe priorități
    prioritati = rezervari.values('nivel_prioritate').annotate(count=Count('id'))

    # 🔥 statistici pe mașini
    masini = rezervari.values('masina__nume').annotate(count=Count('id'))

    return JsonResponse({
        "total_rezervari": total,
        "prioritati": list(prioritati),
        "pe_masini": list(masini)
    }, status=200)