# finance/views.py

from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from users.models import Payment
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from finance.services.payment_total import recalculate_payment_total
from users.models import Payment, StudentRegistration
from users.models import CustomUser as User, RegistrationProgress
from .models import PaymentBreakdown
from django.db import  IntegrityError
from django.forms import inlineformset_factory
from finance.models import ProgramFee, ProgramFeeComponent, FeeComponent
from academics.models import AcademicYear, Semester, Program
from portal.utils import log_event
from academics.models import Course, Assessment, Grade, ProgramLevel, Enrollment
from django.utils.crypto import get_random_string
from django.core.paginator import Paginator
from django.db import transaction, models
from django.db.models import Q
from django.utils import timezone
from users.views import generate_student_id
import csv
from django.http import HttpResponse
import io
from .models import PaymentBreakdown, StudentOverpayment
from .models import ApplicationForm, BankTransaction



def fee_components_locked():
    return StudentRegistration.objects.filter(is_completed=True).exists()


def finance_login(request):
    if request.user.is_authenticated:
        if getattr(request.user, "role", None) == "finance":
            return redirect("finance_dashboard")
        return redirect("portal:home")

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)

        if user is None:
            messages.error(request, "Invalid credentials.")
            return redirect("finance_login")

        if getattr(user, "role", None) != "finance":
            messages.error(request, "You are not authorized as finance.")
            return redirect("finance_login")

        login(request, user)
        return redirect("finance_dashboard")

    return render(request, "finance_login.html")


def generate_pin():
    return get_random_string(6, allowed_chars='0123456789')

@login_required
def finance_main(request):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        messages.error(request, "Access denied.")
        return redirect("portal:home")

    return render(
        request,
        "accounts/finance_main.html",
        {}
    )


@login_required
def finance_dashboard(request):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        messages.error(request, "Access denied.")
        return redirect("portal:home")

    # ---------------------------------
    # Dashboard stats
    # ---------------------------------
    stats = {
        "total_payments": Payment.objects.count(),
        "verified_payments": Payment.objects.filter(is_verified=True).count(),
        "pending_payments": Payment.objects.filter(is_verified=False).count(),
        "declared_fees": ProgramFee.objects.count(),
    }

    # ---------------------------------
    # Recent payments
    # ---------------------------------
    recent_payments = (
        Payment.objects
        .select_related(
            "student",
            "semester",
            "academic_year",
            "program",
        )
        .order_by("-created_at")[:10]
    )

    # ---------------------------------
    # Fetch related ProgramFees in bulk
    # ---------------------------------
    program_fee_map = {}

    program_fees = ProgramFee.objects.filter(
        program__in=[p.program for p in recent_payments],
        academic_year__in=[p.academic_year for p in recent_payments],
        semester__in=[p.semester for p in recent_payments],
    )

    # Key by (program_id, academic_year_id, semester_id)
    for pf in program_fees:
        key = (pf.program_id, pf.academic_year_id, pf.semester_id)
        program_fee_map[key] = pf

    # ---------------------------------
    # Attach ProgramFee to each payment
    # ---------------------------------
    for payment in recent_payments:
        key = (payment.program_id, payment.academic_year_id, payment.semester_id)
        payment.program_fee = program_fee_map.get(key)

    return render(
        request,
        "accounts/finance_main.html",
        {
            "stats": stats,
            "recent_payments": recent_payments,
        }
    )


