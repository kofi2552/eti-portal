from django.contrib import admin
from .models import Program, Course, Enrollment, Department, AcademicYear, Semester


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "dean", "created_at")
    search_fields = ("name", "code")
    ordering = ("name",)
    autocomplete_fields = ("dean",)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "department", "get_department_dean", "created_at")
    search_fields = ("name", "code", "department__name")
    list_filter = ("department", "department__dean")
    autocomplete_fields = ("department",)
    ordering = ("name",)

    def get_department_dean(self, obj):
        return obj.department.dean.username if obj.department and obj.department.dean else "-"
    get_department_dean.short_description = "Dean"


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "program", "semester")
    search_fields = ("code", "title", "program__name", "semester__name")
    list_filter = ("program", "semester")
    filter_horizontal = ("assigned_lecturers",)
    ordering = ("code",)


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "start_date", "end_date", "created_at")
    search_fields = ("name",)
    list_filter = ("is_active",)
    ordering = ("-name",)


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_year", "is_active", "start_date", "end_date")
    search_fields = ("name",)
    list_filter = ("academic_year", "is_active")
    ordering = ("academic_year", "name")

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "semester", "date_enrolled")
    search_fields = ("student__username", "course__title", "course__code")
    list_filter = ("semester",)
    ordering = ("-date_enrolled",)
