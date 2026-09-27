from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'action',
        'user',
        'document',
        'timestamp',
        'details',
    )
    list_filter = (
        'action',
        'timestamp',
    )
    search_fields = (
        'action',
        'user__username',
        'document__title',
        'details',
    )
    readonly_fields = (
        'user',
        'action',
        'document',
        'details',
        'timestamp',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
