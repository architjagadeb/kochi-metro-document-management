from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Department, User


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_user_count')
    search_fields = ('name',)

    @admin.display(description='Users Count')
    def get_user_count(self, obj):
        return obj.users.count()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'role',
        'department',
        'is_staff',
    )
    list_filter = (
        'role',
        'department',
        'is_staff',
        'is_superuser',
        'is_active',
    )
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            'Metro DMS Information',
            {
                'fields': ('role', 'department'),
            },
        ),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            'Metro DMS Information',
            {
                'fields': ('role', 'department'),
            },
        ),
    )
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)
