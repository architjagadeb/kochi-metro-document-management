import os
from django import forms

from accounts.models import Department, User
from accounts.permissions import (
    CONFIDENTIALITY_CHOICES,
    CONFIDENTIALITY_INTERNAL,
    CONFIDENTIALITY_PUBLIC,
    CONFIDENTIALITY_RESTRICTED,
)
from .models import Document

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = ('.pdf', '.docx')


class DocumentUploadForm(forms.Form):
    file = forms.FileField(
        label='Document File',
        widget=forms.FileInput(attrs={
            'accept': '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'id': 'id_file',
        }),
    )
    title = forms.CharField(
        max_length=255,
        required=False,
        label='Document Title',
        widget=forms.TextInput(attrs={
            'placeholder': 'Defaults to file name if left blank',
            'id': 'id_title',
        }),
    )
    document_type = forms.ChoiceField(
        label='Document Type',
        choices=[('auto', 'Auto detect')] + Document.DOCUMENT_TYPE_CHOICES,
        initial='auto',
        widget=forms.Select(attrs={'id': 'id_document_type'}),
    )
    confidentiality = forms.ChoiceField(
        label='Confidentiality',
        choices=CONFIDENTIALITY_CHOICES,
        initial=CONFIDENTIALITY_INTERNAL,
        widget=forms.Select(attrs={'id': 'id_confidentiality'}),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
        label='Department',
        widget=forms.Select(attrs={'id': 'id_department'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Employees can only choose public or internal; officers and admins can choose all three
        if user and getattr(user, 'role', None) == User.ROLE_EMPLOYEE:
            self.fields['confidentiality'].choices = [
                (CONFIDENTIALITY_PUBLIC, 'Public'),
                (CONFIDENTIALITY_INTERNAL, 'Internal'),
            ]

        # The department is the uploader's own, except admins who can choose it
        is_admin = user and (getattr(user, 'role', None) == User.ROLE_ADMIN or getattr(user, 'is_superuser', False))
        if is_admin:
            self.fields['department'].required = True
            if user and user.department:
                self.fields['department'].initial = user.department
        else:
            self.fields['department'].widget = forms.HiddenInput()
            if user and user.department:
                self.fields['department'].initial = user.department

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            raise forms.ValidationError('A document file is required.')

        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError('Only PDF and DOCX files are allowed.')

        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            raise forms.ValidationError('File size cannot exceed 10 MB.')

        return uploaded_file

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        uploaded_file = self.cleaned_data.get('file')
        if not title and uploaded_file:
            filename = uploaded_file.name
            title = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ').strip()
        return title or 'Untitled Document'

    def clean(self):
        cleaned_data = super().clean()
        is_admin = self.user and (getattr(self.user, 'role', None) == User.ROLE_ADMIN or getattr(self.user, 'is_superuser', False))
        if not is_admin:
            if not self.user or not self.user.department:
                raise forms.ValidationError('Your user account is not assigned to a department.')
            cleaned_data['department'] = self.user.department
        elif not cleaned_data.get('department'):
            raise forms.ValidationError('Please select a department for this document.')

        return cleaned_data


class DocumentNewVersionForm(forms.Form):
    file = forms.FileField(
        label='Version File',
        widget=forms.FileInput(attrs={
            'accept': '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'id': 'id_version_file',
        }),
    )
    change_note = forms.CharField(
        max_length=500,
        required=False,
        label='Change Note',
        widget=forms.Textarea(attrs={
            'placeholder': 'Summary of changes in this version (optional)',
            'id': 'id_change_note',
            'rows': 3,
        }),
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            raise forms.ValidationError('A document file is required.')

        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError('Only PDF and DOCX files are allowed.')

        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            raise forms.ValidationError('File size cannot exceed 10 MB.')

        return uploaded_file


class DocumentResubmitForm(forms.Form):
    title = forms.CharField(
        max_length=255,
        required=True,
        label='Document Title',
        widget=forms.TextInput(attrs={
            'id': 'id_resubmit_title',
            'class': 'form-input',
        }),
    )
    file = forms.FileField(
        required=False,
        label='New Document File (Optional)',
        widget=forms.FileInput(attrs={
            'accept': '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'id': 'id_resubmit_file',
            'class': 'version-file-input',
        }),
    )
    document_type = forms.ChoiceField(
        label='Document Type',
        choices=Document.DOCUMENT_TYPE_CHOICES,
        widget=forms.Select(attrs={'id': 'id_resubmit_document_type', 'class': 'form-select'}),
    )
    confidentiality = forms.ChoiceField(
        label='Confidentiality',
        choices=CONFIDENTIALITY_CHOICES,
        widget=forms.Select(attrs={'id': 'id_resubmit_confidentiality', 'class': 'form-select'}),
    )
    note = forms.CharField(
        required=False,
        label='Note Addressing Rejection',
        widget=forms.Textarea(attrs={
            'placeholder': 'Explain what was revised or address the rejection feedback (optional)...',
            'id': 'id_resubmit_note',
            'rows': 3,
            'class': 'form-textarea',
        }),
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            return None

        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError('Only PDF and DOCX files are allowed.')

        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            raise forms.ValidationError('File size cannot exceed 10 MB.')

        return uploaded_file

    def __init__(self, *args, user=None, document=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.document = document

        if document and not self.is_bound:
            self.fields['title'].initial = document.title
            self.fields['document_type'].initial = document.document_type
            self.fields['confidentiality'].initial = document.confidentiality

        if user and getattr(user, 'role', None) == User.ROLE_EMPLOYEE:
            self.fields['confidentiality'].choices = [
                (CONFIDENTIALITY_PUBLIC, 'Public'),
                (CONFIDENTIALITY_INTERNAL, 'Internal'),
            ]


