from django.conf import settings
from django.db import models

from accounts.models import Department, User
from documents.models import Document


class ApprovalRule(models.Model):
    ROLE_OFFICER = User.ROLE_OFFICER
    ROLE_ADMIN = User.ROLE_ADMIN

    APPROVER_ROLE_CHOICES = [
        (ROLE_OFFICER, 'Officer'),
        (ROLE_ADMIN, 'Admin'),
    ]

    document_type = models.CharField(
        max_length=30,
        choices=Document.DOCUMENT_TYPE_CHOICES,
        help_text='Document type that this rule applies to.',
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='approval_rules',
        help_text='Department that this rule applies to.',
    )
    approver_role = models.CharField(
        max_length=20,
        choices=APPROVER_ROLE_CHOICES,
        help_text='Role required to approve documents matching this type and department.',
    )

    class Meta:
        ordering = ['department', 'document_type']
        unique_together = ('document_type', 'department')
        verbose_name = 'Approval Rule'
        verbose_name_plural = 'Approval Rules'

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.department.name} ({self.get_approver_role_display()})"


class Approval(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='approvals',
        help_text='The document awaiting or having undergone approval.',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text='Current status of the approval workflow.',
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decided_approvals',
        help_text='User who decided this approval.',
    )
    comment = models.TextField(
        blank=True,
        default='',
        help_text='Optional comment from the reviewer.',
    )
    decided_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Date and time when the approval decision was made.',
    )
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_date']
        verbose_name = 'Approval'
        verbose_name_plural = 'Approvals'

    def __str__(self):
        return f"Approval for {self.document.title} ({self.get_status_display()})"
