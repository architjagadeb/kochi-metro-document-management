from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'recipient',
        'message',
        'link',
        'is_read',
        'created_date',
    )
    list_filter = (
        'is_read',
        'created_date',
    )
    search_fields = (
        'recipient__username',
        'message',
        'link',
    )
    readonly_fields = (
        'recipient',
        'message',
        'link',
        'is_read',
        'created_date',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
