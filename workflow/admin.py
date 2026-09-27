from django.contrib import admin

from .models import Approval, ApprovalRule


@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    list_display = (
        'document_type',
        'department',
        'approver_role',
    )
    list_filter = (
        'document_type',
        'department',
        'approver_role',
    )
    search_fields = (
        'department__name',
    )


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display = (
        'document',
        'status',
        'decided_by',
        'decided_date',
        'created_date',
    )
    list_filter = (
        'status',
        'decided_date',
        'created_date',
    )
    search_fields = (
        'document__title',
        'decided_by__username',
        'comment',
    )
    readonly_fields = (
        'document',
        'status',
        'decided_by',
        'comment',
        'decided_date',
        'created_date',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
