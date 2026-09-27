from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect

from .models import Notification


@login_required
def mark_all_notifications_read(request):
    """
    Mark all unread notifications for current user as read.
    Supports JSON response for AJAX and standard redirect fallback.
    """
    if request.method == 'POST':
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'ok', 'unread_count': 0})
    return redirect('landing')


@login_required
def mark_notification_read(request, id):
    """
    Mark a single notification for current user as read.
    Supports JSON response for AJAX and standard redirect fallback.
    """
    notification = get_object_or_404(Notification, id=id, recipient=request.user)
    if request.method == 'POST':
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
            return JsonResponse({'status': 'ok', 'unread_count': unread_count})
    return redirect('landing')
