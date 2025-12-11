from django.db import models
from django.conf import settings  
from django.db.models.signals import post_save
from django.dispatch import receiver
import random
import re


User = settings.AUTH_USER_MODEL

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, null=True)
    dean = models.ForeignKey(
        settings.AUTH_USER_MODEL,   
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'dean'},
        related_name='programs_managed'
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='departments_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name


class Program(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, null=True)

    department = models.ForeignKey(
        'Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='programs'
    )

    created_at = models.DateTimeField(auto_now_add=True)

   
    AWARD_CHOICES = [
        ("certificate", "Certificate"),
        ("diploma", "Diploma"),
        ("hnd", "Higher National Diploma"),
        ("bachelor", "Bachelor Degree"),
        ("master", "Masters"),
        ("phd", "PhD"),
    ]

    award_type = models.CharField(max_length=20, choices=AWARD_CHOICES, default="bachelor")
    duration_years = models.PositiveIntegerField(default=1)
    semesters_per_level = models.PositiveIntegerField(default=2)

    def __str__(self):
        return f"{self.name} ({self.get_award_type_display()})"

# Award → Fixed level number (except bachelor)
FIXED_LEVELS = {
    "certificate": 200,
    "diploma": 500,
    "hnd": 300,
    "master": 600,
    "phd": 800,
}

# Bachelor's dynamic levels
BACHELOR_LEVELS = [100, 200, 300, 400]

@receiver(post_save, sender=Program)
def create_program_levels(sender, instance, created, **kwargs):
    if not created:
        return

    award = instance.award_type
    duration = instance.duration_years

    # --------------------------------------------
    # CASE 1: Bachelor's — levels change numerically
    # --------------------------------------------
    if award == "bachelor":
        # Ensure we only create levels equal to program duration
        for index in range(duration):
            level_num = BACHELOR_LEVELS[index]  # 0→100, 1→200, etc.
            ProgramLevel.objects.create(
                program=instance,
                level_name=f"Level {level_num}",
                order=index + 1
            )
        return

    # --------------------------------------------
    # CASE 2: All other awards — fixed level number
    # --------------------------------------------
    fixed_level_num = FIXED_LEVELS.get(award)

    if not fixed_level_num:
        raise ValueError(f"No fixed level defined for award type '{award}'")

    # Create one level per year, all having same level_name
    for index in range(duration):
        ProgramLevel.objects.create(
            program=instance,
            level_name=f"Level {fixed_level_num}",
            order=index + 1
        )

class Assessment(models.Model):
    course = models.ForeignKey(
        'ProgramCourse',
        on_delete=models.CASCADE,
        related_name='assessments'
    )
    program = models.ForeignKey(
        'Program',
        on_delete=models.CASCADE,
        related_name='assessments'
    )
    semester = models.ForeignKey(
        'Semester',
        on_delete=models.CASCADE,
        related_name='assessments'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='assessments'
    )

    # Numeric score (e.g. 85.5)
    score = models.DecimalField(
        max_digits=5,  # allows up to 999.99
        decimal_places=2
    )

    # Letter grade (e.g. A, B+, C)
    grade = models.CharField(
        max_length=2,
        help_text="Final grade obtained for the course (e.g., A, B+, C)"
    )

    date_recorded = models.DateTimeField(auto_now_add=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role__in': ['lecturer', 'admin']},
        related_name='assessments_recorded'
    )

    def __str__(self):
        return f"{self.student} - {self.course.code} ({self.grade})"


class AcademicYear(models.Model):
    name = models.CharField(
        max_length=16,
        unique=True,
        help_text="Format: 2024/2025"
    )
    is_active = models.BooleanField(default=False)
    is_ready = models.BooleanField(default=False)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class ProgramLevel(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="levels")
    level_name = models.CharField(max_length=50)  # e.g. "Level 100", "Level 200"
    order = models.PositiveIntegerField(default=1)  # For sorting

    def __str__(self):
        return f"{self.program.name} - {self.level_name}"


class Semester(models.Model):
    name = models.CharField(max_length=100)

    academic_year = models.ForeignKey(
        'AcademicYear',
        on_delete=models.CASCADE,
        related_name='semesters'
    )

    level = models.ForeignKey(ProgramLevel, on_delete=models.SET_NULL, null=True, blank=True)

    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=False)
    sem_reg_is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.academic_year.name}"


