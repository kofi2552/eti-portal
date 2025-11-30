from .models import SystemLog

def log_event(user, category, message, meta=None):
    SystemLog.objects.create(
        user=user,
        category=category,
        message=message,
        meta=meta
    )
