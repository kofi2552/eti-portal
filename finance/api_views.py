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
        student = User.objects.get(student_id=student_id, role="student")
        return JsonResponse({
            "status": "success",
            "data": {
                "student_id": student.student_id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "current_class": student.level.name if student.level else None
            }
        })
    except User.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Student ID not found."}, status=404)

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
    except:
        return JsonResponse({"status": "error", "message": "Invalid total_amount_paid format"}, status=400)
        
    fee_breakdown = data.get("fee_breakdown", [])
    
    if not bank_reference_id or not student_id:
        return JsonResponse({"status": "error", "message": "Missing required fields: bank_reference_id and student_id"}, status=400)
        
    # Idempotency check: Don't process the same reference twice
    if BankTransaction.objects.filter(bank_reference_id=bank_reference_id, status="success").exists():
        return JsonResponse({
            "status": "success",
            "message": "Payment already processed.",
            "school_receipt_id": bank_reference_id
        }, status=200)
        
    # Verify student
    try:
        student = User.objects.get(student_id=student_id, role="student")
    except User.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Student ID not found"}, status=404)
        
    # Log the incoming transaction
    bank_tx = BankTransaction.objects.create(
        bank_reference_id=bank_reference_id,
        student=student,
        total_amount=total_amount_paid,
        raw_payload=data,
        status="pending"
    )
        
    # Validate fee breakdown sum matches the total amount
    calculated_total = sum(Decimal(str(item.get("amount", "0"))) for item in fee_breakdown)
    if calculated_total != total_amount_paid:
        bank_tx.status = "failed"
        bank_tx.save()
        return JsonResponse({"status": "error", "message": "Sum of fee_breakdown amounts does not match total_amount_paid"}, status=400)
        
    # Process payment
    try:
        # Get active academic year and semester
        active_year = AcademicYear.objects.filter(is_active=True).first()
        active_semester = Semester.objects.filter(is_active=True).first()
        
        if not active_year or not active_semester:
            raise Exception("No active academic year or semester configured in the system.")
            
        program = student.program
        level = student.level
        
        if not program:
            raise Exception("Student is not assigned to any program.")
            
        # Get the ProgramFee for this student's program/year/semester
        program_fee = ProgramFee.objects.filter(
            program=program,
            academic_year=active_year,
            semester=active_semester,
            is_archived=False
        ).first()
        
        amount_expected = program_fee.total_amount if program_fee else Decimal('0.00')
        
        with transaction.atomic():
            payment = Payment.objects.create(
                student=student,
                program=program,
                level=level,
                academic_year=active_year,
                semester=active_semester,
                amount_expected=amount_expected,
                amount_paid=total_amount_paid,
                credit_balance=Decimal('0.00'),
                reference=bank_reference_id,
                date_paid=timezone.now(),
                is_verified=False  # Finance team verifies later
            )
            
            allocated_total = Decimal('0.00')
            for item in fee_breakdown:
                comp_name = item.get("component_code", "")
                amt = Decimal(str(item.get("amount", "0")))
                
                # Match component by name (case-insensitive)
                pfc = None
                if program_fee:
                    pfc = ProgramFeeComponent.objects.filter(
                        program_fee=program_fee,
                        component__name__iexact=comp_name
                    ).first()
                    
                if not pfc:
                    raise Exception(f"Fee component '{comp_name}' not found or not applicable to student's program fee structure.")
                    
                PaymentBreakdown.objects.create(
                    payment=payment,
                    component=pfc,
                    amount_expected=pfc.total_fee,
                    amount_paid=amt,
                    is_active=True
                )
                allocated_total += amt
                
            # If the payment amount exceeded the allocated components, set it as credit balance
            payment.credit_balance = total_amount_paid - allocated_total
            payment.save()
            
            bank_tx.status = "success"
            bank_tx.save()
            
            return JsonResponse({
                "status": "success",
                "message": "Payment successfully recorded.",
                "school_receipt_id": str(payment.id)
            })
            
    except Exception as e:
        bank_tx.status = "failed"
        bank_tx.save()
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
