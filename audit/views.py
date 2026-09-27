from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from accounts.models import User
from .models import AuditLog


@login_required
def audit_list(request):
    """
    List audit log entries, newest first.
    Visible only to admins, returning 404 for non-admin users.
    Supports filtering by action, user, and created date range.
    """
    user = request.user
    is_admin = getattr(user, 'role', None) == User.ROLE_ADMIN or getattr(user, 'is_superuser', False)
    if not is_admin:
        raise Http404('Page not found.')

    queryset = AuditLog.objects.select_related('user', 'document').order_by('-timestamp')

    action_filter = request.GET.get('action', '').strip()
    user_filter = request.GET.get('user', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if action_filter:
        queryset = queryset.filter(action=action_filter)

    if user_filter and user_filter.isdigit():
        queryset = queryset.filter(user_id=int(user_filter))

    if date_from:
        try:
            parsed_date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            queryset = queryset.filter(timestamp__date__gte=parsed_date_from)
        except ValueError:
            pass

    if date_to:
        try:
            parsed_date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            queryset = queryset.filter(timestamp__date__lte=parsed_date_to)
        except ValueError:
            pass

    entries = list(queryset)

    # Distinct actions and users for filter dropdowns
    distinct_actions = AuditLog.objects.values_list('action', flat=True).distinct().order_by('action')
    users = User.objects.all().order_by('username')

    has_filters = bool(action_filter or user_filter or date_from or date_to)

    return render(request, 'audit/audit_list.html', {
        'entries': entries,
        'total_count': len(entries),
        'distinct_actions': distinct_actions,
        'users': users,
        'selected_action': action_filter,
        'selected_user': user_filter,
        'date_from': date_from,
        'date_to': date_to,
        'has_filters': has_filters,
    })
