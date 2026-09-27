from django.conf import settings
from django.db import models


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text='User who receives the notification.',
    )
    message = models.CharField(
        max_length=255,
        help_text='Notification message text.',
    )
    link = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default='',
        help_text='Optional relative URL to send the user to when clicked.',
    )
    is_read = models.BooleanField(
        default=False,
        help_text='Designates whether this notification has been read.',
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        help_text='Date and time when the notification was created.',
    )

    class Meta:
        ordering = ['-created_date']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        recipient_name = self.recipient.username if self.recipient else 'Unknown'
        return f"Notification for {recipient_name}: {self.message[:30]}"
