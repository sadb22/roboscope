import time
from django.core.management.base import BaseCommand
from django.db import connection, close_old_connections, transaction
from django.utils import timezone
from datetime import timedelta
from core.models import SimulationRun, ServiceHeartbeat
from core.simulation import simulate
class Command(BaseCommand):
    help='Обработчик очереди симуляций. PostgreSQL допускает несколько обработчиков.'
    def handle(self,*args,**kwargs):
        self.stdout.write('Simulation worker ready')
        last_heartbeat=0
        while True:
            close_old_connections()
            if time.monotonic()-last_heartbeat>5:
                ServiceHeartbeat.objects.update_or_create(key='simulation-worker',defaults={'updated_at':timezone.now()})
                last_heartbeat=time.monotonic()
            stale=timezone.now()-timedelta(minutes=3)
            SimulationRun.objects.filter(status='running',updated_at__lt=stale).update(status='failed',error='Вычисление прервано. Запустите повторно.')
            SimulationRun.objects.filter(created_at__lt=timezone.now()-timedelta(days=1)).delete()
            with transaction.atomic():
                qs=SimulationRun.objects.filter(status='pending').order_by('created_at')
                if connection.vendor=='postgresql':qs=qs.select_for_update(skip_locked=True)
                run=qs.first()
                if run:
                    run.status='running';run.save(update_fields=['status','updated_at'])
            if not run:
                time.sleep(.5);continue
            try:
                run.result=simulate(run.payload['calculation'],run.payload.get('seed',42),run.payload.get('hours',4))
                run.status='done'
            except Exception as exc:
                run.status='failed';run.error=str(exc)
            run.save(update_fields=['status','result','error','updated_at'])
