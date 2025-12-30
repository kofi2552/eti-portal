from decimal import Decimal
from django.db import transaction
from academics.models import (
    Assessment,
    AssessmentTaskScore,
    AssessmentCategory,
    Grade,
)
from decimal import ROUND_HALF_UP


def resolve_letter_grade(percent, grade_rules):
    for rule in grade_rules:
        if rule.min_score <= percent <= rule.max_score:
            return rule.letter
    return "N/A"


@transaction.atomic
def recalculate_student_assessment(*, student, course, semester, recorded_by=None):
    scores = (
        AssessmentTaskScore.objects
        .filter(
            student=student,
            task__course=course,
            task__semester=semester,
            marks_obtained__isnull=False
        )
        .select_related("task", "task__assessment_category")
    )

    if not scores.exists():
        return None

    # ---------------------------------
    # Fetch category weights
    # ---------------------------------
    categories = {
        c.system_role: c
        for c in AssessmentCategory.objects.all()
    }

    internal_cat = categories.get("INTERNAL")
    external_cat = categories.get("EXTERNAL")

    internal_score = Decimal("0")
    internal_max = Decimal("0")
    external_score = Decimal("0")
    external_max = Decimal("0")

    for s in scores:
        cat = s.task.assessment_category.system_role
        score = Decimal(str(s.marks_obtained))
        max_score = Decimal(str(s.task.total_marks))

        if cat == "INTERNAL":
            internal_score += score
            internal_max += max_score
        else:
            external_score += score
            external_max += max_score

    # ---------------------------------
    # Weighted calculation
    # ---------------------------------
    final_score = Decimal("0")

    if internal_max > 0:
        final_score += (
            (internal_score / internal_max)
            * internal_cat.weight_percentage
        )

    if external_max > 0:
        final_score += (
            (external_score / external_max)
            * external_cat.weight_percentage
        )

    # Clamp safety
    final_score = max(
        Decimal("0"),
        min(final_score, Decimal("100"))
    ).quantize(Decimal("0.0"), rounding=ROUND_HALF_UP)

    # ---------------------------------
    # Resolve grade
    # ---------------------------------
    grade_rules = Grade.objects.order_by("-min_score")
    grade = next(
        (g.letter for g in grade_rules if g.min_score <= final_score <= g.max_score),
        "N/A"
    )

    Assessment.objects.update_or_create(
        student=student,
        course=course,
        semester=semester,
        defaults={
            "program": course.program,
            "score": final_score,
            "grade": grade,
            "recorded_by": recorded_by,
        }
    )