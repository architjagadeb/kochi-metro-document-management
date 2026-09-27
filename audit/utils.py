import json
from .models import AuditLog


def log_action(user=None, action='', document=None, details=None, comment=None, **kwargs):
    """
    Helper function to log an action to the audit app.
    Accepts user, action name, document, details (or comment), and optional kwargs.
    """
    if details is None and comment is not None:
        details = comment
    elif details is None:
        details = ''

    if isinstance(details, dict):
        details_str = json.dumps(details)
    else:
        details_str = str(details) if details else ''

    log_entry = AuditLog.objects.create(
        user=user if (user and user.is_authenticated) else None,
        action=action,
        document=document,
        details=details_str,
    )
    return log_entry
