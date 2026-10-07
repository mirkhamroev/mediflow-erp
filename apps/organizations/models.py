from django.db import models
from apps.accounts.models import User
from apps.commons.mixins import AuditableModelMixin
import uuid

# Create your models here.

class Organization(AuditableModelMixin, models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255)
    tax_id = models.CharField(max_length=50, unique=True)
    address = models.TextField()
    email = models.EmailField(max_length=255)
    phone_number = models.CharField(max_length=20, unique=True)
    logo = models.ImageField(upload_to='organization_logos/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'
        ordering = ['name', 'created_at']

    def __str__(self):
        return self.name

class Hospital(AuditableModelMixin, models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='hospitals')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, unique=True)
    email = models.EmailField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Hospital'
        verbose_name_plural = 'Hospitals'
        ordering = ['name', 'created_at']

    def __str__(self):
        return self.name


class Department(AuditableModelMixin, models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255)
    # unique per hospital, not globally: two hospitals can both have an "ER" department
    code = models.CharField(max_length=50)
    description = models.TextField(null=True, blank=True)
    head = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='headed_departments')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
        ordering = ['name', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['hospital', 'code'], name='unique_department_code_per_hospital'),
        ]

    def __str__(self):
        return self.name
