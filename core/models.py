import uuid
from django.conf import settings
from django.db import models

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_id = models.CharField(max_length=120, unique=True)
    name = models.CharField('Название', max_length=300)
    company = models.CharField('Производитель', max_length=300, blank=True)
    kind = models.CharField('Тип', max_length=160, blank=True)
    subtype = models.CharField('Подтип', max_length=160, blank=True)
    status = models.CharField('Статус', max_length=50, default='operation')
    description = models.TextField('Описание', blank=True)
    price = models.DecimalField('Цена, руб.', max_digits=15, decimal_places=2, null=True, blank=True)
    applications = models.JSONField('Отрасли и сценарии', default=list)
    specs = models.JSONField('Характеристики', default=dict, blank=True)
    sources = models.JSONField('Источники', default=list)
    observations = models.JSONField('Исходные записи', default=list)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['name']
        verbose_name = 'Решение'
        verbose_name_plural = 'Каталог решений'
    def __str__(self): return self.name

class Normative(models.Model):
    key = models.SlugField(primary_key=True)
    label = models.CharField('Показатель', max_length=200)
    value = models.JSONField('Значение')
    source = models.CharField('Источник / допущение', max_length=500)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.label

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=160)
    object_type = models.CharField(max_length=40, default='warehouse')
    payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: ordering = ['-updated_at']

class ProjectVersion(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='versions')
    revision = models.PositiveIntegerField()
    payload = models.JSONField()
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['project', 'revision'], name='unique_project_revision')]
        ordering = ['-revision']

class SimulationRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True)
    session_key = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=30, default='pending')
    payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class LoginAttempt(models.Model):
    key = models.CharField(max_length=100, unique=True)
    failures = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

class ServiceHeartbeat(models.Model):
    key = models.CharField(max_length=40, primary_key=True)
    updated_at = models.DateTimeField(auto_now=True)
