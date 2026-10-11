"""Execute due local read-only workers; safe to invoke from an operator timer."""
from django.core.management.base import BaseCommand, CommandError
from django_scopes import scopes_disabled
from cuaderno.services.worker_schedules import run_due


class Command(BaseCommand):
    help = 'Genera informes locales pendientes; nunca aprueba ni ejecuta propuestas.'

    def add_arguments(self, parser):
        parser.add_argument('--limit',type=int,default=20)

    def handle(self,*args,**options):
        if not 1<=options['limit']<=100:
            raise CommandError('--limit debe estar entre 1 y 100.')
        with scopes_disabled():
            outcomes=run_due(limit=options['limit'])
        generated=sum(row['status']=='generated' for row in outcomes)
        self.stdout.write(f'Informes generados: {generated}; necesitan revisión: {len(outcomes)-generated}. Sin cambios operativos.')