def semester_fee_list(request):
    if request.user.role != "finance":
        return redirect("portal:home")

    fees = (
        ProgramFee.objects
        .select_related("academic_year", "semester", "program")
        .prefetch_related("program_fee_components__component")
        .filter(is_archived=False)
    )

    components = FeeComponent.objects.order_by("name")

    academic_years = AcademicYear.objects.filter(is_active=True).order_by("-start_date")
    semesters = Semester.objects.filter(is_active=True)
    programs = Program.objects.filter(is_active=True).order_by("name")
    levels = ProgramLevel.objects.all().order_by("level_name")


   # -----------------------------------
    # CREATE PROGRAM FEE (CREATE ONLY)
    # -----------------------------------
    if request.method == "POST" and request.POST.get("action") == "save_program_fee":
        program_id = request.POST.get("program")
        academic_year_id = request.POST.get("academic_year")
        semester_id = request.POST.get("semester")
        level_id = request.POST.get("level")
        initial_amount = Decimal(request.POST.get("initial_amount"))
        total_amount = Decimal(request.POST.get("total_amount"))

        use_default = request.POST.get("use_default_components") == "on"
        component_ids = [
            cid for cid in request.POST.getlist("component_id")
            if cid.isdigit()
        ]

        components_data = []

        if use_default:
            for comp_id in component_ids:
                component = get_object_or_404(FeeComponent, id=comp_id)
                components_data.append((component, component.totalFee))
        else:
            component_amounts = request.POST.getlist("component_amount")

            if len(component_ids) != len(component_amounts):
                messages.error(request, "Invalid component selection.")
                return redirect("semester_fee_list")

            for comp_id, amt in zip(component_ids, component_amounts):
                component = get_object_or_404(FeeComponent, id=comp_id)
                components_data.append((component, Decimal(amt)))

        if not components_data:
            messages.error(request, "At least one fee component must be selected.")
            return redirect("semester_fee_list")

        component_sum = sum(amount for _, amount in components_data)

        if component_sum != total_amount:
            messages.error(
                request,
                "Calculated component total does not match submitted total."
            )
            return redirect("semester_fee_list")

        try:
            program_fee = ProgramFee.objects.create(
                program_id=program_id,
                academic_year_id=academic_year_id,
                semester_id=semester_id,
                level_id=level_id if level_id else None,
                initial_amount=initial_amount,
                total_amount=total_amount,
                created_by=request.user,
            )
        except IntegrityError:
            messages.error(
                request,
                "Semester fee for this program already exists."
            )
            return redirect("semester_fee_list")

        for component, amount in components_data:
            ProgramFeeComponent.objects.create(
                program_fee=program_fee,
                component=component,
                total_fee=amount
            )

        messages.success(request, "Program semester fee declared successfully.")

        program = Program.objects.get(id=program_id)
        academic_year = AcademicYear.objects.get(id=academic_year_id)
        semester = Semester.objects.get(id=semester_id)

        # Example usage in your log
        log_event(
            request.user,
            "finance",
            f"Program fees declared for {program.name} with total amount & initial amount being GHS{total_amount} & GHS{initial_amount}, "
            f"Academic Year {academic_year.name}, "
            f"Semester {semester.name}"
        )


        return redirect("semester_fee_list")

    # -----------------------------------
    # EDIT PROGRAM FEE (CREATE ONLY)
    # -----------------------------------
    if request.method == "POST" and request.POST.get("action") == "update_program_fee":
        fee_id = request.POST.get("program_fee_id")
        program_fee = get_object_or_404(ProgramFee, id=fee_id, is_allowed=True)

        level_id = request.POST.get("level")
        initial_amount = Decimal(request.POST.get("initial_amount"))
        total_amount = Decimal(request.POST.get("total_amount"))

        component_ids = request.POST.getlist("component_id")
        component_amounts = request.POST.getlist("component_amount")

        components_data = []
        for cid, amt in zip(component_ids, component_amounts):
            components_data.append((int(cid), Decimal(amt)))

        if sum(a for _, a in components_data) != total_amount:
            messages.error(request, "Component totals must equal total fee.")
            return redirect("semester_fee_list")

        with transaction.atomic():
            program_fee.level_id = level_id if level_id else None
            program_fee.initial_amount = initial_amount
            program_fee.total_amount = total_amount
            program_fee.save()

            # Identify current components
            existing_components = program_fee.program_fee_components.all()
            existing_ids = set(existing_components.values_list("component_id", flat=True))

            # Identify submitted components
            submitted_ids = set(cid for cid, _ in components_data)

            # 1. Delete removed components
            components_to_delete = existing_ids - submitted_ids
            if components_to_delete:
                ProgramFeeComponent.objects.filter(
                    program_fee=program_fee,
                    component_id__in=components_to_delete
                ).delete()

            # 2. Update existing & create new components
            for cid, amt in components_data:
                ProgramFeeComponent.objects.update_or_create(
                    program_fee=program_fee,
                    component_id=cid,
                    defaults={"total_fee": amt}
                )

        log_event(
            request.user,
            "finance",
            f"Program fees edited for {program_fee.program.name} with NEW total amount & initial amount being GHS{total_amount} & GHS{initial_amount}, "
            f"Academic Year {program_fee.academic_year.name}, "
            f"Semester {program_fee.semester.name}"
        )

        messages.success(request, "Program fee updated successfully.")
        return redirect("semester_fee_list")


    # -----------------------------
    # CREATE COMPONENT
    # -----------------------------
    if request.method == "POST" and request.POST.get("action") == "create_component":
        name = request.POST.get("name", "").strip()
        fee = request.POST.get("total_fee", "").strip()

        # if ProgramFee.objects.exists():
        #     messages.error(request, "You cannot create a new component because ProgramFee records already exist.")
        #     return redirect("semester_fee_list")


        if name and fee:
            FeeComponent.objects.get_or_create(name=name, totalFee=fee)
        
        log_event(
                request.user,
                "Finance",
                f"Fee component added successfully by - {request.user.email}"
            )
        
        return redirect("semester_fee_list")
    


    # -----------------------------
    # UPDATE COMPONENT
    # -----------------------------
    if request.method == "POST" and request.POST.get("action") == "update_component":
        component_id = request.POST.get("component_id")
        name = request.POST.get("name", "").strip()
        fee = request.POST.get("total_fee", "").strip()

        
        if component_id and name:
            if ProgramFee.objects.exists():
                # Only update the name if ProgramFee records exist
                FeeComponent.objects.filter(id=component_id).update(name=name)
                messages.warning(request, "Only the component name can be edited because ProgramFee records exist. Contact Admin for assistance")
            else:
                # Safe to update both name and fee
                FeeComponent.objects.filter(id=component_id).update(name=name, totalFee=fee)
                messages.success(request, "Component updated successfully.")


        log_event(
                request.user,
                "Finance",
                f"Fee component updated successfully by - {request.user.email}"
            )
        
        return redirect("semester_fee_list")

    # -----------------------------
    # DELETE COMPONENT
    # -----------------------------
    if request.method == "POST" and request.POST.get("action") == "delete_component":
        component_id = request.POST.get("component_id")


        if ProgramFeeComponent.objects.filter(component_id=component_id).exists():
            messages.error(request, "You cannot delete this component because it is already linked to a ProgramFee.")
            return redirect("semester_fee_list")


        FeeComponent.objects.filter(id=component_id).delete()

        log_event(
                request.user,
                "Finance",
                f"Fee component deleted successfully by - {request.user.email}"
            )
        
        return redirect("semester_fee_list")

    return render(
        request,
        "accounts/semester_fee_list.html",
        {
            "fees": fees,
            "components": components,
            "academic_years": academic_years,
            "semesters": semesters,
            "programs": programs,
            "levels": levels,
        }
    )


