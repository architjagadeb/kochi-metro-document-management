import csv
import io
from datetime import timedelta

import numpy as np
import pandas as pd
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Department, User
from accounts.permissions import (
    CONFIDENTIALITY_INTERNAL,
    CONFIDENTIALITY_PUBLIC,
    CONFIDENTIALITY_RESTRICTED,
)
from documents.models import Document
from workflow.models import Approval
from analytics.services import (
    DOCUMENT_COLUMNS,
    build_approvals_dataframe,
    build_documents_dataframe,
    calculate_approval_metrics,
    calculate_document_metrics,
    export_documents_to_csv,
    get_user_visible_documents,
)


class AnalyticsAccessAndDashboardLinkTests(TestCase):
    """
    Tests for permission-based access control and dashboard link visibility.
    Access to /analytics/ must be restricted to officers and admins (404 for others).
    """

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name='Operations')

        self.admin_user = User.objects.create_user(
            username='admin_user',
            password='password123',
            role=User.ROLE_ADMIN,
            department=self.dept,
        )
        self.officer_user = User.objects.create_user(
            username='officer_user',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.dept,
        )
        self.employee_user = User.objects.create_user(
            username='employee_user',
            password='password123',
            role=User.ROLE_EMPLOYEE,
            department=self.dept,
        )

        self.url = reverse('analytics_dashboard')

    def test_unauthenticated_user_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

        # CSV endpoint redirect
        csv_response = self.client.get(reverse('analytics_csv'))
        self.assertEqual(csv_response.status_code, 302)
        self.assertIn(reverse('login'), csv_response.url)

    def test_employee_gets_404(self):
        self.client.login(username='employee_user', password='password123')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

        csv_response = self.client.get(reverse('analytics_csv'))
        self.assertEqual(csv_response.status_code, 404)

    def test_officer_can_access_analytics(self):
        self.client.login(username='officer_user', password='password123')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'analytics/analytics_dashboard.html')

    def test_admin_can_access_analytics(self):
        self.client.login(username='admin_user', password='password123')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'analytics/analytics_dashboard.html')

    def test_dashboard_link_visibility(self):
        # Admin should see Analytics link on dashboard
        self.client.login(username='admin_user', password='password123')
        landing_admin = self.client.get(reverse('landing'))
        self.assertContains(landing_admin, reverse('analytics_dashboard'))

        # Officer should see Analytics link on dashboard
        self.client.login(username='officer_user', password='password123')
        landing_officer = self.client.get(reverse('landing'))
        self.assertContains(landing_officer, reverse('analytics_dashboard'))

        # Employee should NOT see Analytics link on dashboard
        self.client.login(username='employee_user', password='password123')
        landing_emp = self.client.get(reverse('landing'))
        self.assertNotContains(landing_emp, reverse('analytics_dashboard'))


