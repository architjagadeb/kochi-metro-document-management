from django.contrib.auth.models import AbstractUser
from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
        ordering = ['name']

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLE_EMPLOYEE = 'employee'
    ROLE_OFFICER = 'officer'
    ROLE_ADMIN = 'admin'

    ROLE_CHOICES = [
        (ROLE_EMPLOYEE, 'Employee'),
        (ROLE_OFFICER, 'Officer'),
        (ROLE_ADMIN, 'Admin'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_EMPLOYEE,
        help_text='Designates the role of the user within the organization.',
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        help_text='The department to which this user belongs.',
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
