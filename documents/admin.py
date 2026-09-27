from django.contrib import admin

from .models import Document, DocumentVersion


class DocumentVersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    fields = ('version_number', 'file', 'text_found', 'uploaded_by', 'created_date', 'change_note')
    readonly_fields = ('created_date',)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'document_type',
        'department',
        'confidentiality',
        'status',
        'uploaded_by',
        'current_version',
        'created_date',
    )
    list_filter = (
        'document_type',
        'confidentiality',
        'status',
        'department',
    )
    search_fields = ('title', 'uploaded_by__username', 'department__name')
    readonly_fields = ('created_date',)
    inlines = [DocumentVersionInline]


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        'document',
        'version_number',
        'file',
        'text_found',
        'uploaded_by',
        'created_date',
    )
    list_filter = (
        'text_found',
        'created_date',
    )
    search_fields = ('document__title', 'uploaded_by__username', 'change_note')
    readonly_fields = ('created_date',)
