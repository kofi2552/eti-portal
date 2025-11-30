from django.db import models

class Semester(models.Model):
    name = models.CharField(max_length=20)  # e.g., "First Semester"
    academic_year = models.CharField(max_length=9)  # e.g., "2025/2026"

    def __str__(self):
        return f"{self.name} ({self.academic_year})"


class Grade(models.Model):
    enrollment = models.OneToOneField(
        "academics.Enrollment",
        on_delete=models.CASCADE  # string reference
    )
    letter_grade = models.CharField(max_length=2)  # e.g., "A", "B+"
    grade_point = models.FloatField()

    def __str__(self):
        return f"{self.enrollment.course} - {self.letter_grade}"


class Transcript(models.Model):
    student = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'}
    )
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transcript of {self.student} - {self.semester}"