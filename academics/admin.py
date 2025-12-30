from django.contrib import admin
from .models import Program, Course, Enrollment, Department, AcademicYear, Semester
from .models import (
    AssessmentCategory,
    AssessmentType,
    AssessmentTask,
    AssessmentTaskScore,
)


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
    list_display = ("code", "title", "program", )
    search_fields = ("code", "title", "program__name",)
    list_filter = ("program",)
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
    list_display = ("student", "program", "level", "semester", "date_enrolled")
    search_fields = ("student__username", "program__name", "level__name")
    list_filter = ("semester",)
    ordering = ("-date_enrolled",)






@admin.register(AssessmentCategory)
class AssessmentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "system_role", "weight_percentage", "created_at")
    list_editable = ("weight_percentage",)
    ordering = ("system_role",)
    readonly_fields = ("system_role", "created_at")

    def has_delete_permission(self, request, obj=None):
        """
        Prevent deletion if the category is already used by any task.
        """
        if obj and obj.tasks.exists():
            return False
        return super().has_delete_permission(request, obj)
    

@admin.register(AssessmentType)
class AssessmentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(AssessmentTask)
class AssessmentTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "course",
        "semester",
        "assessment_type",
        "assessment_category",
        "total_marks",
        "created_by",
        "created_at",
    )

    list_filter = (
        "semester",
        "assessment_category",
        "assessment_type",
    )

    search_fields = ("title", "course__name")

    readonly_fields = ("created_at", "updated_at")



@admin.register(AssessmentTaskScore)
class AssessmentTaskScoreAdmin(admin.ModelAdmin):
    list_display = (
        "task",
        "student",
        "marks_obtained",
        "recorded_by",
        "recorded_at",
    )

    list_filter = ("task__assessment_category",)
    search_fields = ("student__username", "task__title")

    readonly_fields = (
        "task",
        "student",
        "recorded_by",
        "recorded_at",
    )








