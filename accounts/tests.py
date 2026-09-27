from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Department, User
from .permissions import (
    CONFIDENTIALITY_INTERNAL,
    CONFIDENTIALITY_PUBLIC,
    CONFIDENTIALITY_RESTRICTED,
    can_view,
)


class AccountsModelsTest(TestCase):
    def setUp(self):
        self.operations_dept = Department.objects.create(name='Operations')
        self.hr_dept = Department.objects.create(name='Human Resources')

    def test_department_creation_and_str(self):
        self.assertEqual(str(self.operations_dept), 'Operations')

    def test_custom_user_creation_with_defaults(self):
        UserModel = get_user_model()
        user = UserModel.objects.create_user(
            username='emp001',
            password='password123',
            email='emp001@example.com',
        )
        self.assertEqual(user.role, User.ROLE_EMPLOYEE)
        self.assertIsNone(user.department)
        self.assertEqual(str(user), 'emp001 (Employee)')

    def test_custom_user_with_role_and_department(self):
        UserModel = get_user_model()
        officer = UserModel.objects.create_user(
            username='officer01',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.operations_dept,
        )
        self.assertEqual(officer.role, User.ROLE_OFFICER)
        self.assertEqual(officer.department, self.operations_dept)
        self.assertIn(officer, self.operations_dept.users.all())

    def test_superuser_creation(self):
        UserModel = get_user_model()
        superuser = UserModel.objects.create_superuser(
            username='superadmin',
            email='superadmin@example.com',
            password='adminpassword',
            role=User.ROLE_ADMIN,
            department=self.hr_dept,
        )
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.is_staff)
        self.assertEqual(superuser.role, User.ROLE_ADMIN)
        self.assertEqual(superuser.department, self.hr_dept)

    def test_admin_registration(self):
        self.assertIn(Department, admin.site._registry)
        self.assertIn(User, admin.site._registry)


class PermissionsTest(TestCase):
    def setUp(self):
        self.ops_dept = Department.objects.create(name='Operations')
        self.fin_dept = Department.objects.create(name='Finance')

        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='password123',
            role=User.ROLE_ADMIN,
            department=self.ops_dept,
        )
        self.ops_officer = User.objects.create_user(
            username='ops_off',
            password='password123',
            role=User.ROLE_OFFICER,
            department=self.ops_dept,
        )
        self.ops_employee = User.objects.create_user(
            username='ops_emp',
            password='password123',
            role=User.ROLE_EMPLOYEE,
            department=self.ops_dept,
        )

    def test_admin_can_view_all(self):
        for dept in [self.ops_dept, self.fin_dept]:
            for level in [CONFIDENTIALITY_PUBLIC, CONFIDENTIALITY_INTERNAL, CONFIDENTIALITY_RESTRICTED]:
                self.assertTrue(can_view(self.admin_user, dept, level))

    def test_officer_permissions(self):
        # Public & Internal from any department -> True
        self.assertTrue(can_view(self.ops_officer, self.ops_dept, CONFIDENTIALITY_PUBLIC))
        self.assertTrue(can_view(self.ops_officer, self.fin_dept, CONFIDENTIALITY_PUBLIC))
        self.assertTrue(can_view(self.ops_officer, self.ops_dept, CONFIDENTIALITY_INTERNAL))
        self.assertTrue(can_view(self.ops_officer, self.fin_dept, CONFIDENTIALITY_INTERNAL))

        # Restricted only from own department
        self.assertTrue(can_view(self.ops_officer, self.ops_dept, CONFIDENTIALITY_RESTRICTED))
        self.assertFalse(can_view(self.ops_officer, self.fin_dept, CONFIDENTIALITY_RESTRICTED))

    def test_employee_permissions(self):
        # Public & Internal only from own department
        self.assertTrue(can_view(self.ops_employee, self.ops_dept, CONFIDENTIALITY_PUBLIC))
        self.assertTrue(can_view(self.ops_employee, self.ops_dept, CONFIDENTIALITY_INTERNAL))
        self.assertFalse(can_view(self.ops_employee, self.fin_dept, CONFIDENTIALITY_PUBLIC))
        self.assertFalse(can_view(self.ops_employee, self.fin_dept, CONFIDENTIALITY_INTERNAL))

        # Restricted -> False for employee everywhere
        self.assertFalse(can_view(self.ops_employee, self.ops_dept, CONFIDENTIALITY_RESTRICTED))
        self.assertFalse(can_view(self.ops_employee, self.fin_dept, CONFIDENTIALITY_RESTRICTED))

    def test_unauthenticated_user_cannot_view(self):
        self.assertFalse(can_view(None, self.ops_dept, CONFIDENTIALITY_PUBLIC))


class AuthViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name='Operations & Station Management')
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword123',
            role=User.ROLE_EMPLOYEE,
            department=self.dept,
            first_name='Test',
            last_name='User',
        )

    def test_unauthenticated_redirect(self):
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_login_page_renders(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')

    def test_successful_login_and_landing_page(self):
        login_response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpassword123',
        })
        self.assertRedirects(login_response, reverse('landing'))

        landing_response = self.client.get(reverse('landing'))
        self.assertEqual(landing_response.status_code, 200)
        self.assertTemplateUsed(landing_response, 'accounts/landing.html')
        self.assertContains(landing_response, 'testuser')
        self.assertContains(landing_response, 'Operations &amp; Station Management')
        self.assertContains(landing_response, 'Employee')

    def test_logout_action(self):
        self.client.login(username='testuser', password='testpassword123')
        logout_response = self.client.post(reverse('logout'))
        self.assertRedirects(logout_response, reverse('login'))
