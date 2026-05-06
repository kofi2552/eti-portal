import json
from decimal import Decimal
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils import timezone
from users.models import CustomUser as User, Payment
from academics.models import AcademicYear, Semester
from finance.models import BankTransaction, ProgramFee, ProgramFeeComponent, PaymentBreakdown
from portal.utils import log_event

def require_bank_api_key(func):
    """Decorator to require a valid Bank API Key in the Authorization header."""
    def wrapper(request, *args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JsonResponse({"status": "error", "message": "Missing or invalid Authorization header"}, status=401)
        
        token = auth_header.split(" ")[1]
        if token != settings.BANK_API_KEY:
            return JsonResponse({"status": "error", "message": "Invalid API Key"}, status=403)
        return func(request, *args, **kwargs)
    return wrapper

@csrf_exempt
@require_http_methods(["POST", "GET"])
@require_bank_api_key
def bank_validate_student(request):
    """Validates if a student ID exists and returns basic details."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            student_id = data.get("student_id")
        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)
    else:
        student_id = request.GET.get("student_id")
        
    if not student_id:
        return JsonResponse({"status": "error", "message": "student_id is required"}, status=400)
        
    try:
        from finance.models import ApplicationForm
        if student_id.startswith("APP-"):
            app = ApplicationForm.objects.get(application_id=student_id)
            student = app.student
            return JsonResponse({
                "status": "success",
                "data": {
                    "student_id": app.application_id,
                    "first_name": student.first_name,
                    "last_name": student.last_name,
                    "current_class": "Applicant",
                    "program": "N/A",
                    "semester": "N/A",
                    "expected_amount": str(app.amount_expected)
                }
            })
        else:
            student = User.objects.get(student_id=student_id, role="student")
            active_semester = Semester.objects.filter(is_active=True).first()
            
            return JsonResponse({
                "status": "success",
                "data": {
                    "student_id": student.student_id,
                    "first_name": student.first_name,
                    "last_name": student.last_name,
                    "current_class": student.level.level_name if student.level else None,
                    "program": student.program.name if student.program else None,
                    "semester": active_semester.name if active_semester else None
                }
            })
    except (User.DoesNotExist, ApplicationForm.DoesNotExist):
        return JsonResponse({"status": "error", "message": "Student ID or Application ID not found."}, status=404)
@csrf_exempt
@require_http_methods(["POST"])
@require_bank_api_key
def bank_notify_payment(request):
    """Processes payment webhook from the bank."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON payload"}, status=400)

    bank_reference_id = data.get("bank_reference_id")
    student_id = data.get("student_id")

    try:
        total_amount_paid = Decimal(str(data.get("total_amount_paid", "0")))
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid total_amount_paid format"}, status=400)

    fee_breakdown = data.get("fee_breakdown", [])

    if not bank_reference_id or not student_id:
        return JsonResponse(
            {"status": "error", "message": "Missing required fields: bank_reference_id and student_id"},
            status=400
        )

    # ---------------------------------------------------------------
    # Validate fee_breakdown sum against total_amount_paid
    # ---------------------------------------------------------------
    breakdown_total = Decimal("0.00")
    for item in fee_breakdown:
        try:
            breakdown_total += Decimal(str(item.get("amount", "0")))
        except Exception:
            return JsonResponse({"status": "error", "message": f"Invalid amount format in component: {item.get('component_code')}"}, status=400)

    if fee_breakdown and breakdown_total != total_amount_paid:
        return JsonResponse({
            "status": "error", 
            "message": f"Payment mismatch. Sum of fee components (GHS {breakdown_total}) does not match the total amount paid (GHS {total_amount_paid})."
        }, status=422)

    # ---------------------------------------------------------------
    # Verify all components in breakdown exist in the system
    # ---------------------------------------------------------------
    from finance.models import FeeComponent
    for item in fee_breakdown:
        code = item.get("component_code")
        if not FeeComponent.objects.filter(name__iexact=code, is_active=True).exists():
            return JsonResponse({
                "status": "error",
                "message": f"Invalid fee component: '{code}'. This component does not exist in our system."
            }, status=422)

    # Idempotency check: Don't process the same reference twice
    if BankTransaction.objects.filter(bank_reference_id=bank_reference_id, status="success").exists():
        return JsonResponse({
            "status": "success",
            "message": "Payment already processed.",
            "school_receipt_id": bank_reference_id
        }, status=200)

    # ---------------------------------------------------------------
    # Verify student
    # ---------------------------------------------------------------
    try:
        from finance.models import ApplicationForm
        if student_id.startswith("APP-"):
            app = ApplicationForm.objects.get(application_id=student_id)
            student = app.student
        else:
            student = User.objects.get(student_id=student_id, role="student")
    except (User.DoesNotExist, ApplicationForm.DoesNotExist):
        return JsonResponse({"status": "error", "message": "Student ID or Application ID not found"}, status=404)

    # ---------------------------------------------------------------
    # Validate fee_breakdown amounts against system records
    # (skipped for first-time applicants — they have no program yet)
    # ---------------------------------------------------------------
    if fee_breakdown and not student_id.startswith("APP-"):
        # Resolve the active semester and the student's program fee
        active_semester = Semester.objects.filter(is_active=True).first()

        if not active_semester:
            return JsonResponse(
                {"status": "error", "message": "No active semester found. Cannot validate fee components."},
                status=422
            )

        # Attempt to find the ProgramFee for this student's program + active semester
        student_program = getattr(student, "program", None)
        program_fee = None

        if student_program:
            program_fee = (
                ProgramFee.objects
                .filter(program=student_program, semester=active_semester)
                .prefetch_related("program_fee_components__component")
                .first()
            )

        if not program_fee:
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        f"No fee schedule found for program '{student_program.name if student_program else 'N/A'}' "
                        f"in the current semester '{active_semester.name}'. "
                        "Cannot validate fee component amounts."
                    )
                },
                status=422
            )

        # Build a lookup: component name (lower) -> ProgramFeeComponent
        component_lookup = {
            pfc.component.name.strip().lower(): pfc
            for pfc in program_fee.program_fee_components.all()
        }

        mismatches = []

        for idx, item in enumerate(fee_breakdown):
            component_code = item.get("component_code", "").strip()
            try:
                bank_amount = Decimal(str(item.get("amount", "0")))
            except Exception:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": f"Invalid amount format for component '{component_code}' at index {idx}."
                    },
                    status=400
                )

            lookup_key = component_code.lower()
            pfc = component_lookup.get(lookup_key)

            if pfc is None:
                mismatches.append({
                    "field": "component_code",
                    "component": component_code,
                    "issue": "unrecognised",
                    "detail": (
                        f"Fee component '{component_code}' is not part of the active fee schedule "
                        f"for program '{student_program.name if student_program else 'N/A'}' "
                        f"in semester '{active_semester.name}'."
                    )
                })
                continue

            system_amount = pfc.total_fee

            if bank_amount != system_amount:
                mismatches.append({
                    "field": "amount",
                    "component": component_code,
                    "issue": "amount_mismatch",
                    "detail": (
                        f"Amount mismatch for fee component '{component_code}': "
                        f"bank sent {bank_amount}, but the required total is {system_amount}."
                    ),
                    "bank_amount": str(bank_amount),
                    "required_amount": str(system_amount)
                })

        if mismatches:
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "Fee component amount validation failed. "
                        "The amounts allocated to one or more fee components in the payment do not match "
                        "the required amounts in our system. Please review the details below and resubmit."
                    ),
                    "mismatches": mismatches
                },
                status=422
            )

    # ---------------------------------------------------------------
    # All validations passed — log the incoming transaction
    # ---------------------------------------------------------------
    
    # Ignore fee component breakdown for first-time applicants
    if student_id.startswith("APP-") and "fee_breakdown" in data:
        del data["fee_breakdown"]

    try:
        BankTransaction.objects.create(
            bank_reference_id=bank_reference_id,
            student=student,
            total_amount=total_amount_paid,
            raw_payload=data,
            status="pending"
        )

        log_event(
            None,
            "finance",
            f"Bank Payment Received: GHS {total_amount_paid} for student {student.get_full_name()} "
            f" (Reference: {bank_reference_id}). Awaiting verification."
        )

        return JsonResponse({
            "status": "success",
            "message": "Payment logged successfully. Awaiting Finance verification.",
            "school_receipt_id": bank_reference_id,
            "total_amount": str(total_amount_paid)
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
