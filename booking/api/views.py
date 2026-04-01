from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count
from datetime import date, timedelta
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
        return JsonResponse({"message": "Masina creata (TEST)", "id": masina.id}, status=201)

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

    if masina.camin != camin_test:
        return JsonResponse({"error": "Acces doar pe date TEST"}, status=403)

    if request.method == 'GET':
        return JsonResponse({"id": masina.id, "nume": masina.nume, "activa": masina.activa}, status=200)

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
# STATISTICI
# =========================

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

    if camin_id:
        rezervari = rezervari.filter(masina__camin_id=camin_id)
    if masina_id:
        rezervari = rezervari.filter(masina_id=masina_id)
    if zi:
        rezervari = rezervari.filter(data_rezervare=zi)

    total = rezervari.count()
    prioritati = rezervari.values('nivel_prioritate').annotate(count=Count('id'))

    return JsonResponse({"total": total, "prioritati": list(prioritati)})


# =========================
# CAMINE / MASINI DROPDOWN
# =========================

def get_camine(request):
    data = list(Camin.objects.values('id', 'nume'))
    return JsonResponse(data, safe=False)


def get_masini(request):
    camin_id = request.GET.get('camin_id')
    masini = Masina.objects.filter(camin_id=camin_id)
    data = list(masini.values('id', 'nume'))
    return JsonResponse(data, safe=False)