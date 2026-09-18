import os
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.catalog import import_catalog
from core.models import Product, Normative
from core.schema import FIELDS
class Command(BaseCommand):
    help='Импорт каталога и нормативов; существующие нормативы сохраняются'
    def handle(self,*args,**kwargs):
        if not Product.objects.exists():
            result=import_catalog((settings.BASE_DIR/'data/catalog.csv').read_bytes())
            self.stdout.write(str(result))
        for f in FIELDS:
            Normative.objects.get_or_create(key=f['key'],defaults=dict(label=f['label'],value=f['default'],source=f['source']))
        for role,staff in [('ADMIN',True),('DEMO',False)]:
            user=os.environ.get(role+'_USERNAME');password=os.environ.get(role+'_PASSWORD')
            if user and password:
                obj,created=get_user_model().objects.get_or_create(username=user)
                if created:
                    if len(password)<10:raise ValueError('Пароль должен содержать минимум 10 символов')
                    obj.set_password(password);obj.is_staff=staff;obj.is_superuser=staff;obj.save()
                    self.stdout.write('Создан пользователь '+user)
        self.stdout.write(self.style.SUCCESS('Каталог и нормативы готовы'))