class Course(models.Model):
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name='courses'
    )
    department = models.ForeignKey(
        'Department',
        on_delete=models.CASCADE,
        related_name='courses'
    )

    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    credit_hours = models.IntegerField(default=3)
    description = models.TextField(blank=True, null=True)

    assigned_lecturers = models.ManyToManyField(
        User,
        blank=True,
        limit_choices_to={'role': 'lecturer'},
        related_name='courses_taught'
    )

    def __str__(self):
        return f"{self.code} - {self.title}"


class Enrollment(models.Model):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'}
    )
    date_enrolled = models.DateTimeField(auto_now_add=True)

    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name='program_semesters'
    )

    level = models.ForeignKey(ProgramLevel, on_delete=models.SET_NULL, null=True, blank=True)

    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    payment = models.ForeignKey("users.Payment", on_delete=models.CASCADE, related_name='enrollment_payment')
    is_current = models.BooleanField(default=False)

    class Meta:
        unique_together = ('student',  'semester')

    def __str__(self):
        return f"{self.student} enrolled in ({self.semester}) semester"


class Grade(models.Model):
    letter = models.CharField(max_length=3, unique=True)
    min_score = models.DecimalField(max_digits=5, decimal_places=2)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ["-min_score"]

    def __str__(self):
        return f"{self.letter} ({self.min_score}-{self.max_score})"


class Resource(models.Model):
    course = models.ForeignKey(
        "ProgramCourse",
        on_delete=models.CASCADE,
        related_name="resources"
    )

    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"role": "lecturer"},
        related_name="uploaded_resources"
    )

    semester = models.ForeignKey(
        "Semester",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resources"
    )

    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True, null=True)

    # External URL: Google Drive, OneDrive, YouTube, Wikipedia, etc.
    external_link = models.URLField(blank=True, null=True)

    # OPTIONAL uploaded file (PDF, PPTX, DOCX etc.)
    file = models.FileField(
        upload_to="course_resources/",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.course.code})"
    

class TranscriptSettings(models.Model):
    allow_requests = models.BooleanField(default=True)

    def __str__(self):
        return "Transcript Settings"


class TranscriptRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending Approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("revoked", "Access Revoked")
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name="transcript_requests"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    transcript_json = models.JSONField(null=True, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)  # When transcript was generated
    approved_at = models.DateTimeField(null=True, blank=True)   # When admin approved
    admin_notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transcript Request — {self.student.get_full_name()}"


class ProgramCourse(models.Model):
    base_course = models.ForeignKey(
        'Course',
        on_delete=models.CASCADE,
        related_name="program_variants"
    )

    program = models.ForeignKey(
        'Program',
        on_delete=models.CASCADE,
        related_name="program_courses"
    )

    level = models.ForeignKey(
        'ProgramLevel',
        on_delete=models.CASCADE,
        related_name="level_courses"
    )

    semester = models.ForeignKey(
        'Semester',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="program_courses"
    )

    assigned_lecturers = models.ManyToManyField(
        User,
        blank=True,
        limit_choices_to={'role': 'lecturer'},
        related_name='program_courses_taught'
    )

    # Program-specific code (auto-generated; editable)
    course_code = models.CharField(max_length=20, unique=True)

    # Title editable in case program needs a variant title
    title = models.CharField(max_length=200)

    credit_hours = models.PositiveIntegerField(default=3)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('program', 'level', 'title')
        ordering = ['program__name', 'level__order', 'title']

    def __str__(self):
        return f"{self.title} ({self.course_code})"

    @staticmethod
    def generate_code_for(title, level):
        """
        Generates a code based on title initials + numeric segment derived from level.
        Example: title 'Finance Ways' + level 100 -> FW1xx (we will produce FW105)
        """
        # get initials (2 letters)
        initials = "".join([w[0] for w in re.findall(r"[A-Za-z0-9]+", title)][:2]).upper()
        if not initials:
            initials = "XX"

        # derive numeric base from level.level_name if possible
        # e.g. "Level 100" => base 100, range 100-199
        base = None
        if level and getattr(level, "level_name", None):
            m = re.search(r"(\d{2,3})", level.level_name)
            if m:
                try:
                    base = int(m.group(1))
                except Exception:
                    base = None

        # fallback: use level.order * 100 (1 -> 100, 2 -> 200)
        if base is None:
            base = (level.order if getattr(level, "order", None) else 1) * 100

        # pick random number in [base, base+99]
        for _ in range(10):
            num = random.randint(base, base + 99)
            code = f"{initials}{num}"
            # caller should check uniqueness; we return candidate
            return code

        # final fallback
        return f"{initials}{base}"
