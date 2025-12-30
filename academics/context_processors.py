from academics.models import ProgramCourse, Enrollment, AcademicYear, Semester, CourseAnnouncement
from portal.models import Announcement
from users.models import StudentRegistration

# def student_sidebar_data(request):
#     user = request.user

#     if not user.is_authenticated or getattr(user, "role", None) != "student":
#         return {}

#     # ---------------------------------------------------------
#     # 1. Student's current level (ProgramLevel)
#     # ---------------------------------------------------------
#     current_level = user.level
#     if not current_level:
#         return {"student_courses": []}

#     # ---------------------------------------------------------
#     # 2. Get ACTIVE academic year
#     # ---------------------------------------------------------
#     active_year = AcademicYear.objects.filter(is_active=True).first()
#     if not active_year:
#         return {"student_courses": []}

#     # ---------------------------------------------------------
#     # 3. Get the ACTIVE semester for this level under this year
#     # ---------------------------------------------------------
#     active_semester = (
#         Semester.objects.filter(
#             level=current_level,
#             academic_year=active_year,
#             is_active=True
#         ).first()
#     )

#     if not active_semester:
#         return {"student_courses": []}

#     # ---------------------------------------------------------
#     # 4. Enrollment = Proof of registration (must be is_current=True)
#     # ---------------------------------------------------------
#     enrollment = (
#         Enrollment.objects.filter(
#             student=user,
#             level=current_level,
#             semester=active_semester,
#             is_current=True
#         )
#         .select_related("program")
#         .first()
#     )

#     if not enrollment:
#         # Student has NOT registered or admin has NOT verified payment
#         return {"student_courses": []}

#     # ---------------------------------------------------------
#     # 5. Load ACTIVE ProgramCourses for this level + semester + program
#     # ---------------------------------------------------------

#         # ---------------------------------------------------------
#     # 6. Get registered course IDs
#     # ---------------------------------------------------------
#     registered_ids = enrollment.courses.values_list("id", flat=True)


#     courses = (
#         ProgramCourse.objects.filter(
#             id__in=registered_ids,
#             program=enrollment.program,
#             level=current_level,
#             semester=active_semester,
#             is_active=True
#         )
#         .only("course_code", "title", "credit_hours", "id")
#         .order_by("course_code")
#     )

#     announcements = Announcement.objects.filter(
#         role__in=["lecturer", "dean"], is_active=True
#     ).order_by("-created_at")[:5]

#     return {
#         "student_courses": courses,
#         "student_announcements": announcements
#             }



def student_sidebar_data(request):
    user = request.user

    if not user.is_authenticated or getattr(user, "role", None) != "student":
        return {}

    # ---------------------------------------------------------
    # 1. Student level
    # ---------------------------------------------------------
    current_level = user.level
    if not current_level:
        return {"student_courses": []}

    # ---------------------------------------------------------
    # 2. Active academic year
    # ---------------------------------------------------------
    active_year = AcademicYear.objects.filter(is_active=True).first()
    if not active_year:
        return {"student_courses": []}

    # ---------------------------------------------------------
    # 3. Active semester
    # ---------------------------------------------------------
    active_semester = Semester.objects.filter(
        academic_year=active_year,
        level=current_level,
        is_active=True
    ).first()

    if not active_semester:
        return {"student_courses": []}

    # ---------------------------------------------------------
    # 4. HARD GATE: Enrollment (payment / verification proof)
    # ---------------------------------------------------------
    enrollment = Enrollment.objects.filter(
        student=user,
        level=current_level,
        semester=active_semester,
        is_current=True
    ).select_related("program").first()

    if not enrollment:
        # Student has not paid / not verified
        return {"student_courses": []}

    # ---------------------------------------------------------
    # 5. StudentRegistration (selected courses)
    # ---------------------------------------------------------
    registration = StudentRegistration.objects.filter(
        student=user,
        academic_year=active_year,
        semester=active_semester,
        program=enrollment.program,
        status__in=["submitted", "approved"]
    ).prefetch_related("courses").first()

    if not registration:
        return {"student_courses": []}

    # ---------------------------------------------------------
    # 6. ProgramCourses FIRST (your approach)
    # ---------------------------------------------------------
    program_courses = ProgramCourse.objects.filter(
        program=enrollment.program,
        level=current_level,
        semester=active_semester,
        is_active=True
    )

    # ---------------------------------------------------------
    # 7. Compare ProgramCourses ↔ Registration courses
    # ---------------------------------------------------------
    registered_ids = registration.courses.values_list("id", flat=True)

    courses = (
        program_courses
        .filter(id__in=registered_ids)
        .only("id", "course_code", "title", "credit_hours")
        .order_by("course_code")
    )

    # ---------------------------------------------------------
    # 8. Course Announcements (for notification preview)
    # ---------------------------------------------------------
    announcements = (
        CourseAnnouncement.objects
        .filter(
            course__in=courses,
            send_as_notification=True,
        )
        .select_related("course", "sender")
        .order_by("-created_at")[:5]   # preview limit
    )

    has_active_announcements = any(
        ann.is_active for ann in announcements
    )

    return {
        "student_courses": courses,
        "announcements": announcements,
         "has_active_announcements": has_active_announcements,
    }

