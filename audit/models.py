from django.conf import settings
from django.db import models

from documents.models import Document


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text='User who performed the action.',
    )
    action = models.CharField(
        max_length=50,
        help_text='The action name (e.g. approve, reject).',
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text='Document associated with the action.',
    )
    details = models.TextField(
        blank=True,
        default='',
        help_text='Details or comments regarding the action.',
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text='Date and time when the action occurred.',
    )

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        user_str = self.user.username if self.user else 'System'
        doc_str = self.document.title if self.document else 'N/A'
        return f"[{self.action}] by {user_str} on {doc_str} at {self.timestamp}"
