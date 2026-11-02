"""
Analytics computation service using pandas and numpy.

All data transformation, aggregation, and statistical logic are placed
here, cleanly separated from the presentation views.
"""
from datetime import timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from django.utils import timezone

from accounts.permissions import can_view
from documents.models import Document
from workflow.models import Approval

DOCUMENT_COLUMNS = [
    'type',
    'department',
    'confidentiality',
    'status',
    'uploader',
    'created date',
]

APPROVAL_COLUMNS = [
    'approval_id',
    'document_id',
    'document_title',
    'status',
    'uploader',
    'decided_by',
    'upload_date',
    'decided_date',
    'turnaround_hours',
]


class DocumentsDataFrame(pd.DataFrame):
    """
    Subclass of pd.DataFrame providing transparent support for accessing
    the created date column via either 'created date' or 'created_date'.
    """

    @property
    def _constructor(self):
        return DocumentsDataFrame

    def __getitem__(self, key):
        if key == 'created_date' and 'created_date' not in self.columns and 'created date' in self.columns:
            return super().__getitem__('created date')
        if key == 'created date' and 'created date' not in self.columns and 'created_date' in self.columns:
            return super().__getitem__('created_date')
        return super().__getitem__(key)


def get_user_visible_documents(user) -> List[Document]:
    """
    Collect all documents visible to the current user using the can_view permission function.
    """
    all_documents = list(
        Document.objects.select_related('department', 'uploaded_by')
        .all()
        .order_by('-created_date')
    )
    return [
        doc
        for doc in all_documents
        if can_view(user, doc.department, doc.confidentiality)
    ]


def build_documents_dataframe(documents: List[Document]) -> DocumentsDataFrame:
    """
    Build a pandas DataFrame from the provided documents with columns for
    type, department, confidentiality, status, uploader, and created date.
    """
    rows = []
    for doc in documents:
        rows.append({
            'type': doc.document_type,
            'department': doc.department.name if doc.department else '',
            'confidentiality': doc.confidentiality,
            'status': doc.status,
            'uploader': doc.uploaded_by.username if doc.uploaded_by else '',
            'created date': doc.created_date,
        })

    if not rows:
        return DocumentsDataFrame(columns=DOCUMENT_COLUMNS)

    return DocumentsDataFrame(rows, columns=DOCUMENT_COLUMNS)


def calculate_document_metrics(df: pd.DataFrame, now=None) -> Dict[str, Any]:
    """
    Using pandas groupby and value_counts, compute:
    - total documents
    - documents per type
    - documents per department
    - documents per status
    - uploads per day for the last 14 days
    """
    current_time = now or timezone.now()
    today = current_time.date()
    start_date = today - timedelta(days=13)

    total_docs = len(df)
    is_empty = total_docs == 0

    if is_empty:
        # Generate 14 days with zero counts for clean visualization
        daily_uploads = [
            {
                'date': (today - timedelta(days=i)).strftime('%Y-%m-%d'),
                'day_name': (today - timedelta(days=i)).strftime('%b %d'),
                'full_day': (today - timedelta(days=i)).strftime('%A, %b %d'),
                'count': 0,
            }
            for i in range(13, -1, -1)
        ]
        return {
            'total_documents': 0,
            'documents_by_type': [],
            'documents_by_department': [],
            'documents_by_status': [],
            'daily_uploads': daily_uploads,
            'total_recent_uploads': 0,
            'is_empty': True,
        }

    # 1. Documents per type using pandas value_counts
    type_counts = df['type'].value_counts()
    documents_by_type = [
        {
            'name': str(item_type),
            'count': int(count),
            'percentage': round((int(count) / total_docs) * 100, 1),
        }
        for item_type, count in type_counts.items()
    ]

    # 2. Documents per department using pandas groupby
    dept_counts = df.groupby('department').size().sort_values(ascending=False)
    documents_by_department = [
        {
            'name': str(dept_name) if dept_name else 'Unassigned',
            'count': int(count),
            'percentage': round((int(count) / total_docs) * 100, 1),
        }
        for dept_name, count in dept_counts.items()
    ]

    # 3. Documents per status using pandas value_counts
    status_counts = df['status'].value_counts()
    documents_by_status = [
        {
            'name': str(status_name),
            'count': int(count),
            'percentage': round((int(count) / total_docs) * 100, 1),
        }
        for status_name, count in status_counts.items()
    ]

    # 4. Uploads per day for the last 14 days using pandas datetime groupby
    created_dates = pd.to_datetime(df['created date']).dt.date
    recent_mask = (created_dates >= start_date) & (created_dates <= today)
    if recent_mask.any():
        daily_counts_series = (
            df.loc[recent_mask]
            .groupby(created_dates.loc[recent_mask])
            .size()
        )
    else:
        daily_counts_series = pd.Series(dtype=int)

    daily_uploads = []
    total_recent_uploads = 0
    for i in range(13, -1, -1):
        day_date = today - timedelta(days=i)
        day_count = int(daily_counts_series.get(day_date, 0))
        total_recent_uploads += day_count
        daily_uploads.append({
            'date': day_date.strftime('%Y-%m-%d'),
            'day_name': day_date.strftime('%b %d'),
            'full_day': day_date.strftime('%A, %b %d'),
            'count': day_count,
        })

    return {
        'total_documents': total_docs,
        'documents_by_type': documents_by_type,
        'documents_by_department': documents_by_department,
        'documents_by_status': documents_by_status,
        'daily_uploads': daily_uploads,
        'total_recent_uploads': total_recent_uploads,
        'is_empty': False,
    }


