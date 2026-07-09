from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings 
from academics.models import Department, Program, AcademicYear, Semester, ProgramCourse, ProgramLevel
from users.models import Payment
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.crypto import get_random_string
import random

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

    level = models.ForeignKey(
        ProgramLevel,
        on_delete=models.CASCADE,
        null=True,
        blank=True
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
        unique_together = ("academic_year", "semester", "program", "level")

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

    code = models.CharField(
        max_length=50,
        default="code",
        help_text="Unique generated code for the fee component",
        editable=False
    )

    class Meta:
        verbose_name = "Fee Component"
        verbose_name_plural = "Fee Components"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.code == "code" or not self.code:
            letters = "".join([word[0] for word in self.name.split() if word]).upper()
            if len(letters) == 1:
                letters = self.name[:3].upper()
            
            while True:
                d1 = str(random.randint(0, 9))
                d2 = str(random.randint(0, 9))
                new_code = f"{d1}{letters}{d2}"
                if not FeeComponent.objects.filter(code=new_code).exclude(pk=self.pk).exists():
                    self.code = new_code
                    break
        super().save(*args, **kwargs)



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


class BankTransaction(models.Model):
    bank_reference_id = models.CharField(max_length=100, unique=True)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_transactions"
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    raw_payload = models.JSONField()
    status = models.CharField(max_length=20, default="pending", choices=[
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("acknowledged", "Acknowledged")
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    # --- Archival / Deletion request tracking ---
    is_archived = models.BooleanField(
        default=False,
        help_text="Soft delete/Archive. Hides transaction from standard views."
    )
    deletion_requested = models.BooleanField(
        default=False,
        help_text="Finance requested to delete/archive this record."
    )
    deletion_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_deletion_requests"
    )
    deletion_requested_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.bank_reference_id} - {self.status}"


class ApplicationForm(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name="application_forms"
    )
    application_id = models.CharField(max_length=50, unique=True)
    amount_expected = models.DecimalField(max_digits=10, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={'role': 'finance'},
        related_name="generated_applications"
    )

    def __str__(self):
        return f"{self.application_id} - {self.student.get_full_name()}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_application_id_for_student(sender, instance, created, **kwargs):
    if created and getattr(instance, "role", None) == "student":
        app_id = f"APP-{get_random_string(6, allowed_chars='0123456789')}"
        ApplicationForm.objects.create(
            student=instance,
            application_id=app_id,
            amount_expected=Decimal("0.00")
        )

class StudentOverpayment(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="overpayments"
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="overpayments"
    )
    academic_year = models.ForeignKey(
        AcademicYear, 
        on_delete=models.CASCADE
    )
    semester = models.ForeignKey(
        Semester, 
        on_delete=models.CASCADE
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    # --- Refund / Reimbursement tracking ---
    reimbursement_requested = models.BooleanField(
        default=False,
        help_text="Set to True when Finance requests a refund for the student."
    )
    reimbursement_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reimbursement_requests",
        help_text="The Finance staff member who initiated the refund request."
    )
    reimbursement_requested_at = models.DateTimeField(null=True, blank=True)
    is_reimbursed = models.BooleanField(
        default=False,
        help_text="Set to True by Admin once the student has been physically paid back."
    )
    reimbursed_at = models.DateTimeField(null=True, blank=True)

    # --- Credit Utilization ---
    is_used = models.BooleanField(
        default=False,
        help_text="Set to True when this credit is used to pay for a future fee."
    )
    used_at = models.DateTimeField(null=True, blank=True)
    used_for_payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="utilized_overpayments",
        help_text="The new payment record where this credit was applied."
    )

    def __str__(self):
        return f"{self.student.get_full_name()} - GHS {self.amount}"


class RateLimitRecord(models.Model):
    key_prefix = models.CharField(max_length=50)
    ip_address = models.CharField(max_length=45)  # supports IPv4 and IPv6
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["key_prefix", "ip_address", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.key_prefix} - {self.ip_address} @ {self.timestamp}"
