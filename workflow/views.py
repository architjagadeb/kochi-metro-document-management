from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from audit.utils import log_action
from documents.models import Document
from .models import Approval


def user_can_approve_or_reject(user, document):
    """
    Check if a user is an admin or an officer in the document's department.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'role', None) == User.ROLE_ADMIN or getattr(user, 'is_superuser', False):
        return True
    if getattr(user, 'role', None) == User.ROLE_OFFICER:
        return (user.department_id is not None) and (user.department_id == document.department_id)
    return False


@login_required
def pending_list(request):
    """
    List documents currently pending approval.
    Visible to officers and admins, filtered to their own department
    using the same department logic as can_view.
    """
    user = request.user
    is_officer_or_admin = (
        getattr(user, 'role', None) in (User.ROLE_OFFICER, User.ROLE_ADMIN)
        or getattr(user, 'is_superuser', False)
    )

    if not is_officer_or_admin:
        raise Http404('Page not found.')

    queryset = Document.objects.filter(
        status=Document.STATUS_PENDING_APPROVAL
    ).select_related('department', 'uploaded_by', 'current_version').order_by('-created_date')

    if user.role == User.ROLE_ADMIN or user.is_superuser:
        pending_docs = list(queryset)
    else:
        pending_docs = [
            doc for doc in queryset
            if doc.department_id == user.department_id
        ]

    return render(request, 'workflow/pending_list.html', {
        'documents': pending_docs,
        'total_count': len(pending_docs),
    })


@login_required
def approve_document(request, document_id):
    """
    Approve a pending document.
    Sets Approval to approved, decided_by, decided_date, document status to approved,
    accepts an optional comment, and logs the action to audit.
    """
    document = get_object_or_404(Document, id=document_id)

    if not user_can_approve_or_reject(request.user, document):
        raise Http404('You do not have permission to approve this document.')

    if request.method == 'POST':
        comment = request.POST.get('comment', '').strip()
        now = timezone.now()

        approval = document.approvals.filter(status=Approval.STATUS_PENDING).first()
        if not approval:
            approval = Approval(document=document)

        approval.status = Approval.STATUS_APPROVED
        approval.decided_by = request.user
        approval.decided_date = now
        approval.comment = comment
        approval.save()

        document.status = Document.STATUS_APPROVED
        document.save(update_fields=['status'])

        log_action(
            user=request.user,
            action='approve',
            document=document,
            details=comment,
        )

        messages.success(request, f'Document "{document.title}" has been approved.')

    return redirect('workflow_pending_list')


@login_required
def reject_document(request, document_id):
    """
    Reject a pending document. Requires a comment.
    Sets Approval to rejected, decided_by, decided_date, document status to rejected,
    and logs the action to audit.
    """
    document = get_object_or_404(Document, id=document_id)

    if not user_can_approve_or_reject(request.user, document):
        raise Http404('You do not have permission to reject this document.')

    if request.method == 'POST':
        comment = request.POST.get('comment', '').strip()
        if not comment:
            messages.error(request, 'A comment is required when rejecting a document.')
            return redirect('workflow_pending_list')

        now = timezone.now()

        approval = document.approvals.filter(status=Approval.STATUS_PENDING).first()
        if not approval:
            approval = Approval(document=document)

        approval.status = Approval.STATUS_REJECTED
        approval.decided_by = request.user
        approval.decided_date = now
        approval.comment = comment
        approval.save()

        document.status = Document.STATUS_REJECTED
        document.save(update_fields=['status'])

        log_action(
            user=request.user,
            action='reject',
            document=document,
            details=comment,
        )

        messages.success(request, f'Document "{document.title}" has been rejected.')

    return redirect('workflow_pending_list')
