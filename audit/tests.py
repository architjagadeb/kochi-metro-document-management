from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Department, User
from accounts.permissions import CONFIDENTIALITY_INTERNAL
from audit.models import AuditLog
from audit.utils import log_action
from documents.models import Document


class AuditListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name='Operations')

        self.admin_user = User.objects.create_user(
            username='admin_audit',
            password='password123',
            role=User.ROLE_ADMIN,
            department=self.dept,
        )
        self.officer_user = User.objects.create_user(
            username='officer_audit',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.dept,
        )
        self.employee_user = User.objects.create_user(
            username='employee_audit',
            password='password123',
            role=User.ROLE_EMPLOYEE,
            department=self.dept,
        )

        self.doc = Document.objects.create(
            title='Track Safety Handbook',
            document_type=Document.DOC_TYPE_SAFETY_CIRCULAR,
            department=self.dept,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            uploaded_by=self.employee_user,
        )

        # Create sample audit log entries
        self.log1 = log_action(
            user=self.employee_user,
            action='ai_query',
            document=self.doc,
            details='What is the track speed limit?',
        )
        self.log2 = log_action(
            user=self.officer_user,
            action='approve',
            document=self.doc,
            details='Approved for release.',
        )
        self.log3 = log_action(
            user=self.admin_user,
            action='archive',
            document=self.doc,
            details='Archived old manual.',
        )

    def test_unauthenticated_user_redirected(self):
        url = reverse('audit_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_non_admin_users_get_404(self):
        url = reverse('audit_list')

        # Employee
        self.client.login(username='employee_audit', password='password123')
        res_emp = self.client.get(url)
        self.assertEqual(res_emp.status_code, 404)

        # Officer
        self.client.login(username='officer_audit', password='password123')
        res_off = self.client.get(url)
        self.assertEqual(res_off.status_code, 404)

    def test_admin_can_access_audit_list(self):
        self.client.login(username='admin_audit', password='password123')
        url = reverse('audit_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'audit/audit_list.html')
        self.assertContains(response, 'System Audit Log')
        self.assertContains(response, 'Track Safety Handbook')
        self.assertContains(response, 'ai_query')
        self.assertContains(response, 'approve')
        self.assertContains(response, 'archive')
        self.assertContains(response, 'What is the track speed limit?')
        self.assertContains(response, reverse('document_detail', args=[self.doc.id]))

    def test_audit_list_filtering_by_action_and_user(self):
        self.client.login(username='admin_audit', password='password123')
        url = reverse('audit_list')

        # Filter by action
        res_action = self.client.get(url, {'action': 'ai_query'})
        self.assertEqual(res_action.status_code, 200)
        self.assertContains(res_action, 'What is the track speed limit?')
        self.assertNotContains(res_action, 'Approved for release.')

        # Filter by user
        res_user = self.client.get(url, {'user': str(self.officer_user.id)})
        self.assertEqual(res_user.status_code, 200)
        self.assertContains(res_user, 'Approved for release.')
        self.assertNotContains(res_user, 'What is the track speed limit?')

    def test_dashboard_audit_link_visibility(self):
        # Admin should see Audit Log link on dashboard
        self.client.login(username='admin_audit', password='password123')
        landing_admin = self.client.get(reverse('landing'))
        self.assertContains(landing_admin, reverse('audit_list'))

        # Employee should NOT see Audit Log link on dashboard
        self.client.login(username='employee_audit', password='password123')
        landing_emp = self.client.get(reverse('landing'))
        self.assertNotContains(landing_emp, reverse('audit_list'))
