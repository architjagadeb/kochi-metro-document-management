from .models import User

CONFIDENTIALITY_PUBLIC = 'public'
CONFIDENTIALITY_INTERNAL = 'internal'
CONFIDENTIALITY_RESTRICTED = 'restricted'

CONFIDENTIALITY_CHOICES = [
    (CONFIDENTIALITY_PUBLIC, 'Public'),
    (CONFIDENTIALITY_INTERNAL, 'Internal'),
    (CONFIDENTIALITY_RESTRICTED, 'Restricted'),
]


def can_view(user, department, confidentiality):
    """
    Determine if a user can view a resource based on confidentiality level and department.

    Rules:
    - Admin can view everything.
    - Officer can view public and internal from any department,
      and restricted only from their own department.
    - Employee can view public and internal only from their own department.
    """
    if not user or not user.is_authenticated:
        return False

    if user.role == User.ROLE_ADMIN or user.is_superuser:
        return True

    is_own_department = (user.department is not None) and (user.department == department)

    if user.role == User.ROLE_OFFICER:
        if confidentiality in (CONFIDENTIALITY_PUBLIC, CONFIDENTIALITY_INTERNAL):
            return True
        if confidentiality == CONFIDENTIALITY_RESTRICTED:
            return is_own_department
        return False

    if user.role == User.ROLE_EMPLOYEE:
        if confidentiality in (CONFIDENTIALITY_PUBLIC, CONFIDENTIALITY_INTERNAL):
            return is_own_department
        if confidentiality == CONFIDENTIALITY_RESTRICTED:
            return False
        return False

    return False
