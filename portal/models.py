# portal/models.py
# This app can contain shared utilities, dashboards, or other core models.
# Data models like Program, Course, Enrollment, Semester, and Grade
# are now moved to the appropriate apps:
# - academics: Program, Course, Enrollment
# - school: Semester, Grade, Transcript

from django.db import models
from django.conf import settings
from django.utils import timezone


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
    

class SystemLock(models.Model):
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL
    )

    def lock(self, user):
        self.is_locked = True
        self.locked_at = timezone.now()
        self.locked_by = user
        self.save()

    def unlock(self):
        self.is_locked = False
        self.locked_at = None
        self.locked_by = None
        self.save()

    def __str__(self):
        return "System is LOCKED" if self.is_locked else "System is UNLOCKED"
    

class Announcement(models.Model):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("lecturer", "Lecturer"),
        ("dean", "Dean"),
    ]

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} ({self.role})"


class ErrorLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    path = models.CharField(max_length=500, help_text="Browser URL")
    method = models.CharField(max_length=10, help_text="GET/POST")
    error_message = models.TextField()
    stack_trace = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.path} - {self.error_message[:50]}"


class SupportTicket(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ]

    CATEGORY_CHOICES = [
        ('bug', 'Bug Report'),
        ('academic', 'Academic Query'),
        ('finance', 'Financial Query'),
        ('other', 'Other')
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('fixed', 'Fixed'),
        ('closed', 'Closed')
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='support_tickets'
    )
    subject = models.CharField(max_length=255)
    message = models.TextField()
    
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='bug')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.subject} - {self.student.get_full_name()}"
