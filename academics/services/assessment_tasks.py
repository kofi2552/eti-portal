from django.db import transaction
from academics.models import AssessmentTask, AssessmentTaskScore
from users.models import StudentRegistration


@transaction.atomic
def create_task_with_scores(*, task: AssessmentTask):
    """
    Creates AssessmentTaskScore rows for all students registered
    for the task's course in the given semester.
    """

    registrations = (
        StudentRegistration.objects
        .filter(
            program=task.course.program,
            semester=task.semester,
            courses=task.course,
        )
        .select_related("student")
    )

    scores = [
        AssessmentTaskScore(
            task=task,
            student=reg.student
        )
        for reg in registrations
    ]

    AssessmentTaskScore.objects.bulk_create(scores)
