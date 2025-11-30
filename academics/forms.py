# users/forms.py  (or academics/forms.py, whichever app you keep models in)
from django import forms
from .models import Resource, Semester

class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ("title", "summary", "external_link", "file", "semester")
        widgets = {
            "title": forms.TextInput(attrs={"class": "w-full border-c rounded px-3 py-2 "}),
            "summary": forms.Textarea(attrs={"class": "w-full border-c rounded px-3 py-2", "rows": 4}),
            "external_link": forms.URLInput(attrs={"class": "w-full border-c rounded px-3 py-2"}),
            "semester": forms.Select(attrs={"class": "w-full border-c rounded px-3 py-2"}),
        }

    def __init__(self, *args, **kwargs):
        # optionally limit semester choices to active ones
        super().__init__(*args, **kwargs)
        self.fields["semester"].queryset = Semester.objects.all().order_by("-start_date")
        self.fields["file"].required = False
        self.fields["external_link"].required = False
