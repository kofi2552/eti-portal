# finance/admin.py
from django.contrib import admin
from finance.models import ProgramFee, ProgramFeeComponent

class SemesterFeeComponentInline(admin.TabularInline):
    model = ProgramFeeComponent
    extra = 0

@admin.register(ProgramFee)
class SemesterFeeAdmin(admin.ModelAdmin):
    inlines = [SemesterFeeComponentInline]
    list_display = ("program", "semester", "academic_year", "total_amount", "is_allowed", "is_archived")
    list_filter = ("program", "academic_year", "is_allowed", "is_archived")
    search_fields = ("program__name", "semester__name", "academic_year__name")
    ordering = ("program", "academic_year", "semester")
