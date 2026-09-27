import os
from datetime import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import Department, User
from accounts.permissions import can_view
from .forms import DocumentNewVersionForm, DocumentResubmitForm, DocumentUploadForm
from .models import Document, DocumentVersion
from .utils import extract_text, guess_document_type


@login_required
def document_list(request):
    """
    List all documents visible to the current user based on can_view permissions.
    Supports search across title and extracted text, filtering by document type,
    department, status, and created date range.
    """
    q = request.GET.get('q', '').strip()
    document_type = request.GET.get('document_type', '').strip()
    department_id = request.GET.get('department', '').strip()
    status = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    queryset = Document.objects.select_related('department', 'uploaded_by', 'current_version').order_by('-created_date')

    if q:
        queryset = queryset.filter(
            Q(title__icontains=q) | Q(versions__extracted_text__icontains=q)
        ).distinct()

    if document_type:
        queryset = queryset.filter(document_type=document_type)

    if department_id:
        if department_id.isdigit():
            queryset = queryset.filter(department_id=int(department_id))

    if status:
        queryset = queryset.filter(status=status)

    if date_from:
        try:
            parsed_date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            queryset = queryset.filter(created_date__date__gte=parsed_date_from)
        except ValueError:
            pass

    if date_to:
        try:
            parsed_date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            queryset = queryset.filter(created_date__date__lte=parsed_date_to)
        except ValueError:
            pass

    visible_docs = [
        doc for doc in queryset
        if can_view(request.user, doc.department, doc.confidentiality)
    ]

    has_filters = bool(q or document_type or department_id or status or date_from or date_to)

    departments = Department.objects.all().order_by('name')
    document_types = Document.DOCUMENT_TYPE_CHOICES
    statuses = Document.STATUS_CHOICES

    return render(request, 'documents/document_list.html', {
        'documents': visible_docs,
        'total_count': len(visible_docs),
        'q': q,
        'selected_type': document_type,
        'selected_department': department_id,
        'selected_status': status,
        'date_from': date_from,
        'date_to': date_to,
        'has_filters': has_filters,
        'departments': departments,
        'document_types': document_types,
        'statuses': statuses,
    })


@login_required
def document_detail(request, id):
    """
    Display document metadata and all versions.
    Returns 404 if the user is not permitted to view the document.
    """
    document = get_object_or_404(
        Document.objects.select_related('department', 'uploaded_by', 'current_version'),
        id=id,
    )

    if not can_view(request.user, document.department, document.confidentiality):
        raise Http404('Document not found.')

    ai_question = ''
    ai_answer = None

    if request.method == 'POST' and 'ai_question' in request.POST:
        ai_question = request.POST.get('ai_question', '').strip()
        if ai_question:
            from .ai_utils import ask_document
            from audit.utils import log_action

            ai_answer = ask_document(document, ai_question)
            log_action(
                user=request.user,
                action='ai_query',
                document=document,
                details=ai_question,
            )

    versions = document.versions.select_related('uploaded_by').order_by('-version_number')

    is_uploader = (document.uploaded_by == request.user)
    is_admin = (getattr(request.user, 'role', None) == User.ROLE_ADMIN or getattr(request.user, 'is_superuser', False))
    can_upload_version = is_uploader or is_admin
    can_resubmit = (is_uploader and document.status == Document.STATUS_REJECTED)

    new_version_form = DocumentNewVersionForm() if can_upload_version else None
    resubmit_form = DocumentResubmitForm(user=request.user, document=document) if can_resubmit else None

    return render(request, 'documents/document_detail.html', {
        'document': document,
        'versions': versions,
        'can_upload_version': can_upload_version,
        'new_version_form': new_version_form,
        'can_resubmit': can_resubmit,
        'resubmit_form': resubmit_form,
        'ai_question': ai_question,
        'ai_answer': ai_answer,
    })


