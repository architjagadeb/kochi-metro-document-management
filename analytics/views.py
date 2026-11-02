"""
Views for the analytics app.
Provides the analytics dashboard and CSV download endpoints,
accessible exclusively by officers and administrators.
"""
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render

from accounts.models import User
from .services import (
    build_approvals_dataframe,
    build_documents_dataframe,
    calculate_approval_metrics,
    calculate_document_metrics,
    export_documents_to_csv,
    get_user_visible_documents,
)


def _check_analytics_permission(user) -> None:
    """
    Ensure the user is an officer, admin, or superuser.
    Raises Http404 for all other users, matching the audit page pattern.
    """
    is_officer = getattr(user, 'role', None) == User.ROLE_OFFICER
    is_admin = getattr(user, 'role', None) == User.ROLE_ADMIN
    is_superuser = getattr(user, 'is_superuser', False)

    if not (is_officer or is_admin or is_superuser):
        raise Http404('Page not found.')


@login_required
def analytics_dashboard(request):
    """
    Render the analytics dashboard with document breakdowns and approval turnaround metrics.
    Supports CSV export when 'export=csv' or 'format=csv' query param is passed.
    """
    _check_analytics_permission(request.user)

    # 1. Collect visible documents according to permissions
    documents = get_user_visible_documents(request.user)

    # 2. Build pandas DataFrame for documents
    docs_df = build_documents_dataframe(documents)

    # Support inline CSV export parameter
    if request.GET.get('format') == 'csv' or request.GET.get('export') == 'csv':
        csv_content = export_documents_to_csv(docs_df)
        response = HttpResponse(csv_content, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="documents_analytics.csv"'
        return response

    # 3. Calculate document aggregation metrics
    doc_metrics = calculate_document_metrics(docs_df)

    # 4. Build approvals DataFrame and compute numpy turnaround stats
    approvals_df = build_approvals_dataframe(documents)
    approval_metrics = calculate_approval_metrics(approvals_df)

    context = {
        'doc_metrics': doc_metrics,
        'approval_metrics': approval_metrics,
        'user': request.user,
    }
    return render(request, 'analytics/analytics_dashboard.html', context)


@login_required
def export_csv_view(request):
    """
    Dedicated view to export the visible documents DataFrame as a CSV file.
    """
    _check_analytics_permission(request.user)

    documents = get_user_visible_documents(request.user)
    docs_df = build_documents_dataframe(documents)
    csv_content = export_documents_to_csv(docs_df)

    response = HttpResponse(csv_content, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="documents_analytics.csv"'
    return response