@login_required
def ajax_program_fee_components(request, program_id, year_id, semester_id):
    student_id = request.GET.get("student_id")
    level_id = request.GET.get("level_id")
    
    # i) First with the level, semester and program selected
    program_fee = None
    if level_id:
        program_fee = ProgramFee.objects.filter(
            program_id=program_id,
            academic_year_id=year_id,
            semester_id=semester_id,
            level_id=level_id
        ).first()
    
    # ii) With the semester and program selected (fallback if level is optional or not found)
    if not program_fee:
        program_fee = ProgramFee.objects.filter(
            program_id=program_id,
            academic_year_id=year_id,
            semester_id=semester_id,
            level_id=None
        ).first()

    if not program_fee:
        return JsonResponse({"error": "No fee structure declared for this selection."}, status=404)

    components = program_fee.program_fee_components.select_related("component")
    
    component_data = []
    
    for pfc in components:
        paid_so_far = Decimal("0.00")
        if student_id:
            try:
                s_id = int(student_id)
                paid_so_far = (
                    PaymentBreakdown.objects
                    .filter(
                        payment__student_id=s_id, 
                        component=pfc, 
                        is_active=True,
                        payment__is_verified=True  # Only count verified payments
                    )
                    .aggregate(total=models.Sum("amount_paid"))["total"] or Decimal("0.00")
                )
            except (ValueError, TypeError):
                pass
            
        remaining = max(Decimal("0.00"), pfc.total_fee - paid_so_far)
        
        if remaining > 0:
            component_data.append({
                "id": pfc.id,
                "name": pfc.component.name,
                "total_fee": str(pfc.total_fee),
                "balance": str(remaining),
            })

    available_credit = Decimal("0.00")
    if student_id:
        try:
            s_id = int(student_id)
            from finance.models import StudentOverpayment
            available_credit = StudentOverpayment.objects.filter(
                student_id=s_id, 
                is_reimbursed=False, 
                is_used=False
            ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
        except (ValueError, TypeError):
            pass

    # Check if student has already made any verified payments for this semester
    has_paid_initially = False
    if student_id:
        try:
            from users.models import Payment
            has_paid_initially = Payment.objects.filter(
                student_id=student_id,
                academic_year_id=year_id,
                semester_id=semester_id,
                is_verified=True
            ).exists()
        except Exception:
            pass

    return JsonResponse({
        "initial_amount": str(program_fee.initial_amount if not has_paid_initially else "0.00"),
        "available_credit": str(available_credit),
        "components": component_data
    })


@login_required
def finance_program_fee_detail(request, fee_id):
    if request.user.role != "finance":
        return JsonResponse({"error": "Unauthorized"}, status=403)

    fee = get_object_or_404(
        ProgramFee.objects.prefetch_related("program_fee_components__component"),
        id=fee_id,
        is_allowed=True
    )

    # Fetch levels for this program
    available_levels = ProgramLevel.objects.filter(program=fee.program).order_by("order")

    return JsonResponse({
        "id": fee.id,
        "academic_year": fee.academic_year.name,
        "semester": fee.semester.name,
        "semester_id": fee.semester_id,
        "program": fee.program.name,
        "level_id": fee.level_id,
        "level_name": fee.level.level_name if fee.level else "All Levels",
        "initial_amount": str(fee.initial_amount),
        "available_levels": [{"id": lvl.id, "name": lvl.level_name} for lvl in available_levels],
        "components": [
            {
                "id": pfc.component.id,
                "name": pfc.component.name,
                "amount": str(pfc.total_fee),
            }
            for pfc in fee.program_fee_components.all()
        ],
    })


@login_required
def finance_create_student_payment(request):
    # ---------------------------------------
    # ACCESS CONTROL
    # ---------------------------------------
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        log_event(request.user, "auth", "Unauthorized attempt to access student enrollment page")
        messages.error(request, "Access denied.")
        return redirect("portal:home")

    # Fetch all payments
    payments = Payment.objects.select_related("student", "academic_year", "semester").order_by("-created_at")

    # ======================================
    # SEARCH
    # ======================================
    search_query = request.GET.get("q", "").strip()

    # print("query: ", search_query)

    payments_qs = (
        Payment.objects
        .select_related("student", "academic_year", "semester")
        .order_by("-created_at")
    )

    if search_query:
        payments_qs = payments_qs.filter(
            Q(student__first_name__icontains=search_query) |
            Q(student__last_name__icontains=search_query) |
            Q(student__username__icontains=search_query)
        )

    # ======================================
    # PAGINATION
    # ======================================
    paginator = Paginator(payments_qs, 10)  # 10 per page
    page_number = request.GET.get("page")
    payments_page = paginator.get_page(page_number)

    # Bulk fetch ProgramFees for the displayed payments to display true amount owing
    program_fee_map = {}
    program_fees = ProgramFee.objects.filter(
        program__in=[p.program for p in payments_page],
        academic_year__in=[p.academic_year for p in payments_page],
        semester__in=[p.semester for p in payments_page],
    )
    for pf in program_fees:
        key = (pf.program_id, pf.academic_year_id, pf.semester_id)
        program_fee_map[key] = pf

    for p in payments_page:
        pf_key = (p.program_id, p.academic_year_id, p.semester_id)
        pf = program_fee_map.get(pf_key)
        total_fee = pf.total_amount if pf else p.amount_expected
        p.total_fee = total_fee
        p.amount_owing = max(0, total_fee - p.amount_paid)


    # ============================
    # CREATE PAYMENT RECORD
    # ============================
    if request.method == "POST" and request.POST.get("create_payment"):
        student = get_object_or_404(User, id=request.POST["student_id"], role="student")
        program = get_object_or_404(Program, id=request.POST["program_id"])
        level = get_object_or_404(ProgramLevel, id=request.POST["level_id"])
        year = get_object_or_404(AcademicYear, id=request.POST["academic_year_id"])
        semester = get_object_or_404(Semester, id=request.POST["semester_id"])

        # ===========================================================
        # VITAL INTEGRITY CHECKS (New Rule)
        # ===========================================================
        
        # Check if student is "Continuing" (has at least one verified payment)
        is_continuing = Payment.objects.filter(student=student, is_verified=True).exists()

        if is_continuing:
            # 1. Validate Program Match
            if student.program != program:
                messages.error(request, f"Payment Rejected: Student '{student.get_full_name()}' is enrolled in {student.program.name if student.program else 'N/A'}, not {program.name}.")
                return redirect("finance_create_student_payment")
                
            # 2. Validate Level Match
            if student.level != level:
                messages.error(request, f"Payment Rejected: Student '{student.get_full_name()}' is currently in {student.level.level_name if student.level else 'N/A'}, not {level.level_name}.")
                return redirect("finance_create_student_payment")

        # 3. Validate Semester belongs to Level (Applies to everyone)
        if semester.level != level:
            messages.error(request, f"Payment Rejected: {semester.name} is not a valid semester for {level.level_name}.")
            return redirect("finance_create_student_payment")

        # 4. Critical: Check if an official fee schedule exists (Applies to everyone)
        # i) Try with the specific level first
        pf = ProgramFee.objects.filter(program=program, academic_year=year, semester=semester, level=level).first()
        
        # ii) Fallback to program/semester fee (where level is null)
        if not pf:
            pf = ProgramFee.objects.filter(program=program, academic_year=year, semester=semester, level=None).first()

        if not pf:
            messages.error(request, f"Payment Rejected: No official fee schedule (Program Fee) found for {program.name} - {semester.name} ({year.name}). Finance must set up the fee structure before accepting payments.")
            return redirect("finance_create_student_payment")

        # ALWAYS use the initial_amount from the official ProgramFee schedule as the expected amount
        amount_expected = pf.initial_amount

        amount_paid = Decimal(request.POST.get("amount_paid", "0") or "0")
        reference = request.POST["reference"]
        
        tx_id = request.POST.get("tx_id")

        component_ids = [cid for cid in request.POST.getlist("component_id") if cid.isdigit()]
        
        # -----------------------------------------------------------
        # CREDIT UTILIZATION LOGIC
        # Fetch all unused overpayments for this student
        # -----------------------------------------------------------
        from finance.models import StudentOverpayment
        available_overpayments = StudentOverpayment.objects.filter(
            student=student, 
            is_reimbursed=False, 
            is_used=False
        )
        total_credit = available_overpayments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
        
        # Combined funds available for this transaction
        total_available_funds = amount_paid + total_credit

        components = None

        if not component_ids:
            if not is_continuing:
                # ===========================================================
                # NEW STUDENT SECURITY LAYER
                # ===========================================================
                # 1. Block if amount is less than initial registration amount
                if amount_paid < amount_expected:
                    messages.error(
                        request, 
                        f"New Student Payment Rejected: The amount paid (GHS {amount_paid}) is less than the required initial registration amount (GHS {amount_expected}) for this semester."
                    )
                    return redirect("finance_create_student_payment")
                
                # 2. Automatically select ALL fee components for this semester
                components = pf.program_fee_components.all()
                if not components.exists():
                    messages.error(request, "Critical Error: No fee components found for this program fee schedule. Please setup components first.")
                    return redirect("finance_create_student_payment")
                
                # By-pass the overpayment logic below and proceed to shared allocation
            else:
                # EXISTING OVERPAYMENT LOGIC (Continuing Students Only)

                # -------------------------------------------------------
                # OVERPAYMENT-ONLY EXCEPTION (strict rule):
                # Finance may submit a payment with NO fee components
                # selected ONLY when there is an actual amount being paid
                # (i.e. the entire amount goes directly to credit/wallet).
                # If amount_paid is zero with no components → reject.
                # -------------------------------------------------------
                if amount_paid > Decimal("0.00"):
                    with transaction.atomic():
                        payment = Payment.objects.create(
                            student=student,
                            program=program,
                            level=level,
                            academic_year=year,
                            semester=semester,
                            amount_expected=amount_expected,
                            amount_paid=amount_paid,
                            credit_balance=total_available_funds,   # Entire combined sum is now credit
                            reference=reference,
                            date_paid=timezone.now(),
                            is_verified=False,
                        )
                        
                        # Mark application as paid if this is their first payment
                        from finance.models import ApplicationForm
                        app = ApplicationForm.objects.filter(student=student, is_paid=False).first()
                        if app:
                            app.is_paid = True
                            app.save()
                        
                        # Mark old overpayments as used (absorbed into the new one)
                        for op in available_overpayments:
                            op.is_used = True
                            op.used_at = timezone.now()
                            op.used_for_payment = payment
                            op.save()

                        # Create new consolidated overpayment
                        StudentOverpayment.objects.create(
                            student=student,
                            payment=payment,
                            academic_year=year,
                            semester=semester,
                            amount=total_available_funds,
                        )
                        
                        if tx_id:
                            try:
                                from finance.models import BankTransaction
                                tx = BankTransaction.objects.get(id=tx_id)
                                tx.status = "acknowledged"
                                tx.save()
                            except BankTransaction.DoesNotExist:
                                pass
                        log_event(
                            request.user,
                            "payment",
                            f"Pure overpayment recorded for {student.get_full_name()}. "
                            f"Paid: {amount_paid}, Used Credit: {total_credit}, Total New Wallet: {total_available_funds}."
                        )
                        messages.success(
                            request,
                            f"Payment recorded. Combined GHS {total_available_funds} saved to student wallet."
                        )
                    return redirect("finance_create_student_payment")
                else:
                    messages.error(request, "Select at least one fee component.")
                    return redirect("finance_create_student_payment")

        # If not already auto-selected for new students, fetch selected components
        if components is None:
            components = ProgramFeeComponent.objects.filter(id__in=component_ids)

        allocated_total = Decimal("0.00")
        allocations = []

        for c in components:
            paid_so_far = (
                PaymentBreakdown.objects
                .filter(component=c, is_active=True, payment__student=student)
                .aggregate(total=models.Sum("amount_paid"))["total"] or Decimal("0")
            )
            remaining = max(Decimal("0"), c.total_fee - paid_so_far)
            if remaining > 0:
                allocations.append((c, remaining))
                allocated_total += remaining

        if allocated_total == 0:
            messages.error(request, "Selected components are already fully paid.")
            return redirect("finance_create_student_payment")

        if total_available_funds < allocated_total:
            messages.error(request, f"Insufficient funds (Paid: {amount_paid} + Credit: {total_credit} = {total_available_funds}) for selected components (Total: {allocated_total}).")
            return redirect("finance_create_student_payment")

        new_credit_balance = total_available_funds - allocated_total

        with transaction.atomic():
            payment = Payment.objects.create(
                student=student,
                program=program,
                level=level,
                academic_year=year,
                semester=semester,
                amount_expected=amount_expected,
                amount_paid=amount_paid,
                credit_balance=new_credit_balance,
                reference=reference,
                date_paid=timezone.now(),
                is_verified=False,
            )

            # Mark application as paid if this is their first payment
            from finance.models import ApplicationForm
            app = ApplicationForm.objects.filter(student=student, is_paid=False).first()
            if app:
                app.is_paid = True
                app.save()

            # Mark utilized overpayments
            for op in available_overpayments:
                op.is_used = True
                op.used_at = timezone.now()
                op.used_for_payment = payment
                op.save()

            for comp, amt in allocations:
                PaymentBreakdown.objects.create(
                    payment=payment,
                    component=comp,
                    amount_expected=amt,
                    amount_paid=amt,
                    is_active=True,
                )

            if new_credit_balance > 0:
                StudentOverpayment.objects.create(
                    student=student,
                    payment=payment,
                    academic_year=year,
                    semester=semester,
                    amount=new_credit_balance
                )
                messages.success(
                    request,
                    f"Payment recorded. Used GHS {total_credit} credit. Remaining overpayment of GHS {new_credit_balance} saved to wallet."
                )
            else:
                messages.success(request, f"Payment recorded successfully. Used GHS {total_credit} credit.")
                
            if tx_id:
                try:
                    from finance.models import BankTransaction
                    tx = BankTransaction.objects.get(id=tx_id)
                    tx.status = "acknowledged"
                    tx.save()
                except BankTransaction.DoesNotExist:
                    pass

            
            log_event(
                request.user,
                "payment",
                f"Payment of {amount_paid} made for student {payment.student.get_full_name()}"
            )

            return redirect("finance_create_student_payment")

        # return render(request, "accounts/finance_payments.html", {
        #     "students": User.objects.filter(role="student"),
        #     "programs": Program.objects.all(),
        #     "levels": ProgramLevel.objects.all(),
        #     "years": AcademicYear.objects.all(),
        #     "semesters": Semester.objects.all(),
        #     "payments": payments_page,     
        #     "search_query": search_query, 
        # })
 
    tx_id_get = request.GET.get("tx_id")
    prefill_student = None
    prefill_amount = None
    if tx_id_get:
        try:
            from finance.models import BankTransaction
            tx = BankTransaction.objects.get(id=tx_id_get)
            prefill_student = tx.student
            prefill_amount = tx.total_amount
        except BankTransaction.DoesNotExist:
            pass

    from finance.models import StudentOverpayment
    overpayments = StudentOverpayment.objects.select_related("student", "academic_year", "semester").order_by("-created_at")

    # Render page
    return render(request, "accounts/finance_payments.html", {
        "payments": payments_page,     
        "search_query": search_query, 
        "students": User.objects.filter(role="student"),
        "years": AcademicYear.objects.all(),
        "semesters": Semester.objects.all(),
        "programs": Program.objects.all(),
        "levels": ProgramLevel.objects.all(),
        "tx_id": tx_id_get,
        "prefill_student": prefill_student,
        "prefill_amount": prefill_amount,
        "overpayments": overpayments,
    })



@login_required
def finance_export_summary_payments_csv(request):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return redirect("portal:home")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="student_finance_data.csv"'

    writer = csv.writer(response)

    # ======================
    # CSV HEADER
    # ======================
    writer.writerow([
        "Student Name",
        "Student ID",
        "Program",
        "Academic Year",
        "Semester",
        "Amount Paid",
        "Credit Balance",
        "Verified",
        "Reference",
        "Date Paid",
    ])

    payments = (
        Payment.objects
        .select_related("student", "program", "academic_year", "semester")
        .order_by("-created_at")
    )

    for p in payments:
        writer.writerow([
            p.student.get_full_name(),
            p.student.student_id or "",
            p.program.name if p.program else "",
            p.academic_year.name,
            p.semester.name,
            p.amount_paid,
            p.credit_balance,
            "YES" if p.is_verified else "NO",
            p.reference,
            p.date_paid.strftime("%Y-%m-%d %H:%M") if p.date_paid else "",
        ])

    return response



@login_required
def finance_export_payments_csv(request):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return redirect("portal:home")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="student_finance_breakdown.csv"'
    )

    writer = csv.writer(response)

    # ==========================
    # HEADER
    # ==========================
    writer.writerow([
        "Student Name",
        "Student ID",
        "Program",
        "Academic Year",
        "Semester",
        "Fee Component",
        "Component Paid",
        "Credit Balance",
        "Payment Verified",
        "Reference",
        "Date Paid",
    ])

    payments = (
        Payment.objects
        .select_related("student", "program", "academic_year", "semester")
        .prefetch_related("breakdowns__component")
        .order_by("-created_at")
    )

    for payment in payments:
        base_row = [
            payment.student.get_full_name(),
            payment.student.student_id or "",
            payment.program.name if payment.program else "",
            payment.academic_year.name,
            payment.semester.name,
        ]

        breakdowns = payment.breakdowns.all()

        # -----------------------
        # COMPONENT ROWS
        # -----------------------
        for bd in breakdowns:
            writer.writerow(
                base_row + [
                    bd.component.component.name
                    if hasattr(bd.component, "component")
                    else str(bd.component),
                    bd.amount_paid,
                    "",  # credit column empty for normal components
                    "YES" if payment.is_verified else "NO",
                    payment.reference,
                    payment.date_paid.strftime("%Y-%m-%d %H:%M")
                    if payment.date_paid else "",
                ]
            )

        # -----------------------
        # CREDIT ROW (IF ANY)
        # -----------------------
        if payment.credit_balance > 0:
            writer.writerow(
                base_row + [
                    "CREDIT",
                    "",  # component paid empty
                    payment.credit_balance,
                    "YES" if payment.is_verified else "NO",
                    payment.reference,
                    payment.date_paid.strftime("%Y-%m-%d %H:%M")
                    if payment.date_paid else "",
                ]
            )

    return response



