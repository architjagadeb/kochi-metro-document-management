from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .models import User
from .permissions import can_view
from documents.models import Document


def get_dashboard_data(user):
    """
    Fetch summary metrics and activity feeds for the dashboard based on user permissions.
    """
    if getattr(user, 'role', None) == User.ROLE_OFFICER:
        approvals_label = 'Awaiting approval'
        if user and user.is_authenticated and user.department_id:
            approvals_value = Document.objects.filter(
                department_id=user.department_id,
                status=Document.STATUS_PENDING_APPROVAL,
            ).count()
        else:
            approvals_value = 0
        try:
            approvals_link = reverse('workflow_pending_list')
        except Exception:
            approvals_link = '/workflow/pending/'
    elif getattr(user, 'role', None) == User.ROLE_ADMIN or getattr(user, 'is_superuser', False):
        approvals_label = 'Pending approvals'
        if user and user.is_authenticated:
            approvals_value = Document.objects.filter(
                status=Document.STATUS_PENDING_APPROVAL,
            ).count()
        else:
            approvals_value = 0
        try:
            approvals_link = reverse('workflow_pending_list')
        except Exception:
            approvals_link = '/workflow/pending/'
    else:
        approvals_label = 'My submissions'
        if user and user.is_authenticated:
            approvals_value = Document.objects.filter(
                uploaded_by=user,
                status__in=[Document.STATUS_PENDING_APPROVAL, Document.STATUS_REJECTED],
            ).count()
        else:
            approvals_value = 0
        approvals_link = None

    # Get all documents ordered newest first and filter by can_view
    all_docs = list(Document.objects.select_related('department', 'uploaded_by', 'current_version').order_by('-created_date'))
    visible_docs = [
        doc for doc in all_docs
        if can_view(user, doc.department, doc.confidentiality)
    ]
    total_docs_count = len(visible_docs)

    # Filter visible documents created within the last 7 days (excluding archived documents)
    seven_days_ago = timezone.now() - timedelta(days=7)
    recent_visible_docs = [
        doc for doc in visible_docs
        if doc.created_date >= seven_days_ago and doc.status != Document.STATUS_ARCHIVED
    ]
    recent_uploads_count = len(recent_visible_docs)
    recent_uploads_list = recent_visible_docs[:5]

    try:
        docs_link = reverse('document_list')
    except Exception:
        docs_link = '/documents/'

    return {
        'cards': [
            {
                'key': 'total_docs',
                'label': 'Total documents',
                'value': total_docs_count,
                'link': docs_link,
                'is_primary': False,
            },
            {
                'key': 'approvals',
                'label': approvals_label,
                'value': approvals_value,
                'link': approvals_link,
                'is_primary': True,
            },
            {
                'key': 'recent_uploads',
                'label': 'Recent uploads',
                'value': recent_uploads_count,
                'link': None,
                'is_primary': False,
            },
            {
                'key': 'notifications',
                'label': 'Notifications',
                'value': 0,
                'link': None,
                'is_primary': False,
            },
        ],
        'recent_uploads': recent_uploads_list,
        'notifications': [],
    }


@login_required
def landing_page(request):
    dashboard_data = get_dashboard_data(request.user)
    return render(request, 'accounts/landing.html', {
        'user': request.user,
        'dashboard': dashboard_data,
    })
