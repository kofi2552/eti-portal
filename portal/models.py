# portal/models.py
# This app can contain shared utilities, dashboards, or other core models.
# Data models like Program, Course, Enrollment, Semester, and Grade
# are now moved to the appropriate apps:
# - academics: Program, Course, Enrollment
# - school: Semester, Grade, Transcript

from django.db import models
from django.conf import settings

# Example: Portal-level settings or utilities could go here
class PortalSettings(models.Model):
    site_name = models.CharField(max_length=100, default="ETI MIS Platform")
    academic_year = models.CharField(max_length=9, default="2025/2026")
    allow_registration = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.site_name} ({self.academic_year})"


class SystemLog(models.Model):
    CATEGORY_CHOICES = [
        ("system", "System"),
        ("auth", "Authentication"),
        ("registration", "Registration"),
        ("assessment", "Assessment"),
        ("resource", "Resource"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="system_logs"
    )

    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="system"
    )

    message = models.TextField()

    meta = models.TextField(
        null=True,
        blank=True,
        help_text="Optional metadata or extra context (JSON/text)."
    )

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.category}] {self.message[:50]}"