class AnalyticsServiceUnitTests(TestCase):
    """
    Unit tests for pandas and numpy analytical operations in services.py.
    """

    def setUp(self):
        self.dept_ops = Department.objects.create(name='Operations')
        self.dept_fin = Department.objects.create(name='Finance')

        self.admin = User.objects.create_user(
            username='admin_svc',
            password='password123',
            role=User.ROLE_ADMIN,
            department=self.dept_ops,
        )
        self.officer_ops = User.objects.create_user(
            username='officer_ops',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.dept_ops,
        )

        now = timezone.now()

        # Document 1: Operations, Public, Tender
        self.doc1 = Document.objects.create(
            title='Track Maintenance Tender',
            document_type=Document.DOC_TYPE_TENDER,
            department=self.dept_ops,
            confidentiality=CONFIDENTIALITY_PUBLIC,
            status=Document.STATUS_APPROVED,
            uploaded_by=self.officer_ops,
        )
        # Manually backdate created_date
        Document.objects.filter(id=self.doc1.id).update(created_date=now - timedelta(hours=10))
        self.doc1.refresh_from_db()

        # Document 2: Operations, Restricted, Report
        self.doc2 = Document.objects.create(
            title='Station Safety Report',
            document_type=Document.DOC_TYPE_REPORT,
            department=self.dept_ops,
            confidentiality=CONFIDENTIALITY_RESTRICTED,
            status=Document.STATUS_REJECTED,
            uploaded_by=self.officer_ops,
        )
        Document.objects.filter(id=self.doc2.id).update(created_date=now - timedelta(hours=5))
        self.doc2.refresh_from_db()

        # Document 3: Finance, Restricted, Contract (Officer in Ops should NOT see this due to can_view)
        self.doc3 = Document.objects.create(
            title='Confidential Finance Contract',
            document_type=Document.DOC_TYPE_CONTRACT,
            department=self.dept_fin,
            confidentiality=CONFIDENTIALITY_RESTRICTED,
            status=Document.STATUS_PENDING_APPROVAL,
            uploaded_by=self.admin,
        )
        Document.objects.filter(id=self.doc3.id).update(created_date=now - timedelta(hours=2))
        self.doc3.refresh_from_db()

        # Approvals:
        # Approval 1 for doc1: Decided 6 hours after creation -> turnaround = 6.0 hrs
        self.approval1 = Approval.objects.create(
            document=self.doc1,
            status=Approval.STATUS_APPROVED,
            decided_by=self.admin,
            decided_date=self.doc1.created_date + timedelta(hours=6),
        )

        # Approval 2 for doc2: Decided 2 hours after creation -> turnaround = 2.0 hrs
        self.approval2 = Approval.objects.create(
            document=self.doc2,
            status=Approval.STATUS_REJECTED,
            decided_by=self.officer_ops,
            decided_date=self.doc2.created_date + timedelta(hours=2),
        )

        # Approval 3 for doc3: Still pending (no decision date)
        self.approval3 = Approval.objects.create(
            document=self.doc3,
            status=Approval.STATUS_PENDING,
        )

    def test_get_user_visible_documents_respects_can_view(self):
        # Officer in Ops should only see doc1 (public) and doc2 (restricted in own dept), NOT doc3 (restricted in finance)
        visible_officer = get_user_visible_documents(self.officer_ops)
        visible_ids = [d.id for d in visible_officer]
        self.assertIn(self.doc1.id, visible_ids)
        self.assertIn(self.doc2.id, visible_ids)
        self.assertNotIn(self.doc3.id, visible_ids)

        # Admin should see all 3 documents
        visible_admin = get_user_visible_documents(self.admin)
        self.assertEqual(len(visible_admin), 3)

    def test_build_documents_dataframe_structure(self):
        docs = [self.doc1, self.doc2]
        df = build_documents_dataframe(docs)

        # Assert correct columns
        self.assertEqual(list(df.columns), DOCUMENT_COLUMNS)
        self.assertEqual(len(df), 2)

        # Test transparent indexing for both 'created date' and 'created_date'
        self.assertTrue('created date' in df)
        self.assertIsNotNone(df['created date'])
        self.assertIsNotNone(df['created_date'])

        # Check values in first row
        row0 = df.iloc[0]
        self.assertEqual(row0['type'], Document.DOC_TYPE_TENDER)
        self.assertEqual(row0['department'], 'Operations')
        self.assertEqual(row0['confidentiality'], CONFIDENTIALITY_PUBLIC)
        self.assertEqual(row0['status'], Document.STATUS_APPROVED)
        self.assertEqual(row0['uploader'], self.officer_ops.username)

    def test_build_documents_dataframe_empty(self):
        df = build_documents_dataframe([])
        self.assertEqual(list(df.columns), DOCUMENT_COLUMNS)
        self.assertTrue(df.empty)
        metrics = calculate_document_metrics(df)
        self.assertTrue(metrics['is_empty'])
        self.assertEqual(metrics['total_documents'], 0)
        self.assertEqual(len(metrics['daily_uploads']), 14)

    def test_calculate_document_metrics_aggregations(self):
        docs = [self.doc1, self.doc2]
        df = build_documents_dataframe(docs)
        metrics = calculate_document_metrics(df)

        self.assertFalse(metrics['is_empty'])
        self.assertEqual(metrics['total_documents'], 2)

        # Check documents_by_type
        type_names = [item['name'] for item in metrics['documents_by_type']]
        self.assertIn(Document.DOC_TYPE_TENDER, type_names)
        self.assertIn(Document.DOC_TYPE_REPORT, type_names)

        # Check documents_by_department
        dept_names = [item['name'] for item in metrics['documents_by_department']]
        self.assertIn('Operations', dept_names)

        # Check documents_by_status
        status_names = [item['name'] for item in metrics['documents_by_status']]
        self.assertIn(Document.STATUS_APPROVED, status_names)
        self.assertIn(Document.STATUS_REJECTED, status_names)

        # Check daily uploads has 14 entries
        self.assertEqual(len(metrics['daily_uploads']), 14)
        total_in_trend = sum(day['count'] for day in metrics['daily_uploads'])
        self.assertEqual(total_in_trend, 2)

    def test_build_approvals_dataframe_and_numpy_metrics(self):
        docs = [self.doc1, self.doc2, self.doc3]
        approvals_df = build_approvals_dataframe(docs)

        self.assertEqual(len(approvals_df), 3)

        # Calculate metrics using numpy
        metrics = calculate_approval_metrics(approvals_df)

        self.assertTrue(metrics['has_decided_data'])
        self.assertEqual(metrics['total_approvals'], 3)
        self.assertEqual(metrics['total_decided'], 2)

        # Turnarounds are 6.0 and 2.0 hours
        expected_avg = np.mean([6.0, 2.0])  # 4.0
        expected_median = np.median([6.0, 2.0])  # 4.0
        expected_p90 = np.percentile([6.0, 2.0], 90)  # 5.6

        self.assertAlmostEqual(metrics['avg_turnaround_hours'], round(float(expected_avg), 1))
        self.assertAlmostEqual(metrics['median_turnaround_hours'], round(float(expected_median), 1))
        self.assertAlmostEqual(metrics['p90_turnaround_hours'], round(float(expected_p90), 1))

    def test_approval_metrics_with_no_decided_approvals(self):
        # Empty approvals
        empty_df = build_approvals_dataframe([])
        empty_metrics = calculate_approval_metrics(empty_df)
        self.assertFalse(empty_metrics['has_decided_data'])
        self.assertIsNone(empty_metrics['avg_turnaround_hours'])
        self.assertIsNone(empty_metrics['median_turnaround_hours'])
        self.assertIsNone(empty_metrics['p90_turnaround_hours'])

        # Approvals with only pending status
        pending_only_df = build_approvals_dataframe([self.doc3])
        pending_metrics = calculate_approval_metrics(pending_only_df)
        self.assertFalse(pending_metrics['has_decided_data'])
        self.assertIsNone(pending_metrics['avg_turnaround_hours'])


