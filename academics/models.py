from django.db import models
from django.conf import settings  

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

    def __str__(self):
        return self.name


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
    semester = models.ForeignKey(
        'Semester',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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


class Assessment(models.Model):
    course = models.ForeignKey(
        'Course',
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
        max_length=9,
        unique=True,
        help_text="Format: 2024/2025"
    )
    is_active = models.BooleanField(default=False)

    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Semester(models.Model):
    name = models.CharField(max_length=100)

    academic_year = models.ForeignKey(
        'AcademicYear',
        on_delete=models.CASCADE,
        related_name='semesters'
    )

    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=False)
    sem_reg_is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.academic_year.name}"


class Enrollment(models.Model):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'}
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    semester = models.ForeignKey("school.Semester", on_delete=models.CASCADE)
    date_enrolled = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course', 'semester')

    def __str__(self):
        return f"{self.student} enrolled in {self.course} ({self.semester})"


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
        "Course",
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