# users/forms.py  (or academics/forms.py, whichever app you keep models in)
from django import forms
from django.db.models import Q
from .models import Resource, Semester

class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ("title", "summary", "external_link", "semester")
        widgets = {
            "title": forms.TextInput(attrs={"class": "w-full border-c rounded px-3 py-2 "}),
            "summary": forms.Textarea(attrs={"class": "w-full border-c rounded px-3 py-2", "rows": 4}),
            "external_link": forms.URLInput(attrs={"class": "w-full border-c rounded px-3 py-2"}),
            "semester": forms.Select(attrs={"class": "w-full border-c rounded px-3 py-2"}),
        }

    def __init__(self, *args, program=None, lecturer=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Semester.objects.filter(is_active=True).select_related("level", "academic_year")
        if program:
            qs = qs.filter(level__program=program)
        elif lecturer and getattr(lecturer, "role", None) == "lecturer":
            assigned_pcs = lecturer.program_courses_taught.filter(is_active=True)
            prog_ids = assigned_pcs.values_list("program_id", flat=True)
            direct_sem_ids = assigned_pcs.values_list("semester_id", flat=True)
            qs = qs.filter(Q(level__program_id__in=prog_ids) | Q(id__in=direct_sem_ids)).distinct()

        self.fields["semester"].queryset = qs.order_by("-academic_year__start_date", "name")
        self.fields["semester"].label_from_instance = lambda obj: f"{obj.name}_{obj.level.level_name}" if obj.level else f"{obj.name}"
        self.fields["semester"].required = False
        self.fields["external_link"].required = False

