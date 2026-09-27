from django.conf import settings
from django.db import models

from accounts.models import Department
from accounts.permissions import (
    CONFIDENTIALITY_CHOICES,
    CONFIDENTIALITY_INTERNAL,
    CONFIDENTIALITY_PUBLIC,
    CONFIDENTIALITY_RESTRICTED,
)


class Document(models.Model):
    DOC_TYPE_TENDER = 'tender'
    DOC_TYPE_CONTRACT = 'contract'
    DOC_TYPE_REPORT = 'report'
    DOC_TYPE_INVOICE = 'invoice'
    DOC_TYPE_LEGAL = 'legal'
    DOC_TYPE_SAFETY_CIRCULAR = 'safety circular'
    DOC_TYPE_OTHER = 'other'

    DOCUMENT_TYPE_CHOICES = [
        (DOC_TYPE_TENDER, 'Tender'),
        (DOC_TYPE_CONTRACT, 'Contract'),
        (DOC_TYPE_REPORT, 'Report'),
        (DOC_TYPE_INVOICE, 'Invoice'),
        (DOC_TYPE_LEGAL, 'Legal'),
        (DOC_TYPE_SAFETY_CIRCULAR, 'Safety Circular'),
        (DOC_TYPE_OTHER, 'Other'),
    ]

    STATUS_UPLOADED = 'uploaded'
    STATUS_PENDING_APPROVAL = 'pending approval'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_ARCHIVED = 'archived'

    STATUS_CHOICES = [
        (STATUS_UPLOADED, 'Uploaded'),
        (STATUS_PENDING_APPROVAL, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    title = models.CharField(max_length=255)
    document_type = models.CharField(
        max_length=30,
        choices=DOCUMENT_TYPE_CHOICES,
        default=DOC_TYPE_OTHER,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    confidentiality = models.CharField(
        max_length=20,
        choices=CONFIDENTIALITY_CHOICES,
        default=CONFIDENTIALITY_INTERNAL,
    )
    status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        default=STATUS_UPLOADED,
    )
    previous_status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        blank=True,
        default='',
        help_text='Stores status prior to archiving for restoration on unarchive.',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_documents',
    )
    created_date = models.DateTimeField(auto_now_add=True)
    current_version = models.ForeignKey(
        'DocumentVersion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return self.title


class DocumentVersion(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='versions',
    )
    version_number = models.PositiveIntegerField(default=1)
    file = models.FileField(upload_to='documents/%Y/%m/')
    extracted_text = models.TextField(blank=True, default='')
    text_found = models.BooleanField(
        default=False,
        help_text='Flag indicating whether text was found in the file',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_versions',
    )
    created_date = models.DateTimeField(auto_now_add=True)
    change_note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['document', '-version_number']
        unique_together = ('document', 'version_number')

    def __str__(self):
        return f"{self.document.title} (v{self.version_number})"