class AnalyticsViewIntegrationTests(TestCase):
    """
    Integration tests for /analytics/ page rendering, CSV download, and empty states.
    """

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name='Operations')

        self.officer = User.objects.create_user(
            username='officer_view',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.dept,
        )

    def test_analytics_page_empty_state_rendering(self):
        # No documents in database
        self.client.login(username='officer_view', password='password123')
        response = self.client.get(reverse('analytics_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Document &amp; Workflow Analytics')
        self.assertContains(response, 'No Document Records Found')
        self.assertContains(response, 'Download CSV')

    def test_analytics_page_with_data_rendering(self):
        # Create a document and an approval
        doc = Document.objects.create(
            title='Track Geometry Standard',
            document_type=Document.DOC_TYPE_SAFETY_CIRCULAR,
            department=self.dept,
            confidentiality=CONFIDENTIALITY_PUBLIC,
            status=Document.STATUS_APPROVED,
            uploaded_by=self.officer,
        )
        now = timezone.now()
        Approval.objects.create(
            document=doc,
            status=Approval.STATUS_APPROVED,
            decided_by=self.officer,
            decided_date=now,
        )

        self.client.login(username='officer_view', password='password123')
        response = self.client.get(reverse('analytics_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Total Documents')
        self.assertContains(response, 'safety circular')
        self.assertContains(response, 'Operations')
        self.assertContains(response, 'Uploads per Day (Last 14 Days)')
        self.assertContains(response, 'Approval Turnaround Metrics')

    def test_download_csv_button_and_response(self):
        doc = Document.objects.create(
            title='Tender 101',
            document_type=Document.DOC_TYPE_TENDER,
            department=self.dept,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            status=Document.STATUS_UPLOADED,
            uploaded_by=self.officer,
        )

        self.client.login(username='officer_view', password='password123')

        # Download via dedicated CSV endpoint
        response = self.client.get(reverse('analytics_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="documents_analytics.csv"', response['Content-Disposition'])

        csv_text = response.content.decode('utf-8')
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)

        # Header row check
        self.assertEqual(rows[0], DOCUMENT_COLUMNS)
        # Data row check
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], Document.DOC_TYPE_TENDER)
        self.assertEqual(rows[1][1], 'Operations')
        self.assertEqual(rows[1][2], CONFIDENTIALITY_INTERNAL)
        self.assertEqual(rows[1][3], Document.STATUS_UPLOADED)
        self.assertEqual(rows[1][4], self.officer.username)

        # Also test ?format=csv parameter on /analytics/
        param_response = self.client.get(reverse('analytics_dashboard'), {'format': 'csv'})
        self.assertEqual(param_response.status_code, 200)
        self.assertIn('text/csv', param_response['Content-Type'])