@login_required
def finance_payment_detail(request, student_id):
    if getattr(request.user, "role", None) != "finance":
        messages.error(request, "Access denied.")
        return redirect("portal:home")

    student = get_object_or_404(
        User.objects.select_related("program"),
        id=student_id,
        role="student"
    )

    payments = (
        Payment.objects
        .filter(student=student)
        .select_related("academic_year", "semester", "program")
        .prefetch_related("breakdowns__component__component")
        .order_by(
            "academic_year__start_date",
            "semester__start_date",
            "created_at"
        )
    )

    # Program fees per year/semester
    program_fees = {
        (pf.academic_year_id, pf.semester_id): pf
        for pf in (
            ProgramFee.objects
            .filter(program=student.program)
            .prefetch_related("program_fee_components__component")
        )
    }

    finance_data = {}

    # --------------------------------------
    # 1. AGGREGATE PAYMENTS
    # --------------------------------------
    for payment in payments:
        key = (payment.academic_year, payment.semester)

        if key not in finance_data:
            pf = program_fees.get(
                (payment.academic_year_id, payment.semester_id)
            )

            finance_data[key] = {
                "academic_year": payment.academic_year,
                "semester": payment.semester,
                "program_fee": pf,
                "payments": [],
                "total_paid": Decimal("0.00"),
                "credit": Decimal("0.00"),
                "balance": Decimal("0.00"),
                "is_fully_paid": False,
                "components": {},
            }

        block = finance_data[key]

        block["payments"].append(payment)
        block["total_paid"] += payment.amount_paid
        block["credit"] += payment.credit_balance

        for bd in payment.breakdowns.all():
            name = bd.component.component.name
            comp = block["components"].setdefault(
            name,
            {
                "expected": Decimal("0.00"),
                "paid": Decimal("0.00"),
                "balance": Decimal("0.00"),
            }
        )

        comp["expected"] += bd.amount_expected
        comp["paid"] += bd.amount_paid
        comp["balance"] = max(
            Decimal("0.00"),
            comp["expected"] - comp["paid"]
        )

    # --------------------------------------
    # 2. CALCULATE BALANCES (ONCE)
    # --------------------------------------
    for block in finance_data.values():
        pf = block["program_fee"]
        if pf:
            block["balance"] = max(
                Decimal("0.00"),
                pf.total_amount - block["total_paid"]
            )
            block["is_fully_paid"] = block["balance"] == 0

    return render(
        request,
        "accounts/finance_student_finance_detail.html",
        {
            "student": student,
            "finance_data": finance_data,
        }
    )



