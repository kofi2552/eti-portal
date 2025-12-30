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
import csv



def fee_components_locked():
    return StudentRegistration.objects.filter(is_completed=True).exists()


def finance_login(request):
    if request.user.is_authenticated:
        if getattr(request.user, "role", None) == "finance":
            return redirect("finance_dashboard")
        return redirect("home")

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


def generate_student_id():
    # Example: STU + year + random digits
    from datetime import datetime
    year = datetime.now().year % 100
    random_part = get_random_string(4, allowed_chars='0123456789')
    return f"STU{year}{random_part}"


def generate_pin():
    return get_random_string(6, allowed_chars='0123456789')

@login_required
def finance_main(request):
    if getattr(request.user, "role", None) != "finance":
        messages.error(request, "Access denied.")
        return redirect("home")

    return render(
        request,
        "accounts/finance_main.html",
        {}
    )


@login_required
def finance_dashboard(request):
    if getattr(request.user, "role", None) != "finance":
        messages.error(request, "Access denied.")
        return redirect("home")

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
        return redirect("home")

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


   # -----------------------------------
    # CREATE PROGRAM FEE (CREATE ONLY)
    # -----------------------------------
    if request.method == "POST" and request.POST.get("action") == "save_program_fee":
        program_id = request.POST.get("program")
        academic_year_id = request.POST.get("academic_year")
        semester_id = request.POST.get("semester")
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
            program_fee.initial_amount = initial_amount
            program_fee.total_amount = total_amount
            program_fee.save()

            # program_fee.program_fee_components.all().delete()

            for cid, amt in components_data:
                ProgramFeeComponent.objects.filter(
                    program_fee=program_fee,
                    component_id=cid
                ).update(total_fee=amt)

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
        }
    )


@login_required
def ajax_program_fee_components(request, program_id, year_id, semester_id):
    program_fee = get_object_or_404(
        ProgramFee,
        program_id=program_id,
        academic_year_id=year_id,
        semester_id=semester_id
    )

    components = program_fee.program_fee_components.select_related("component")

    return JsonResponse({
        "initial_amount": str(program_fee.initial_amount),
        "components": [
            {
                "id": pfc.id,
                "name": pfc.component.name,
                "total_fee": str(pfc.total_fee),
                "balance": str(pfc.total_fee),
            }
            for pfc in components
        ]
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

    return JsonResponse({
        "id": fee.id,
        "academic_year": fee.academic_year.name,
        "semester": fee.semester.name,
        "program": fee.program.name,
        "initial_amount": str(fee.initial_amount),
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
    if getattr(request.user, "role", None) != "finance":
        log_event(request.user, "auth", "Unauthorized attempt to access student enrollment page")
        messages.error(request, "Access denied.")
        return redirect("home")

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


    # ============================
    # CREATE PAYMENT RECORD
    # ============================
    if request.method == "POST" and request.POST.get("create_payment"):
        student = get_object_or_404(User, id=request.POST["student_id"], role="student")
        program = get_object_or_404(Program, id=request.POST["program_id"])
        level = get_object_or_404(ProgramLevel, id=request.POST["level_id"])
        year = get_object_or_404(AcademicYear, id=request.POST["academic_year_id"])
        semester = get_object_or_404(Semester, id=request.POST["semester_id"])

        amount_expected = Decimal(request.POST["amount_expected"])
        amount_paid = Decimal(request.POST["amount_paid"])
        reference = request.POST["reference"]

        component_ids = [cid for cid in request.POST.getlist("component_id") if cid.isdigit()]

        if not component_ids:
            messages.error(request, "Select at least one fee component.")
            return redirect("finance_create_student_payment")

        components = ProgramFeeComponent.objects.filter(id__in=component_ids)

        allocated_total = Decimal("0.00")
        allocations = []

        for c in components:
            paid_so_far = (
                PaymentBreakdown.objects
                .filter(component=c, is_active=True)
                .aggregate(total=models.Sum("amount_paid"))["total"] or Decimal("0")
            )

            remaining = max(Decimal("0"), c.total_fee - paid_so_far)
            if remaining > 0:
                allocations.append((c, remaining))
                allocated_total += remaining

        if allocated_total == 0:
            messages.error(request, "Selected components are already fully paid.")
            return redirect("finance_create_student_payment")

        if amount_paid < allocated_total:
            messages.error(request, "Amount paid is less than selected component totals.")
            return redirect("finance_create_student_payment")

        credit_balance = amount_paid - allocated_total

        with transaction.atomic():
            payment = Payment.objects.create(
                student=student,
                program=program,
                academic_year=year,
                semester=semester,
                amount_expected=amount_expected,
                amount_paid=amount_paid,
                credit_balance=credit_balance,
                reference=reference,
                date_paid=timezone.now(),
                is_verified=False,
            )

            for comp, amt in allocations:
                PaymentBreakdown.objects.create(
                    payment=payment,
                    component=comp,
                    amount_expected=amt,
                    amount_paid=amt,
                    is_active=True,
                )

            if credit_balance > 0:
                messages.success(
                    request,
                    f"Payment recorded. Credit balance: GHS {credit_balance}"
                )
            else:
                messages.success(request, "Payment recorded successfully.")

            
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
 
 
    # Render page
    return render(request, "accounts/finance_payments.html", {
        "payments": payments_page,     
        "search_query": search_query, 
        "students": User.objects.filter(role="student"),
        "years": AcademicYear.objects.all(),
        "semesters": Semester.objects.all(),
        "programs": Program.objects.all(),
        "levels": ProgramLevel.objects.all(),
    })



@login_required
def finance_export_summary_payments_csv(request):
    if getattr(request.user, "role", None) != "finance":
        return redirect("home")

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
    if getattr(request.user, "role", None) != "finance":
        return redirect("home")

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
        return redirect("home")

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





