def build_approvals_dataframe(documents: List[Document]) -> pd.DataFrame:
    """
    Build a second DataFrame from the Approval records of the specified documents.
    Computes turnaround in hours for decided approvals.
    """
    if not documents:
        return pd.DataFrame(columns=APPROVAL_COLUMNS)

    approvals = (
        Approval.objects.filter(document__in=documents)
        .select_related('document', 'decided_by', 'document__uploaded_by')
        .order_by('-decided_date', '-created_date')
    )

    rows = []
    for approval in approvals:
        doc = approval.document
        is_decided = (
            approval.status in (Approval.STATUS_APPROVED, Approval.STATUS_REJECTED)
            and approval.decided_date is not None
        )

        turnaround_hours: Optional[float] = None
        if is_decided and doc.created_date and approval.decided_date:
            raw_hours = (approval.decided_date - doc.created_date).total_seconds() / 3600.0
            turnaround_hours = max(0.0, raw_hours)

        rows.append({
            'approval_id': approval.id,
            'document_id': doc.id,
            'document_title': doc.title,
            'status': approval.status,
            'uploader': doc.uploaded_by.username if doc.uploaded_by else '',
            'decided_by': approval.decided_by.username if approval.decided_by else '',
            'upload_date': doc.created_date,
            'decided_date': approval.decided_date,
            'turnaround_hours': turnaround_hours,
        })

    if not rows:
        return pd.DataFrame(columns=APPROVAL_COLUMNS)

    return pd.DataFrame(rows, columns=APPROVAL_COLUMNS)


def calculate_approval_metrics(approvals_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Use numpy to calculate average, median, and 90th percentile turnaround in hours
    for decided approvals only.
    """
    if approvals_df.empty or 'turnaround_hours' not in approvals_df.columns:
        return {
            'total_approvals': 0,
            'total_decided': 0,
            'avg_turnaround_hours': None,
            'median_turnaround_hours': None,
            'p90_turnaround_hours': None,
            'has_decided_data': False,
            'decided_records': [],
        }

    decided_df = approvals_df[
        approvals_df['status'].isin([Approval.STATUS_APPROVED, Approval.STATUS_REJECTED])
        & approvals_df['turnaround_hours'].notna()
    ]

    total_approvals = len(approvals_df)
    total_decided = len(decided_df)

    if total_decided == 0:
        return {
            'total_approvals': total_approvals,
            'total_decided': 0,
            'avg_turnaround_hours': None,
            'median_turnaround_hours': None,
            'p90_turnaround_hours': None,
            'has_decided_data': False,
            'decided_records': [],
        }

    turnaround_array = decided_df['turnaround_hours'].to_numpy(dtype=float)

    # Use numpy to compute average, median, and 90th percentile
    avg_turnaround = float(np.mean(turnaround_array))
    median_turnaround = float(np.median(turnaround_array))
    p90_turnaround = float(np.percentile(turnaround_array, 90))

    decided_records = []
    for _, row in decided_df.head(10).iterrows():
        decided_records.append({
            'document_title': row['document_title'],
            'status': row['status'],
            'decided_by': row['decided_by'] or 'System',
            'upload_date': row['upload_date'],
            'decided_date': row['decided_date'],
            'turnaround_hours': round(row['turnaround_hours'], 1),
        })

    return {
        'total_approvals': total_approvals,
        'total_decided': total_decided,
        'avg_turnaround_hours': round(avg_turnaround, 1),
        'median_turnaround_hours': round(median_turnaround, 1),
        'p90_turnaround_hours': round(p90_turnaround, 1),
        'has_decided_data': True,
        'decided_records': decided_records,
    }


def export_documents_to_csv(df: pd.DataFrame) -> str:
    """
    Export the documents DataFrame to CSV using pandas to_csv.
    """
    return df.to_csv(index=False)