@login_required
def finance_applications(request):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return redirect("portal:home")

    query = request.GET.get("q", "")
    applications = ApplicationForm.objects.select_related("student")

    if query:
        applications = applications.filter(
            models.Q(student__first_name__icontains=query) |
            models.Q(student__last_name__icontains=query) |
            models.Q(student__username__icontains=query) |
            models.Q(application_id__icontains=query)
        )

    applications = applications.order_by("-created_at")

    return render(request, "accounts/applications.html", {
        "applications": applications,
        "query": query
    })

@login_required
def finance_bank_transactions(request):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return redirect("portal:home")

    query = request.GET.get("q", "")
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    show_archived = request.GET.get("show_archived", "off") == "on"

    transactions = BankTransaction.objects.select_related("student")

    # Filter by Archive Status
    transactions = transactions.filter(is_archived=show_archived)

    # Filter by Query
    if query:
        transactions = transactions.filter(
            models.Q(student__first_name__icontains=query) |
            models.Q(student__last_name__icontains=query) |
            models.Q(student__username__icontains=query) |
            models.Q(bank_reference_id__icontains=query)
        )

    # Filter by Date Range
    if start_date:
        transactions = transactions.filter(created_at__date__gte=start_date)
    if end_date:
        transactions = transactions.filter(created_at__date__lte=end_date)

    transactions = transactions.order_by("-created_at")

    return render(request, "accounts/bank_transactions.html", {
        "transactions": transactions,
        "query": query,
        "start_date": start_date,
        "end_date": end_date,
        "show_archived": show_archived
    })

@login_required
def finance_verify_bank_transaction(request, tx_id):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return redirect("portal:home")
        
    if request.method == "POST":
        tx = get_object_or_404(BankTransaction, id=tx_id)
        
        if tx.status == "verified":
            messages.error(request, "Already verified")
            return redirect("finance_bank_transactions")
            
        with transaction.atomic():
            tx.status = "verified"
            tx.save()
            
            student = tx.student
            if student:
                messages.success(request, "Transaction verified successfully.")
            
                log_event(
                    request.user,
                    "finance",
                    f"Bank Transaction VERIFIED: {tx.bank_reference_id} for student {student.get_full_name()} "
                    f"(ID: {student.student_id})."
                )
                    
                # Update the application status if it exists
                app = ApplicationForm.objects.filter(student=student, is_paid=False).first()
                if app:
                    app.is_paid = True
                    app.save()
            else:
                messages.success(request, "Transaction verified successfully.")
                log_event(
                    request.user,
                    "finance",
                    f"Bank Transaction VERIFIED: {tx.bank_reference_id} (No student linked)."
                )

        return redirect("finance_bank_transactions")
        
    return redirect("finance_bank_transactions")