@login_required
def resubmit_document(request, id):
    """
    Resubmit a rejected document.
    Allowed only for the original uploader, and only when status is rejected.
    Optionally accepts a new document file, creating a new version.
    Updates title, document_type, confidentiality, sets status to 'pending approval',
    creates a new Approval record in workflow, and logs 'resubmit' action to audit.
    """
    document = get_object_or_404(Document, id=id)

    if not can_view(request.user, document.department, document.confidentiality):
        raise Http404('Document not found.')

    if document.uploaded_by != request.user or document.status != Document.STATUS_REJECTED:
        raise Http404('You cannot resubmit this document.')

    if request.method == 'POST':
        form = DocumentResubmitForm(request.POST, request.FILES, user=request.user, document=document)
        if form.is_valid():
            uploaded_file = form.cleaned_data.get('file')
            note = form.cleaned_data.get('note', '')
            has_new_file = bool(uploaded_file)

            if has_new_file:
                try:
                    extracted_text = extract_text(uploaded_file)
                except Exception:
                    extracted_text = ''

                latest_version = document.versions.order_by('-version_number').first()
                next_version_num = (latest_version.version_number + 1) if latest_version else 1
                has_text = bool(extracted_text and extracted_text.strip())

                new_version = DocumentVersion.objects.create(
                    document=document,
                    version_number=next_version_num,
                    file=uploaded_file,
                    extracted_text=extracted_text,
                    text_found=has_text,
                    uploaded_by=request.user,
                    change_note=note,
                )
                document.current_version = new_version

            document.title = form.cleaned_data['title']
            document.document_type = form.cleaned_data['document_type']
            document.confidentiality = form.cleaned_data['confidentiality']
            document.status = Document.STATUS_PENDING_APPROVAL

            update_fields = ['title', 'document_type', 'confidentiality', 'status']
            if has_new_file:
                update_fields.append('current_version')
            document.save(update_fields=update_fields)

            # Create new Approval record with status pending
            from workflow.models import Approval
            Approval.objects.create(
                document=document,
                status=Approval.STATUS_PENDING,
                comment=note,
            )

            # Log to audit app with file attachment details
            audit_details = f"New file attached: {'Yes' if has_new_file else 'No'}. Note: {note}".strip() if note else f"New file attached: {'Yes' if has_new_file else 'No'}."
            from audit.utils import log_action
            log_action(
                user=request.user,
                action='resubmit',
                document=document,
                details=audit_details,
            )

            messages.success(request, f'Document "{document.title}" has been resubmitted for approval.')
            return redirect('document_detail', id=document.id)
        else:
            messages.error(request, 'Please correct the errors in the resubmission form.')

    return redirect('document_detail', id=document.id)


@login_required
def toggle_document_archive(request, id):
    """
    Archive or unarchive a document.
    Allowed only for the original uploader or an administrator.
    Restores the previous status upon unarchiving.
    """
    document = get_object_or_404(Document, id=id)

    if not can_view(request.user, document.department, document.confidentiality):
        raise Http404('Document not found.')

    is_uploader = (document.uploaded_by == request.user)
    is_admin = (getattr(request.user, 'role', None) == User.ROLE_ADMIN or getattr(request.user, 'is_superuser', False))

    if not (is_uploader or is_admin):
        raise Http404('You do not have permission to archive or unarchive this document.')

    if request.method == 'POST':
        if document.status == Document.STATUS_ARCHIVED:
            restored_status = document.previous_status or Document.STATUS_UPLOADED
            document.status = restored_status
            document.previous_status = ''
            document.save(update_fields=['status', 'previous_status'])
            messages.success(request, f'Document "{document.title}" has been unarchived.')
        else:
            document.previous_status = document.status
            document.status = Document.STATUS_ARCHIVED
            document.save(update_fields=['status', 'previous_status'])
            messages.success(request, f'Document "{document.title}" has been archived.')

    return redirect('document_detail', id=document.id)


