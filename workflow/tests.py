from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Department
from accounts.permissions import CONFIDENTIALITY_INTERNAL
from audit.models import AuditLog
from audit.utils import log_action
from documents.models import Document, DocumentVersion
from workflow.models import Approval, ApprovalRule

User = get_user_model()


class WorkflowModelsTest(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Operations & Station Management')
        self.user = User.objects.create_user(
            username='test_user',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.dept,
        )
        self.doc = Document.objects.create(
            title='Track Maintenance Rule',
            document_type=Document.DOC_TYPE_TENDER,
            department=self.dept,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            uploaded_by=self.user,
        )

    def test_create_approval_rule(self):
        rule = ApprovalRule.objects.create(
            document_type=Document.DOC_TYPE_TENDER,
            department=self.dept,
            approver_role=ApprovalRule.ROLE_OFFICER,
        )
        self.assertEqual(rule.document_type, Document.DOC_TYPE_TENDER)
        self.assertEqual(rule.department, self.dept)
        self.assertEqual(rule.approver_role, ApprovalRule.ROLE_OFFICER)
        self.assertIn('Tender', str(rule))
        self.assertIn('Operations & Station Management', str(rule))

    def test_create_approval_record(self):
        approval = Approval.objects.create(
            document=self.doc,
        )
        self.assertEqual(approval.status, Approval.STATUS_PENDING)
        self.assertIsNone(approval.decided_by)
        self.assertEqual(approval.comment, '')
        self.assertIsNone(approval.decided_date)
        self.assertIn('Track Maintenance Rule', str(approval))
        self.assertIn('Pending', str(approval))


class WorkflowAdminTest(TestCase):
    def setUp(self):
        self.site = admin.site
        self.dept = Department.objects.create(name='Operations & Station Management')
        self.admin_user = User.objects.create_superuser(
            username='admin_boss',
            password='password123',
            role=User.ROLE_ADMIN,
            department=self.dept,
        )

    def test_models_registered_in_admin(self):
        self.assertIn(ApprovalRule, self.site._registry)
        self.assertIn(Approval, self.site._registry)

    def test_approval_admin_is_read_only(self):
        approval_admin = self.site._registry[Approval]
        request = type('Request', (), {'user': self.admin_user})()

        self.assertFalse(approval_admin.has_add_permission(request))
        self.assertFalse(approval_admin.has_change_permission(request))
        self.assertFalse(approval_admin.has_delete_permission(request))


class DocumentUploadWorkflowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name='Operations & Station Management')
        self.officer = User.objects.create_user(
            username='off_uploader',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.dept,
        )

    def test_document_upload_automatically_creates_approval(self):
        self.client.login(username='off_uploader', password='password123')
        uploaded_file = SimpleUploadedFile(
            'safety_doc.pdf',
            b'%PDF-1.4 dummy pdf content for safety circular',
            content_type='application/pdf',
        )

        response = self.client.post(reverse('document_upload'), {
            'file': uploaded_file,
            'title': 'Safety Guidelines 2026',
            'document_type': Document.DOC_TYPE_SAFETY_CIRCULAR,
            'confidentiality': CONFIDENTIALITY_INTERNAL,
        })
        self.assertRedirects(response, reverse('landing'))

        doc = Document.objects.filter(title='Safety Guidelines 2026').first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.status, Document.STATUS_PENDING_APPROVAL)

        # Confirm approval record created
        approvals = Approval.objects.filter(document=doc)
        self.assertEqual(approvals.count(), 1)
        approval = approvals.first()
        self.assertEqual(approval.status, Approval.STATUS_PENDING)
        self.assertIsNone(approval.decided_by)


class WorkflowPendingAndActionsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.ops_dept = Department.objects.create(name='Operations & Station Management')
        self.fin_dept = Department.objects.create(name='Finance & Accounts')

        self.ops_employee = User.objects.create_user(
            username='emp_ops',
            password='password123',
            role=User.ROLE_EMPLOYEE,
            department=self.ops_dept,
        )
        self.ops_officer = User.objects.create_user(
            username='off_ops',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.ops_dept,
        )
        self.fin_officer = User.objects.create_user(
            username='off_fin',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.fin_dept,
        )
        self.admin = User.objects.create_superuser(
            username='admin_user',
            password='password123',
            role=User.ROLE_ADMIN,
            department=self.fin_dept,
        )

        # Ops pending doc
        self.doc_ops = Document.objects.create(
            title='Ops Daily Shift Log',
            document_type=Document.DOC_TYPE_REPORT,
            department=self.ops_dept,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            status=Document.STATUS_PENDING_APPROVAL,
            uploaded_by=self.ops_employee,
        )
        self.approval_ops = Approval.objects.create(
            document=self.doc_ops,
            status=Approval.STATUS_PENDING,
        )

        # Fin pending doc
        self.doc_fin = Document.objects.create(
            title='Fin Vendor Invoice',
            document_type=Document.DOC_TYPE_INVOICE,
            department=self.fin_dept,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            status=Document.STATUS_PENDING_APPROVAL,
            uploaded_by=self.admin,
        )
        self.approval_fin = Approval.objects.create(
            document=self.doc_fin,
            status=Approval.STATUS_PENDING,
        )

    def test_unauthenticated_redirect(self):
        response = self.client.get(reverse('workflow_pending_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_employee_cannot_access_pending_list(self):
        self.client.login(username='emp_ops', password='password123')
        response = self.client.get(reverse('workflow_pending_list'))
        self.assertEqual(response.status_code, 404)

    def test_officer_sees_only_own_department_pending_documents(self):
        self.client.login(username='off_ops', password='password123')
        response = self.client.get(reverse('workflow_pending_list'))
        self.assertEqual(response.status_code, 200)
        docs = response.context['documents']
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0], self.doc_ops)
        self.assertContains(response, 'Ops Daily Shift Log')
        self.assertNotContains(response, 'Fin Vendor Invoice')

    def test_admin_sees_all_pending_documents(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.get(reverse('workflow_pending_list'))
        self.assertEqual(response.status_code, 200)
        docs = response.context['documents']
        self.assertEqual(len(docs), 2)

    def test_officer_can_approve_own_department_document(self):
        self.client.login(username='off_ops', password='password123')
        response = self.client.post(reverse('workflow_approve_document', args=[self.doc_ops.id]), {
            'comment': 'Looks good to proceed.',
        })
        self.assertRedirects(response, reverse('workflow_pending_list'))

        self.doc_ops.refresh_from_db()
        self.assertEqual(self.doc_ops.status, Document.STATUS_APPROVED)

        self.approval_ops.refresh_from_db()
        self.assertEqual(self.approval_ops.status, Approval.STATUS_APPROVED)
        self.assertEqual(self.approval_ops.decided_by, self.ops_officer)
        self.assertIsNotNone(self.approval_ops.decided_date)
        self.assertEqual(self.approval_ops.comment, 'Looks good to proceed.')

        # Verify audit log entry
        audit_entry = AuditLog.objects.filter(document=self.doc_ops, action='approve').first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.user, self.ops_officer)
        self.assertEqual(audit_entry.details, 'Looks good to proceed.')

    def test_officer_cannot_approve_other_department_document(self):
        self.client.login(username='off_ops', password='password123')
        response = self.client.post(reverse('workflow_approve_document', args=[self.doc_fin.id]), {
            'comment': 'Attempting unauthorized approval',
        })
        self.assertEqual(response.status_code, 404)
        self.doc_fin.refresh_from_db()
        self.assertEqual(self.doc_fin.status, Document.STATUS_PENDING_APPROVAL)

    def test_officer_can_reject_with_required_comment(self):
        self.client.login(username='off_ops', password='password123')
        response = self.client.post(reverse('workflow_reject_document', args=[self.doc_ops.id]), {
            'comment': 'Incomplete signatures on shift handover.',
        })
        self.assertRedirects(response, reverse('workflow_pending_list'))

        self.doc_ops.refresh_from_db()
        self.assertEqual(self.doc_ops.status, Document.STATUS_REJECTED)

        self.approval_ops.refresh_from_db()
        self.assertEqual(self.approval_ops.status, Approval.STATUS_REJECTED)
        self.assertEqual(self.approval_ops.decided_by, self.ops_officer)
        self.assertEqual(self.approval_ops.comment, 'Incomplete signatures on shift handover.')

        # Verify audit log entry
        audit_entry = AuditLog.objects.filter(document=self.doc_ops, action='reject').first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.user, self.ops_officer)
        self.assertEqual(audit_entry.details, 'Incomplete signatures on shift handover.')

    def test_reject_without_comment_fails(self):
        self.client.login(username='off_ops', password='password123')
        response = self.client.post(reverse('workflow_reject_document', args=[self.doc_ops.id]), {
            'comment': '',
        })
        self.assertRedirects(response, reverse('workflow_pending_list'))

        self.doc_ops.refresh_from_db()
        self.assertEqual(self.doc_ops.status, Document.STATUS_PENDING_APPROVAL)
        self.approval_ops.refresh_from_db()
        self.assertEqual(self.approval_ops.status, Approval.STATUS_PENDING)

    def test_dashboard_approvals_card_links_to_pending_list(self):
        from accounts.views import get_dashboard_data
        data = get_dashboard_data(self.ops_officer)
        cards = {c['key']: c for c in data['cards']}
        self.assertEqual(cards['approvals']['link'], reverse('workflow_pending_list'))

        admin_data = get_dashboard_data(self.admin)
        admin_cards = {c['key']: c for c in admin_data['cards']}
        self.assertEqual(admin_cards['approvals']['link'], reverse('workflow_pending_list'))


class WorkflowApprovalRuleTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.safety_dept = Department.objects.create(name='Safety & Security')
        self.fin_dept = Department.objects.create(name='Finance & Accounts')

        self.safety_officer = User.objects.create_user(
            username='safety_off',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.safety_dept,
        )
        self.fin_officer = User.objects.create_user(
            username='fin_off',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.fin_dept,
        )
        self.admin = User.objects.create_superuser(
            username='admin_boss',
            password='password123',
            role=User.ROLE_ADMIN,
            department=self.safety_dept,
        )

        # Safety circular document
        self.safety_doc = Document.objects.create(
            title='Emergency Track Evacuation Protocol',
            document_type=Document.DOC_TYPE_SAFETY_CIRCULAR,
            department=self.safety_dept,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            status=Document.STATUS_PENDING_APPROVAL,
            uploaded_by=self.safety_officer,
        )
        self.safety_approval = Approval.objects.create(
            document=self.safety_doc,
            status=Approval.STATUS_PENDING,
        )

        # Finance invoice document
        self.invoice_doc = Document.objects.create(
            title='Vendor Payment Q3',
            document_type=Document.DOC_TYPE_INVOICE,
            department=self.fin_dept,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            status=Document.STATUS_PENDING_APPROVAL,
            uploaded_by=self.fin_officer,
        )
        self.invoice_approval = Approval.objects.create(
            document=self.invoice_doc,
            status=Approval.STATUS_PENDING,
        )

        # Rule 1: Safety Circulars in Safety Dept require Admin
        self.rule_safety = ApprovalRule.objects.create(
            document_type=Document.DOC_TYPE_SAFETY_CIRCULAR,
            department=self.safety_dept,
            approver_role=ApprovalRule.ROLE_ADMIN,
        )

        # Rule 2: Invoices in Finance Dept require Officer
        self.rule_finance = ApprovalRule.objects.create(
            document_type=Document.DOC_TYPE_INVOICE,
            department=self.fin_dept,
            approver_role=ApprovalRule.ROLE_OFFICER,
        )

    def test_pending_list_hides_doc_when_rule_requires_admin_for_officer(self):
        self.client.login(username='safety_off', password='password123')
        response = self.client.get(reverse('workflow_pending_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['documents']), 0)
        self.assertNotContains(response, 'Emergency Track Evacuation Protocol')

    def test_pending_list_shows_doc_when_rule_requires_officer_for_officer(self):
        self.client.login(username='fin_off', password='password123')
        response = self.client.get(reverse('workflow_pending_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['documents']), 1)
        self.assertEqual(response.context['documents'][0], self.invoice_doc)
        self.assertContains(response, 'Vendor Payment Q3')

    def test_pending_list_shows_all_to_admin_regardless_of_rules(self):
        self.client.login(username='admin_boss', password='password123')
        response = self.client.get(reverse('workflow_pending_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['documents']), 2)

    def test_officer_cannot_approve_when_rule_requires_admin(self):
        self.client.login(username='safety_off', password='password123')
        response = self.client.post(reverse('workflow_approve_document', args=[self.safety_doc.id]), {
            'comment': 'Attempting approval without admin role',
        })
        self.assertEqual(response.status_code, 404)
        self.safety_doc.refresh_from_db()
        self.assertEqual(self.safety_doc.status, Document.STATUS_PENDING_APPROVAL)

    def test_officer_cannot_reject_when_rule_requires_admin(self):
        self.client.login(username='safety_off', password='password123')
        response = self.client.post(reverse('workflow_reject_document', args=[self.safety_doc.id]), {
            'comment': 'Attempting rejection without admin role',
        })
        self.assertEqual(response.status_code, 404)
        self.safety_doc.refresh_from_db()
        self.assertEqual(self.safety_doc.status, Document.STATUS_PENDING_APPROVAL)

    def test_admin_can_approve_when_rule_requires_admin(self):
        self.client.login(username='admin_boss', password='password123')
        response = self.client.post(reverse('workflow_approve_document', args=[self.safety_doc.id]), {
            'comment': 'Admin approved safety circular.',
        })
        self.assertRedirects(response, reverse('workflow_pending_list'))
        self.safety_doc.refresh_from_db()
        self.assertEqual(self.safety_doc.status, Document.STATUS_APPROVED)

    def test_fallback_to_department_visibility_when_no_rule_exists(self):
        # Create a report document in Safety department with NO ApprovalRule
        report_doc = Document.objects.create(
            title='Monthly Safety Incident Summary',
            document_type=Document.DOC_TYPE_REPORT,
            department=self.safety_dept,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            status=Document.STATUS_PENDING_APPROVAL,
            uploaded_by=self.safety_officer,
        )
        Approval.objects.create(
            document=report_doc,
            status=Approval.STATUS_PENDING,
        )

        # Safety officer should see the report document due to fallback
        self.client.login(username='safety_off', password='password123')
        response = self.client.get(reverse('workflow_pending_list'))
        self.assertEqual(response.status_code, 200)
        docs = response.context['documents']
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0], report_doc)

        # Safety officer can approve the fallback document
        post_resp = self.client.post(reverse('workflow_approve_document', args=[report_doc.id]), {
            'comment': 'Fallback approval works',
        })
        self.assertRedirects(post_resp, reverse('workflow_pending_list'))
        report_doc.refresh_from_db()
        self.assertEqual(report_doc.status, Document.STATUS_APPROVED)

