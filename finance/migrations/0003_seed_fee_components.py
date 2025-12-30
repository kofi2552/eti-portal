from django.db import migrations

def seed_fee_components(apps, schema_editor):
    FeeComponent = apps.get_model("finance", "FeeComponent")

    COMPONENTS = [
        ("Tuition", 2000),
        ("Library", 200),
        ("ICT", 200),
        ("SRC", 200),
        ("Exam", 1000),
    ]

    for name, total_fee in COMPONENTS:
        FeeComponent.objects.get_or_create(
            name=name,
            defaults={
                "totalFee": total_fee
            }
        )

class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_fee_components),
    ]
