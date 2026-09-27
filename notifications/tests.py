from unittest.mock import patch
from django.contrib.admin.sites import site
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Department, User
from accounts.permissions import CONFIDENTIALITY_INTERNAL
from documents.models import Document, DocumentVersion
from notifications.admin import NotificationAdmin
from notifications.models import Notification
from notifications.utils import notify
from workflow.models import Approval


class NotificationModelAndHelperTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Operations')
        self.user = User.objects.create_user(
            username='notify_user',
            password='password123',
            role=User.ROLE_EMPLOYEE,
            department=self.dept,
        )

    def test_notification_creation_and_defaults(self):
        notification = Notification.objects.create(
            recipient=self.user,
            message='Test message content',
        )
        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.message, 'Test message content')
        self.assertEqual(notification.link, '')
        self.assertFalse(notification.is_read)
        self.assertIsNotNone(notification.created_date)
        self.assertIn('Notification for notify_user', str(notification))

    def test_notify_helper_success(self):
        notif = notify(
            user=self.user,
            message='You have a new update.',
            link='/documents/1/',
        )
        self.assertIsNotNone(notif)
        self.assertEqual(notif.recipient, self.user)
        self.assertEqual(notif.message, 'You have a new update.')
        self.assertEqual(notif.link, '/documents/1/')
        self.assertFalse(notif.is_read)

    def test_notify_helper_handles_none_user(self):
        result = notify(user=None, message='Anonymous update')
        self.assertIsNone(result)
        self.assertEqual(Notification.objects.count(), 0)

    @patch('notifications.models.Notification.objects.create')
    def test_notify_helper_never_raises_on_exception(self, mock_create):
        mock_create.side_effect = Exception('Database connection failed')
        # Should not raise exception
        result = notify(user=self.user, message='Should fail gracefully')
        self.assertIsNone(result)

    def test_admin_is_read_only(self):
        admin_obj = NotificationAdmin(Notification, site)
        self.assertFalse(admin_obj.has_add_permission(None))
        self.assertFalse(admin_obj.has_change_permission(None))
        self.assertFalse(admin_obj.has_delete_permission(None))


class NotificationWorkflowIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept_ops = Department.objects.create(name='Operations')
        self.dept_finance = Department.objects.create(name='Finance')

        self.employee_ops = User.objects.create_user(
            username='emp_ops',
            password='password123',
            role=User.ROLE_EMPLOYEE,
            department=self.dept_ops,
        )
        self.officer_ops = User.objects.create_user(
            username='officer_ops',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.dept_ops,
        )
        self.officer_finance = User.objects.create_user(
            username='officer_fin',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.dept_finance,
        )
        self.admin_user = User.objects.create_user(
            username='super_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )

    def test_notify_on_document_approved(self):
        doc = Document.objects.create(
            title='Track Maintenance Schedule',
            document_type=Document.DOC_TYPE_REPORT,
            department=self.dept_ops,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            status=Document.STATUS_PENDING_APPROVAL,
            uploaded_by=self.employee_ops,
        )
        Approval.objects.create(document=doc, status=Approval.STATUS_PENDING)

        self.client.login(username='officer_ops', password='password123')
        url = reverse('workflow_approve_document', args=[doc.id])
        response = self.client.post(url, {'comment': 'Approved by Ops Head'})
        self.assertEqual(response.status_code, 302)

        notif = Notification.objects.filter(recipient=self.employee_ops).first()
        self.assertIsNotNone(notif)
        self.assertIn('Track Maintenance Schedule', notif.message)
        self.assertIn('approved', notif.message.lower())

    def test_notify_on_document_rejected_with_comment(self):
        doc = Document.objects.create(
            title='Faulty Shift Schedule',
            document_type=Document.DOC_TYPE_REPORT,
            department=self.dept_ops,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            status=Document.STATUS_PENDING_APPROVAL,
            uploaded_by=self.employee_ops,
        )
        Approval.objects.create(document=doc, status=Approval.STATUS_PENDING)

        self.client.login(username='officer_ops', password='password123')
        url = reverse('workflow_reject_document', args=[doc.id])
        rejection_reason = 'Shift timings violate rest period regulations.'
        response = self.client.post(url, {'comment': rejection_reason})
        self.assertEqual(response.status_code, 302)

        notif = Notification.objects.filter(recipient=self.employee_ops).first()
        self.assertIsNotNone(notif)
        self.assertIn('Faulty Shift Schedule', notif.message)
        self.assertIn('rejected', notif.message.lower())
        self.assertIn(rejection_reason, notif.message)

    def test_notify_on_document_resubmitted(self):
        doc = Document.objects.create(
            title='Revised Shift Schedule',
            document_type=Document.DOC_TYPE_REPORT,
            department=self.dept_ops,
            confidentiality=CONFIDENTIALITY_INTERNAL,
            status=Document.STATUS_REJECTED,
            uploaded_by=self.employee_ops,
        )

        self.client.login(username='emp_ops', password='password123')
        url = reverse('document_resubmit', args=[doc.id])
        response = self.client.post(url, {
            'title': 'Revised Shift Schedule V2',
            'document_type': Document.DOC_TYPE_REPORT,
            'confidentiality': CONFIDENTIALITY_INTERNAL,
            'note': 'Corrected rest periods as per regulations.',
        })
        self.assertEqual(response.status_code, 302)

        # Relevant officers in Ops and Admins should receive notifications
        ops_officer_notif = Notification.objects.filter(recipient=self.officer_ops).first()
        admin_notif = Notification.objects.filter(recipient=self.admin_user).first()
        finance_officer_notif = Notification.objects.filter(recipient=self.officer_finance).first()

        self.assertIsNotNone(ops_officer_notif)
        self.assertIn('Revised Shift Schedule V2', ops_officer_notif.message)
        self.assertIn('resubmitted', ops_officer_notif.message.lower())

        self.assertIsNotNone(admin_notif)
        self.assertIn('resubmitted', admin_notif.message.lower())

        # Officer in another department should NOT receive notification
        self.assertIsNone(finance_officer_notif)

    def test_notify_on_initial_document_upload(self):
        self.client.login(username='emp_ops', password='password123')
        url = reverse('document_upload')
        fake_file = SimpleUploadedFile('sop.pdf', b'%PDF-1.4 sample content', content_type='application/pdf')

        response = self.client.post(url, {
            'title': 'New Standard Operating Procedure',
            'file': fake_file,
            'document_type': Document.DOC_TYPE_REPORT,
            'department': self.dept_ops.id,
            'confidentiality': CONFIDENTIALITY_INTERNAL,
        })
        self.assertEqual(response.status_code, 302)

        # Relevant officers in Ops and Admins should receive notifications
        ops_officer_notif = Notification.objects.filter(recipient=self.officer_ops).first()
        admin_notif = Notification.objects.filter(recipient=self.admin_user).first()
        finance_officer_notif = Notification.objects.filter(recipient=self.officer_finance).first()

        self.assertIsNotNone(ops_officer_notif)
        self.assertIn('New Standard Operating Procedure', ops_officer_notif.message)
        self.assertIn('pending approval', ops_officer_notif.message.lower())

        self.assertIsNotNone(admin_notif)
        self.assertIn('pending approval', admin_notif.message.lower())

        # Officer in another department should NOT receive notification
        self.assertIsNone(finance_officer_notif)


class NotificationDashboardAndActionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name='Operations')
        self.user1 = User.objects.create_user(
            username='user1',
            password='password123',
            role=User.ROLE_EMPLOYEE,
            department=self.dept,
        )
        self.user2 = User.objects.create_user(
            username='user2',
            password='password123',
            role=User.ROLE_EMPLOYEE,
            department=self.dept,
        )

    def test_dashboard_data_notifications_order_and_unread_count(self):
        from accounts.views import get_dashboard_data

        # Create 7 notifications for user1 (some read, some unread)
        for i in range(7):
            Notification.objects.create(
                recipient=self.user1,
                message=f'Notification {i}',
                link=f'/documents/{i}/',
                is_read=(i < 2),  # 0 and 1 are read, 2..6 (5 notifications) are unread
            )

        # Create 1 notification for user2
        Notification.objects.create(
            recipient=self.user2,
            message='User2 secret notification',
            is_read=False,
        )

        data = get_dashboard_data(self.user1)

        # Check 5 most recent notifications returned
        self.assertEqual(len(data['notifications']), 5)
        # Newest first: Notification 6 should be first
        self.assertEqual(data['notifications'][0].message, 'Notification 6')
        self.assertEqual(data['notifications'][4].message, 'Notification 2')

        # Check unread count card value
        self.assertEqual(data['unread_notifications_count'], 5)
        notif_card = next(c for c in data['cards'] if c['key'] == 'notifications')
        self.assertEqual(notif_card['value'], 5)

    def test_mark_all_notifications_read_post(self):
        for i in range(3):
            Notification.objects.create(
                recipient=self.user1,
                message=f'Notif {i}',
                is_read=False,
            )

        self.client.login(username='user1', password='password123')
        url = reverse('notifications_mark_all_read')

        # Standard POST redirect
        response = self.client.post(url)
        self.assertRedirects(response, reverse('landing'))

        self.assertEqual(Notification.objects.filter(recipient=self.user1, is_read=False).count(), 0)

    def test_mark_all_notifications_read_ajax(self):
        for i in range(3):
            Notification.objects.create(
                recipient=self.user1,
                message=f'Notif {i}',
                is_read=False,
            )

        self.client.login(username='user1', password='password123')
        url = reverse('notifications_mark_all_read')

        # AJAX POST
        response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('unread_count'), 0)
        self.assertEqual(Notification.objects.filter(recipient=self.user1, is_read=False).count(), 0)

    def test_mark_single_notification_read_ajax(self):
        n1 = Notification.objects.create(recipient=self.user1, message='N1', is_read=False)
        n2 = Notification.objects.create(recipient=self.user1, message='N2', is_read=False)

        self.client.login(username='user1', password='password123')
        url = reverse('notifications_mark_read', args=[n1.id])

        response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('unread_count'), 1)

        n1.refresh_from_db()
        n2.refresh_from_db()
        self.assertTrue(n1.is_read)
        self.assertFalse(n2.is_read)

    def test_mark_notification_read_permission_isolation(self):
        n_user2 = Notification.objects.create(recipient=self.user2, message='User2 Notif', is_read=False)

        # user1 cannot mark user2's notification
        self.client.login(username='user1', password='password123')
        url = reverse('notifications_mark_read', args=[n_user2.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

        n_user2.refresh_from_db()
        self.assertFalse(n_user2.is_read)

