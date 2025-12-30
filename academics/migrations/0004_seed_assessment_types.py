from django.db import migrations

def seed_assessment_types(apps, schema_editor):
    AssessmentType = apps.get_model("academics", "AssessmentType")

    default_types = [
        ("Quiz", "Short quizzes and in-class tests"),
        ("Assignment", "Take-home or class assignments"),
        ("Midterm", "Mid-semester examination"),
        ("Final Exam", "End of semester examination"),
        ("Project", "Individual or group project"),
        ("Practical", "Laboratory or hands-on assessment"),
        ("Presentation", "Oral or slide presentation"),
        ("Continuous Assessment", "Overall continuous evaluation"),
    ]

    for name, description in default_types:
        AssessmentType.objects.get_or_create(
            name=name,
            defaults={"description": description}
        )

def reverse_seed(apps, schema_editor):
    AssessmentType = apps.get_model("academics", "AssessmentType")
    AssessmentType.objects.filter(
        name__in=[
            "Quiz",
            "Assignment",
            "Midterm",
            "Final Exam",
            "Project",
            "Practical",
            "Presentation",
            "Continuous Assessment",
        ]
    ).delete()

class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0003_seed_assessment_categories"),
    ]

    operations = [
        migrations.RunPython(seed_assessment_types, reverse_seed),
    ]