from django.core.management.base import BaseCommand

from booking.api.utils import ensure_camin_test
from booking.models import Masina


class Command(BaseCommand):
    help = "Pregateste mediul TAD: camin API_TEST si optional masini demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--demo",
            action="store_true",
            help="Adauga 2 masini demo in API_TEST (daca lista e goala).",
        )

    def handle(self, *args, **options):
        camin = ensure_camin_test()
        self.stdout.write(self.style.SUCCESS(f"Camin gata: {camin.nume} (id={camin.id})"))

        if options["demo"]:
            count = Masina.objects.filter(camin=camin).count()
            if count == 0:
                Masina.objects.create(nume="Masina Demo 1", camin=camin, activa=True)
                Masina.objects.create(nume="Masina Demo 2", camin=camin, activa=True)
                self.stdout.write(self.style.SUCCESS("2 masini demo adaugate."))
            else:
                self.stdout.write("Lista API_TEST nu e goala — demo sarit.")

        self.stdout.write("Dashboard TAD: /api-dashboard/")
        self.stdout.write("API root: /api/")
