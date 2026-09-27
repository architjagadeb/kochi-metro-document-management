def notify(user, message, link=None):
    """
    Helper function to create a Notification.
    Never raises an exception that could break the calling view,
    logging any internal failure to the console instead.
    """
    if not user:
        return None
    try:
        from .models import Notification
        notification = Notification.objects.create(
            recipient=user,
            message=message,
            link=link or '',
        )
        return notification
    except Exception as e:
        print(f"[Notification Error] Failed to create notification for {user}: {e}")
        return None
