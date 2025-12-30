from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings 
from academics.models import Department, Program, AcademicYear, Semester, ProgramCourse, ProgramLevel
from users.models import Payment


class ProgramFee(models.Model):
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE
    )

    program= models.ForeignKey(
        Program,
        on_delete=models.CASCADE
    )

    name = models.CharField(
        max_length=100,
        default="Semester Fee"
    )

    initial_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="initial required amount for semester registration"
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Total semester fee declared by finance"
    )

    is_allowed = models.BooleanField(default=False)

    is_archived = models.BooleanField(default=False)

    components = models.ManyToManyField(
        "FeeComponent",
        through="ProgramFeeComponent",
        related_name="program_fees"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={'role': 'finance'}
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("academic_year", "semester", "program")

    def __str__(self):
        return f"{self.semester} ({self.academic_year}) - {self.total_amount}"



class FeeComponent(models.Model):

    name = models.CharField(
        max_length=100,
        help_text="e.g. Tuition, Library, ICT"
    )
    
    is_active = models.BooleanField(default=True)

    totalFee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    class Meta:
        verbose_name = "Fee Component"
        verbose_name_plural = "Fee Components"

    def __str__(self):
        return self.name



class ProgramFeeComponent(models.Model):
    program_fee = models.ForeignKey(
        ProgramFee,
        on_delete=models.CASCADE,
        related_name="program_fee_components"
    )

    component = models.ForeignKey(
        FeeComponent,
        on_delete=models.PROTECT,
        related_name="fee_component_links"
    )

    total_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    class Meta:
        unique_together = ("program_fee", "component")
    
    def __str__(self):
        return f"{self.program_fee} - {self.component} ({self.total_fee})"



class PaymentBreakdown(models.Model):
    
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="breakdowns"
    )

    component = models.ForeignKey(
        ProgramFeeComponent,
        on_delete=models.PROTECT
    )

    amount_expected = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("payment", "component")

    @property
    def balance(self):
        return self.amount_expected - self.amount_paid

    def __str__(self):
        return f"{self.component.component.name} - {self.amount_paid}/{self.amount_expected}"
