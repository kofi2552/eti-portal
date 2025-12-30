from django.apps import AppConfig
from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate
import os


class PortalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'portal'

    def ready(self):
        post_migrate.connect(create_default_superuser, sender=self)


def create_default_superuser(sender, **kwargs):
    User = get_user_model()

    # 🔒 HARD STOP: if any user exists, do nothing
    if User.objects.exists():
        return

    username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
    email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

    if not all([username, email, password]):
        return

    User.objects.create_superuser(
        username=username,
        email=email,
        password=password
    )