@login_required
def upload_new_version(request, id):
    """
    Upload a new version for an existing document.
    Allowed only for the original uploader or an administrator.
    """
    document = get_object_or_404(Document, id=id)

    if not can_view(request.user, document.department, document.confidentiality):
        raise Http404('Document not found.')

    is_uploader = (document.uploaded_by == request.user)
    is_admin = (getattr(request.user, 'role', None) == User.ROLE_ADMIN or getattr(request.user, 'is_superuser', False))

    if not (is_uploader or is_admin):
        raise Http404('You do not have permission to upload a new version for this document.')

    if request.method == 'POST':
        form = DocumentNewVersionForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data['file']
            change_note = form.cleaned_data.get('change_note', '')

            # Extract text safely
            try:
                extracted_text = extract_text(uploaded_file)
            except Exception:
                extracted_text = ''

            # Compute next version number
            latest_version = document.versions.order_by('-version_number').first()
            next_version_num = (latest_version.version_number + 1) if latest_version else 1

            has_text = bool(extracted_text and extracted_text.strip())
            new_version = DocumentVersion.objects.create(
                document=document,
                version_number=next_version_num,
                file=uploaded_file,
                extracted_text=extracted_text,
                text_found=has_text,
                uploaded_by=request.user,
                change_note=change_note,
            )

            document.current_version = new_version
            document.save(update_fields=['current_version'])

            messages.success(request, f'Version {new_version.version_number} uploaded successfully.')
            return redirect('document_detail', id=document.id)
        else:
            messages.error(request, 'Error uploading new version. Please check the file requirements (PDF/DOCX up to 10 MB).')

    return redirect('document_detail', id=document.id)


@login_required
def document_version_download(request, id, version_id):
    """
    Download a document version file securely.
    Verifies can_view permissions before streaming the file back to the browser.
    """
    document = get_object_or_404(Document, id=id)

    if not can_view(request.user, document.department, document.confidentiality):
        raise Http404('Document not found.')

    version = get_object_or_404(DocumentVersion, id=version_id, document=document)

    if not version.file or not version.file.storage.exists(version.file.name):
        raise Http404('File not found.')

    filename = os.path.basename(version.file.name)
    response = FileResponse(
        version.file.open('rb'),
        as_attachment=True,
        filename=filename,
    )
    return response


@login_required
def upload_document(request):
    """
    Handle document file upload at /documents/upload/.
    Extracts text, guesses document type if Auto detect is selected,
    creates Document and DocumentVersion (v1), and redirects to the dashboard.
    """
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            uploaded_file = form.cleaned_data['file']
            title = form.cleaned_data['title']
            doc_type_choice = form.cleaned_data['document_type']
            confidentiality = form.cleaned_data['confidentiality']
            department = form.cleaned_data['department']

            # Extract text safely
            try:
                extracted_text = extract_text(uploaded_file)
            except Exception:
                extracted_text = ''

            # Guess document type if Auto detect is selected
            if doc_type_choice == 'auto':
                final_doc_type = guess_document_type(extracted_text)
            else:
                final_doc_type = doc_type_choice

            # Create document
            document = Document.objects.create(
                title=title,
                document_type=final_doc_type,
                department=department,
                confidentiality=confidentiality,
                status=Document.STATUS_PENDING_APPROVAL,
                uploaded_by=request.user,
            )

            # Create version 1
            has_text = bool(extracted_text and extracted_text.strip())
            version = DocumentVersion.objects.create(
                document=document,
                version_number=1,
                file=uploaded_file,
                extracted_text=extracted_text,
                text_found=has_text,
                uploaded_by=request.user,
                change_note='Initial upload',
            )

            document.current_version = version
            document.save(update_fields=['current_version'])

            # Automatically create one Approval record for the document
            from workflow.models import Approval
            Approval.objects.create(
                document=document,
                status=Approval.STATUS_PENDING,
            )

            messages.success(request, f'Document "{document.title}" uploaded successfully.')
            return redirect('landing')
    else:
        form = DocumentUploadForm(user=request.user)

    return render(request, 'documents/upload.html', {
        'form': form,
    })