# -----------------------------------------------------------------------
# OVERPAYMENT REIMBURSEMENT – STEP 1: Finance requests refund
# -----------------------------------------------------------------------
@login_required
def finance_request_reimbursement(request, op_id):
    """Finance staff mark an overpayment record as 'refund requested'.
    This surfaces a pending confirmation task to Admin."""
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        messages.error(request, "Access denied.")
        return redirect("portal:home")

    if request.method != "POST":
        return redirect("finance_create_student_payment")

    from finance.models import StudentOverpayment
    op = get_object_or_404(StudentOverpayment, id=op_id)

    if op.is_reimbursed:
        messages.info(request, "This overpayment has already been reimbursed.")
        return redirect("finance_create_student_payment")

    if op.reimbursement_requested:
        messages.info(request, "Reimbursement request already submitted. Awaiting admin confirmation.")
        return redirect("finance_create_student_payment")

    op.reimbursement_requested = True
    op.reimbursement_requested_by = request.user
    op.reimbursement_requested_at = timezone.now()
    op.save()

    log_event(
        request.user,
        "finance",
        f"Reimbursement requested for overpayment of GHS {op.amount} "
        f"belonging to {op.student.get_full_name()} (Overpayment ID: {op.id})."
    )
    messages.success(
        request,
        f"Refund request submitted for GHS {op.amount} — awaiting admin confirmation."
    )
    return redirect("finance_create_student_payment")


# -----------------------------------------------------------------------
# OVERPAYMENT REIMBURSEMENT – STEP 2: Admin confirms & marks reimbursed
# -----------------------------------------------------------------------
@login_required
def admin_confirm_reimbursement(request, op_id):
    """Admin confirms that the student has been physically paid back.
    This can only be done after Finance has submitted a refund request."""
    if getattr(request.user, "role", None) not in ["admin", "superadmin"]:
        messages.error(request, "Access denied. Only admins can confirm reimbursements.")
        return redirect("portal:home")

    if request.method != "POST":
        return redirect("portal:home")

    from finance.models import StudentOverpayment
    op = get_object_or_404(StudentOverpayment, id=op_id)

    if not op.reimbursement_requested:
        messages.error(request, "No reimbursement request has been made for this record.")
        return redirect("admin_main")

    if op.is_reimbursed:
        messages.info(request, "This overpayment has already been marked as reimbursed.")
        return redirect("admin_main")

    op.is_reimbursed = True
    op.reimbursed_at = timezone.now()
    op.save()

    log_event(
        request.user,
        "finance",
        f"Reimbursement CONFIRMED for overpayment of GHS {op.amount} "
        f"belonging to {op.student.get_full_name()} (Overpayment ID: {op.id})."
    )
    messages.success(
        request,
        f"Reimbursement of GHS {op.amount} confirmed for {op.student.get_full_name()}."
    )
    # Redirect back to wherever admin came from, default to admin dashboard
    next_url = request.POST.get("next") or "admin_main"
    return redirect(next_url)


# -----------------------------------------------------------------------
# OVERPAYMENT REIMBURSEMENT – STEP 2.5: Admin REJECTS refund request
# -----------------------------------------------------------------------
@login_required
def admin_reject_reimbursement(request, op_id):
    """Admin rejects the refund request. The overpayment remains in the wallet."""
    if getattr(request.user, "role", None) not in ["admin", "superadmin"]:
        messages.error(request, "Access denied.")
        return redirect("portal:home")

    if request.method != "POST":
        return redirect("portal:home")

    from finance.models import StudentOverpayment
    op = get_object_or_404(StudentOverpayment, id=op_id)

    if op.is_reimbursed:
        messages.error(request, "This overpayment is already reimbursed.")
        return redirect("admin_main")

    op.reimbursement_requested = False
    op.reimbursement_requested_by = None
    op.reimbursement_requested_at = None
    op.save()

    log_event(
        request.user,
        "finance",
        f"Reimbursement REJECTED for overpayment of GHS {op.amount} "
        f"belonging to {op.student.get_full_name()} (Overpayment ID: {op.id})."
    )
    messages.warning(
        request,
        f"Refund request for {op.student.get_full_name()} has been rejected. The amount remains in their wallet."
    )
    next_url = request.POST.get("next") or "admin_main"
    return redirect(next_url)


# -----------------------------------------------------------------------
# BANK TRANSACTION ARCHIVAL (FINANCE REQUEST → ADMIN CONFIRM)
# -----------------------------------------------------------------------

@login_required
def finance_request_bank_transaction_deletion(request, tx_id):
    """Finance staff requests that a bank transaction be archived/deleted."""
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        messages.error(request, "Access denied.")
        return redirect("portal:home")

    if request.method != "POST":
        return redirect("finance_bank_transactions")

    tx = get_object_or_404(BankTransaction, id=tx_id)

    if tx.is_archived:
        messages.info(request, "This transaction is already archived.")
        return redirect("finance_bank_transactions")

    if tx.deletion_requested:
        messages.info(request, "Deletion request already pending for this transaction.")
        return redirect("finance_bank_transactions")

    tx.deletion_requested = True
    tx.deletion_requested_by = request.user
    tx.deletion_requested_at = timezone.now()
    tx.save()

    log_event(
        request.user,
        "finance",
        f"Archive request submitted for bank transaction {tx.bank_reference_id} — awaiting admin confirmation."
    )
    messages.success(
        request,
        f"Archive request submitted for {tx.bank_reference_id} — awaiting admin confirmation."
    )
    return redirect("finance_bank_transactions")


@login_required
def admin_confirm_bank_transaction_deletion(request, tx_id):
    """Admin confirms the archival/deletion of a bank transaction."""
    if getattr(request.user, "role", None) not in ["admin", "superadmin"]:
        messages.error(request, "Access denied. Only admins can confirm bank transaction deletions.")
        return redirect("portal:home")

    if request.method != "POST":
        return redirect("portal:home")

    tx = get_object_or_404(BankTransaction, id=tx_id)

    if not tx.deletion_requested:
        messages.error(request, "No deletion request has been made for this record.")
        return redirect("admin_main")

    if tx.is_archived:
        messages.info(request, "This record is already archived.")
        return redirect("admin_main")

    tx.is_archived = True
    tx.save()

    log_event(
        request.user,
        "finance",
        f"Bank Transaction ARCHIVED: {tx.bank_reference_id} (requested by {tx.deletion_requested_by.get_full_name()})."
    )
    messages.success(
        request,
        f"Bank transaction {tx.bank_reference_id} has been archived successfully."
    )
    
    next_url = request.POST.get("next") or "admin_main"
    return redirect(next_url)


@login_required
def admin_reject_bank_transaction_deletion(request, tx_id):
    """Admin rejects the archival/deletion request."""
    if getattr(request.user, "role", None) not in ["admin", "superadmin"]:
        messages.error(request, "Access denied.")
        return redirect("portal:home")

    if request.method != "POST":
        return redirect("portal:home")

    tx = get_object_or_404(BankTransaction, id=tx_id)

    if tx.is_archived:
        messages.error(request, "This record is already archived.")
        return redirect("admin_main")

    tx.deletion_requested = False
    tx.deletion_requested_by = None
    tx.deletion_requested_at = None
    tx.save()

    log_event(
        request.user,
        "finance",
        f"Archive request REJECTED for bank transaction {tx.bank_reference_id}."
    )
    messages.warning(
        request,
        f"Archive request for {tx.bank_reference_id} has been rejected."
    )
    
    next_url = request.POST.get("next") or "admin_main"
    return redirect(next_url)



