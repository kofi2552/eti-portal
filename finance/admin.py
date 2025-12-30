# finance/admin.py
from django.contrib import admin
from finance.models import ProgramFee, ProgramFeeComponent

class SemesterFeeComponentInline(admin.TabularInline):
    model = ProgramFeeComponent
    extra = 0

@admin.register(ProgramFee)
class SemesterFeeAdmin(admin.ModelAdmin):
    inlines = [SemesterFeeComponentInline]
    list_display = ("semester", "academic_year", "total_amount")
