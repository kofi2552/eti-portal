from academics.models import ProgramCourse, Enrollment, AcademicYear, Semester
from portal.models import Announcement

def student_sidebar_data(request):
    user = request.user

    if not user.is_authenticated or getattr(user, "role", None) != "student":
        return {}

    # ---------------------------------------------------------
    # 1. Student's current level (ProgramLevel)
    # ---------------------------------------------------------
    current_level = user.level
    if not current_level:
        return {"student_courses": []}

    # ---------------------------------------------------------
    # 2. Get ACTIVE academic year
    # ---------------------------------------------------------
    active_year = AcademicYear.objects.filter(is_active=True).first()
    if not active_year:
        return {"student_courses": []}

    # ---------------------------------------------------------
    # 3. Get the ACTIVE semester for this level under this year
    # ---------------------------------------------------------
    active_semester = (
        Semester.objects.filter(
            level=current_level,
            academic_year=active_year,
            is_active=True
        ).first()
    )

    if not active_semester:
        return {"student_courses": []}

    # ---------------------------------------------------------
    # 4. Enrollment = Proof of registration (must be is_current=True)
    # ---------------------------------------------------------
    enrollment = (
        Enrollment.objects.filter(
            student=user,
            level=current_level,
            semester=active_semester,
            is_current=True
        )
        .select_related("program")
        .first()
    )

    if not enrollment:
        # Student has NOT registered or admin has NOT verified payment
        return {"student_courses": []}

    # ---------------------------------------------------------
    # 5. Load ACTIVE ProgramCourses for this level + semester + program
    # ---------------------------------------------------------


    courses = (
        ProgramCourse.objects.filter(
            program=enrollment.program,
            level=current_level,
            semester=active_semester,
            is_active=True
        )
        .only("course_code", "title", "credit_hours", "id")
        .order_by("course_code")
    )

    announcements = Announcement.objects.filter(
        role__in=["lecturer", "dean"], is_active=True
    ).order_by("-created_at")[:5]

    return {
        "student_courses": courses,
        "student_announcements": announcements
            }