@login_required
def finance_export_bank_transactions_csv(request):
    """Exports filtered bank transactions to CSV."""
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return redirect("portal:home")

    query = request.GET.get("q", "")
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    show_archived = request.GET.get("show_archived", "off") == "on"

    transactions = BankTransaction.objects.select_related("student")
    transactions = transactions.filter(is_archived=show_archived)

    if query:
        transactions = transactions.filter(
            models.Q(student__first_name__icontains=query) |
            models.Q(student__last_name__icontains=query) |
            models.Q(student__username__icontains=query) |
            models.Q(bank_reference_id__icontains=query)
        )

    if start_date:
        transactions = transactions.filter(created_at__date__gte=start_date)
    if end_date:
        transactions = transactions.filter(created_at__date__lte=end_date)

    transactions = transactions.order_by("-created_at")

    response = HttpResponse(content_type='text/csv')
    filename = f"bank_transactions_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'Reference ID', 'Student Name', 'Student ID', 
        'Amount (GHS)', 'Status', 'Date Received'
    ])

    for tx in transactions:
        writer.writerow([
            tx.bank_reference_id,
            tx.student.get_full_name() if tx.student else "N/A",
            tx.student.username if tx.student else "N/A",
            tx.total_amount,
            tx.status.title(),
            tx.created_at.strftime("%Y-%m-%d %H:%M")
        ])

    return response


@login_required
def finance_export_student_template_csv(request):
    """Exports all students to a CSV template for backlog uploading."""
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return redirect("portal:home")

    response = HttpResponse(content_type='text/csv')
    filename = f"student_backlog_template_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'Index Number', 'Full Name', 'Email', 
        'Program', 'Level', 'Academic Year', 'Semester', 
        'Total Paid', 'Reference'
    ])

    students = User.objects.filter(role="student").select_related("program", "level")
    
    for s in students:
        writer.writerow([
            s.student_id or "",
            s.get_full_name(),
            s.email,
            s.program.name if s.program else "",
            s.level.level_name if s.level else "",
            "",  # Academic Year
            "",  # Semester
            "",  # Total Paid (leave empty for finance to fill)
            ""   # Reference (leave empty for finance to fill)
        ])

    return response



@login_required
def finance_upload_backlog_csv(request):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return redirect("portal:home")
        
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        year_id = request.POST.get("academic_year_id")
        
        if not csv_file or not year_id:
            messages.error(request, "Please provide the CSV file and select an Academic Year.")
            return redirect("finance_create_student_payment")
            
        try:
            global_year = AcademicYear.objects.get(id=year_id)
            data_set = csv_file.read().decode('UTF-8')
            io_string = io.StringIO(data_set)
            reader = csv.DictReader(io_string)
            
            preview_data = []
            
            for row in reader:
                email = row.get('Email', '').strip()
                index_number = row.get('Index Number', '').strip()
                program_name = row.get('Program', '').strip()
                level_name = row.get('Level', '').strip()
                year_name = row.get('Academic Year', '').strip()
                semester_name = row.get('Semester', '').strip()
                amount_str = row.get('Total Paid', '').strip()
                reference = row.get('Reference', '').strip()
                
                if not email or not amount_str:
                    continue
                    
                status = "Ready"
                errors = []
                
                # Lookups
                student = User.objects.filter(email=email).first()
                if not student:
                    status = "Error"
                    errors.append("Student not found")
                
                # Try exact match first, then icontains for Program
                p = Program.objects.filter(name=program_name).first() if program_name else None
                if not p and program_name:
                    p = Program.objects.filter(name__icontains=program_name).first()
                
                if not p:
                    status = "Error"
                    errors.append("Program not found")
                
                # Scope Level to Program
                lvl = None
                if p and level_name:
                    lvl = ProgramLevel.objects.filter(program=p, level_name__icontains=level_name).first()
                    if not lvl:
                        lvl = ProgramLevel.objects.filter(level_name__icontains=level_name).first()
                
                if not lvl and level_name:
                    status = "Error"
                    errors.append("Level not found")
                    
                year = global_year
                
                # Try exact match first, then icontains for Semester
                matching_semesters = Semester.objects.filter(name=semester_name) if semester_name else Semester.objects.none()
                if not matching_semesters.exists() and semester_name:
                    matching_semesters = Semester.objects.filter(name__icontains=semester_name)

                if not matching_semesters.exists():
                    status = "Error"
                    errors.append("Semester not found")
                    semester = None
                else:
                    # Try to find a semester that matches the identified level
                    semester = None
                    if lvl:
                        semester = matching_semesters.filter(level=lvl).first()
                    
                    # Fallback to first match if level-specific one not found
                    if not semester:
                        semester = matching_semesters.first()
                
                # Check for existing payment
                if student and reference and Payment.objects.filter(reference=reference, student=student).exists():
                    status = "Error"
                    errors.append("Duplicate reference")

                # Check fee structure
                amount_expected = Decimal('0.00')
                if p and year and matching_semesters.exists():
                    pf = ProgramFee.objects.filter(
                        program=p,
                        academic_year=year,
                        semester__in=matching_semesters
                    ).first()
                    
                    if pf:
                        amount_expected = pf.total_amount
                        # Update identified semester to the one that actually has the fee
                        semester = pf.semester
                        if not pf.program_fee_components.exists():
                            status = "Warning"
                            errors.append("No fee components found")
                    else:
                        status = "Error"
                        errors.append("No fee structure found for this selection")

                preview_data.append({
                    'email': email,
                    'index_number': index_number,
                    'program_name': program_name,
                    'level_name': level_name,
                    'year_name': global_year.name,
                    'semester_name': semester_name,
                    'amount_paid': amount_str,
                    'reference': reference,
                    'student_name': student.get_full_name() if student else "N/A",
                    'identified_program': p.name if p else "N/A",
                    'identified_level': lvl.level_name if lvl else "N/A",
                    'identified_year': global_year.name,
                    'identified_semester': semester.name if semester else "N/A",
                    'program_id': p.id if p else None,
                    'level_id': lvl.id if lvl else None,
                    'year_id': global_year.id,
                    'semester_id': semester.id if semester else None,
                    'amount_expected': str(amount_expected),
                    'status': status,
                    'errors': ", ".join(errors)
                })
                
            request.session['backlog_preview'] = preview_data
            any_errors = any(r['status'] == 'Error' for r in preview_data)
            return render(request, "finance/backlog_preview.html", {"preview": preview_data, "any_errors": any_errors})
            
        except Exception as e:
            messages.error(request, f"Critical error processing file: {str(e)}")
            return redirect("finance_create_student_payment")
            
    return redirect("finance_create_student_payment")


