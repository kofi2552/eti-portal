from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings  
from academics.models import Department, Program, AcademicYear, Semester, ProgramCourse, ProgramLevel

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('lecturer', 'Lecturer'),
        ('dean', 'Dean/HOD'),
        ('admin', 'Admin'),
        ('superadmin', 'Super Admin'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    level = models.ForeignKey(
        ProgramLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students_in_level"
    )
    student_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    pin_code = models.CharField(max_length=10, null=True, blank=True)

    # STUDENT-RELATED FIELDS
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students"
    )

    program = models.ForeignKey(
        Program,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students"
    )

    is_fee_paid = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.username} ({self.role})"


class Payment(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
        limit_choices_to={'role': 'student'}
    )

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)

    amount_expected = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    reference = models.CharField(max_length=100, unique=True)
    date_paid = models.DateTimeField(null=True, blank=True)

    generated_student_id = models.CharField(max_length=20, null=True, blank=True)
    generated_pin = models.CharField(max_length=10, null=True, blank=True)

    is_verified = models.BooleanField(default=False)  # admin must verify

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "academic_year", "semester")

    def __str__(self):
        return f"{self.student} - {self.semester} - {self.amount_paid}"


class RegistrationProgress(models.Model):
    student = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="registration_progress"
    )

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    semester = models.ForeignKey(
        Semester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    program = models.ForeignKey(
        Program,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Progress flags
    step1_completed = models.BooleanField(default=False)  # Fee confirmation
    step2_completed = models.BooleanField(default=False)  # Program selection
    step3_completed = models.BooleanField(default=False)  # Course selection
    step4_completed = models.BooleanField(default=False)  # Review & confirm

    is_submitted = models.BooleanField(default=False)  # Final submission done

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student.get_full_name()} - Registration Progress"
    
class StudentRegistration(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="registrations"
    )

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    level = models.ForeignKey(
        ProgramLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registration_level"
    )
    courses = models.ManyToManyField(
    ProgramCourse,
    related_name="registered_students"
    )

    submitted_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=20,
        default="submitted",  # other values: approved, rejected
        choices=[
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ]
    )

    class Meta:
        unique_together = ("student", "academic_year", "semester")

    def __str__(self):
        return f"{self.student.get_full_name()} - {self.academic_year} - {self.semester}"


























