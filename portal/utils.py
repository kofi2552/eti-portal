from .models import SystemLog
from users.models import StudentRegistration
from academics.models import Assessment
from django.db.models import Prefetch
from decimal import Decimal

def log_event(user, category, message, meta=None):
    SystemLog.objects.create(
        user=user,
        category=category,
        message=message,
        meta=meta
    )


def generate_transcript_json(student):
    """
    Returns a full transcript dictionary:
    """

    # Load all registrations for this student (old + new)
    registrations = (
        StudentRegistration.objects.filter(student=student)
        .select_related("semester", "semester__academic_year", "semester__level")
        .order_by("semester__start_date")
    )

    grade_points = {
        "A": 4.0, "B+": 3.5, "B": 3.0,
        "C+": 2.5, "C": 2.0, "D+": 1.5,
        "D": 1.0, "F": 0.0,
    }

    transcript_semesters = []
    total_points = Decimal("0")
    total_credits = Decimal("0")

    for reg in registrations:
        sem_data = {
            "semester": reg.semester.name,
            "academic_year": reg.semester.academic_year.name,
            "level": reg.semester.level.level_name if reg.semester.level else None,
            "courses": [],
            "gpa": None,
        }

        assessments = (
            Assessment.objects.filter(
                student=student,
                semester=reg.semester,
                course__in=reg.courses.all()
            ).select_related("course")
        )

        sem_points = Decimal("0")
        sem_credits = Decimal("0")

        for a in assessments:
            credits = Decimal(a.course.credit_hours or 0)
            point = Decimal(grade_points.get(a.grade, 0)) * credits

            sem_points += point
            sem_credits += credits

            sem_data["courses"].append({
                "code": a.course.course_code,
                "title": a.course.title,
                "score": float(a.score),
                "grade": a.grade,
                "credits": int(credits),
            })

        sem_data["gpa"] = float(sem_points / sem_credits) if sem_credits > 0 else None

        # accumulate for CGPA
        total_points += sem_points
        total_credits += sem_credits

        transcript_semesters.append(sem_data)

    cgpa = float(total_points / total_credits) if total_credits > 0 else None

    # -------------------------------
    # BUILD FINAL TRANSCRIPT OBJECT
    # -------------------------------
    transcript = {
        "student": {
            "name": student.get_full_name(),
            "student_id": student.student_id,
            "email": student.email,
            "department": student.department.name if student.department else None,
            "program": student.program.name if student.program else None,
            "award_type": student.program.get_award_type_display() if student.program else None,
            "program_duration_years": student.program.duration_years if student.program else None,
        },
        "semesters": transcript_semesters,
        "cgpa": cgpa,
    }

    return transcript