@login_required
def finance_save_backlog(request):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return redirect("portal:home")
        
    preview_data = request.session.get('backlog_preview')
    if not preview_data:
        messages.error(request, "No backlog data found in session.")
        return redirect("finance_create_student_payment")
        
    any_errors = any(r['status'] == 'Error' for r in preview_data)
    if any_errors:
        messages.error(request, "Cannot finalize backlog while there are errors in the data. Please fix your CSV and re-upload.")
        return redirect("finance_create_student_payment")

    success_count = 0
    
    try:
        with transaction.atomic():
            for row in preview_data:
                email = row['email']
                student = User.objects.get(email=email)
                program = Program.objects.get(id=row['program_id'])
                level = ProgramLevel.objects.get(id=row['level_id'])
                year = AcademicYear.objects.get(id=row['year_id'])
                semester = Semester.objects.get(id=row['semester_id'])
                amount_paid = Decimal(row['amount_paid'])
                reference = row['reference']
                
                # Update student
                student.program = program
                student.level = level
                student.department = program.department
                
                if row.get('index_number'):
                    student.student_id = row['index_number']
                elif not student.student_id:
                    student.student_id = generate_student_id(program)
                
                if student.student_id:
                    student.username = student.student_id
                
                if not student.pin_code:
                    from users.views import generate_pin
                    student.pin_code = generate_pin()
                    student.set_password(student.pin_code)
                
                student.save()
                
                # Waterfall Allocation
                remaining_paid = amount_paid
                components = ProgramFeeComponent.objects.filter(
                    program_fee__program=program,
                    program_fee__academic_year=year,
                    program_fee__semester=semester
                ).order_by('id')
                
                amount_expected = sum(c.total_fee for c in components) if components else Decimal('0.00')
                
                payment = Payment.objects.create(
                    student=student,
                    program=program,
                    level=level,
                    academic_year=year,
                    semester=semester,
                    amount_expected=amount_expected,
                    amount_paid=amount_paid,
                    reference=reference or f"BACKLOG-{get_random_string(6, allowed_chars='0123456789')}",
                    date_paid=timezone.now(),
                    is_verified=True,
                    credit_balance=0,
                    generated_student_id=student.student_id,
                    generated_pin=student.pin_code
                )
                
                from finance.models import ApplicationForm
                app = ApplicationForm.objects.filter(student=student, is_paid=False).first()
                if app:
                    app.is_paid = True
                    app.save()
                
                for c in components:
                    if remaining_paid <= 0:
                        break
                    allocate = min(remaining_paid, c.total_fee)
                    remaining_paid -= allocate
                    PaymentBreakdown.objects.create(
                        payment=payment,
                        component=c,
                        amount_expected=c.total_fee,
                        amount_paid=allocate,
                        is_active=True
                    )
                    
                if remaining_paid > 0:
                    payment.credit_balance = remaining_paid
                    payment.save()
                    StudentOverpayment.objects.create(
                        student=student,
                        payment=payment,
                        academic_year=year,
                        semester=semester,
                        amount=remaining_paid
                    )
                
                success_count += 1
                
        if 'backlog_preview' in request.session:
            del request.session['backlog_preview']
        messages.success(request, f"Backlog processing complete: {success_count} successful records saved.")
        
    except Exception as e:
        messages.error(request, f"Backlog upload failed and was rolled back: {str(e)}")
        
    return redirect("finance_create_student_payment")


@login_required
def ajax_get_semesters(request, level_id):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return JsonResponse({"status": "error", "message": "Access denied"}, status=403)
    
    from academics.models import Semester
    semesters = Semester.objects.filter(level_id=level_id).select_related('academic_year').order_by('-is_active', '-academic_year__name', 'name')
    
    data = [
        {
            "id": sem.id, 
            "name": f"{sem.name} ({sem.academic_year.name})", 
            "is_active": sem.is_active,
            "year_id": sem.academic_year_id
        }
        for sem in semesters
    ]
    return JsonResponse({"semesters": data})
 
 
@login_required
def ajax_get_program_levels(request, program_id):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return JsonResponse({"status": "error", "message": "Access denied"}, status=403)
    
    from academics.models import ProgramLevel
    levels = ProgramLevel.objects.filter(program_id=program_id).order_by('order', 'level_name')
    
    data = [
        {
            "id": lvl.id, 
            "name": lvl.level_name
        }
        for lvl in levels
    ]
    return JsonResponse({"levels": data})


@login_required
def ajax_get_student_details(request, student_id):
    if getattr(request.user, "role", None) not in ["finance", "admin", "superadmin"]:
        return JsonResponse({"error": "Unauthorized"}, status=403)
        
    student = get_object_or_404(User, id=student_id, role="student")
    
    data = {
        "program_id": student.program.id if student.program else None,
        "program_name": student.program.name if student.program else "N/A",
        "level_id": student.level.id if student.level else None,
        "level_name": student.level.level_name if student.level else "N/A",
        "academic_year_id": None,
        "semester_id": None,
        "semester_name": "N/A",
    }

    # Try to find current enrollment to get academic year and semester
    # Strictly look for enrollment matching the student's current level
    current_enrollment = Enrollment.objects.filter(
        student=student, 
        is_current=True,
        semester__level=student.level
    ).first()
    
    if current_enrollment:
        data["academic_year_id"] = current_enrollment.semester.academic_year.id
        sem = current_enrollment.semester
        if sem.level != student.level:
            match = Semester.objects.filter(name=sem.name, level=student.level).first()
            if match:
                sem = match
        data["semester_id"] = sem.id
        data["semester_name"] = sem.name
    else:
        # Fallback: check their last registration for THEIR CURRENT LEVEL
        last_reg = student.registrations.filter(level=student.level).order_by("-submitted_at").first()
        if not last_reg:
            # Also check any registration, just in case, but we will fix the semester level mismatch
            last_reg = student.registrations.order_by("-submitted_at").first()

        if last_reg:
            data["academic_year_id"] = last_reg.academic_year.id
            sem = last_reg.semester
            if sem.level != student.level:
                match = Semester.objects.filter(name=sem.name, level=student.level).first()
                if match:
                    sem = match
            data["semester_id"] = sem.id
            data["semester_name"] = sem.name
            if not data["program_id"]:
                data["program_id"] = last_reg.program.id if last_reg.program else None
                data["program_name"] = last_reg.program.name if last_reg.program else "N/A"
        else:
            # Fallback 2: Check latest payment 
            last_payment = student.payments.order_by("-created_at").first()
            if last_payment:
                data["academic_year_id"] = last_payment.academic_year.id
                sem = last_payment.semester
                if sem.level != student.level:
                    match = Semester.objects.filter(name=sem.name, level=student.level).first()
                    if match:
                        sem = match
                data["semester_id"] = sem.id
                data["semester_name"] = sem.name
                if not data["program_id"]:
                    data["program_id"] = last_payment.program.id if last_payment.program else None
                    data["program_name"] = last_payment.program.name if last_payment.program else "N/A"

    # Fallback 3: If still no semester, find any active semester for their level
    if not data["semester_id"] and student.level:
        active_sem = Semester.objects.filter(level=student.level, is_active=True).first()
        if active_sem:
            data["academic_year_id"] = active_sem.academic_year_id
            data["semester_id"] = active_sem.id
            data["semester_name"] = active_sem.name
    return JsonResponse(data)
