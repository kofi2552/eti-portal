from django.db import migrations



def seed_assessment_categories(apps, schema_editor):
    AssessmentCategory = apps.get_model('academics', 'AssessmentCategory')

    categories = [
        {
            "system_role": "INTERNAL",
            "name": "Internal Assessment",
            "weight_percentage": 40,
        },
        {
            "system_role": "EXTERNAL",
            "name": "External Examination",
            "weight_percentage": 60,
        },
    ]
    
    for category in categories:
        AssessmentCategory.objects.get_or_create(
            system_role=category["system_role"],
            defaults={
                "name": category["name"],
                "weight_percentage": category["weight_percentage"],
            },
        )



def unseed_assessment_categories(apps, schema_editor):
    """
    Reverse migration:
    Only deletes categories if they are not referenced.
    Safe to keep empty to avoid accidental data loss.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(
            seed_assessment_categories,
            unseed_assessment_categories,
        ),
    ]
