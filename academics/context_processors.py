from academics.models import Course

def student_sidebar_data(request):
    """
    Injects student's registered courses into every student dashboard view.
    Only runs for authenticated student users.
    """
    user = request.user

    # Only apply to logged-in students
    if not user.is_authenticated or getattr(user, "role", None) != "student":
        return {}

    # Get all unique registered courses for the student
    courses = (
        Course.objects.filter(registered_students__student=user)
        .select_related("program", "semester")
        .order_by("code")
        .distinct()
    )

    return {
        "student_courses": courses
    }
