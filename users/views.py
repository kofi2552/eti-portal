from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import CustomUser as User, Payment, RegistrationProgress, StudentRegistration
from academics.models import Program, Course, AcademicYear, Semester, Assessment, Grade
from academics.models import Department, Resource
from portal.models import SystemLog
from django.core.paginator import Paginator
import csv, io
import pandas as pd
from django.http import HttpResponse
import random
from django.utils import timezone
from django.db import transaction
from django.urls import reverse
from django.utils.crypto import get_random_string
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from decimal import Decimal
from academics.forms import ResourceForm
import json
from portal.utils import log_event



# Example assumes your User model has a 'role' field with values:
# "student", "lecturer", "dean", or "admin"


def generate_student_id():
    # Example: STU + year + random digits
    from datetime import datetime
    year = datetime.now().year % 100
    random_part = get_random_string(4, allowed_chars='0123456789')
    return f"STU{year}{random_part}"

def generate_pin():
    return get_random_string(6, allowed_chars='0123456789')


# def student_login(request):
#     if request.method == "POST":
#         username = request.POST.get("username")
#         password = request.POST.get("password")
#         user = authenticate(request, username=username, password=password)
#         if user is not None and user.role == "student":
#             login(request, user)
#             return redirect("student_main")
#         else:
#             print("error happened")
#             messages.error(request, "Invalid student credentials.")
#     return render(request, "users/student_login.html")


# def lecturer_login(request):
#     if request.method == "POST":
#         email = request.POST.get("email")
#         password = request.POST.get("password")
#         user = authenticate(request, email=email, password=password)
#         if user is not None and user.role == "lecturer":
#             login(request, user)
#             return redirect("lecturer_main")
#         else:
#             messages.error(request, "Invalid lecturer credentials.")
#     return render(request, "users/lecturer_login.html")


# def dean_login(request):
#     if request.method == "POST":
#         email = request.POST.get("email")
#         password = request.POST.get("password")
#         user = authenticate(request, email=email, password=password)
#         if user is not None and user.role == "dean":
#             login(request, user)
#             return redirect("dean_main")
#         else:
#             messages.error(request, "Invalid dean credentials.")
#     return render(request, "users/dean_login.html")


# def admin_login(request):
#     if request.method == "POST":
#         email = request.POST.get("email")
#         password = request.POST.get("password")
#         user = authenticate(request, email=email, password=password)
#         if user is not None and user.role == "admin":
#             login(request, user)
#             return redirect("admin_main")
#         else:
#             messages.error(request, "Invalid admin credentials.")
#     return render(request, "users/admin_login.html")

def student_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None and user.role == "student":
            login(request, user)
            log_event(user, "auth", f"Student login successful (username: {username})")
            return redirect("student_main")

        # Failed login
        log_event(
            None,
            "auth",
            f"Failed student login attempt (username: {username})"
        )
        messages.error(request, "Invalid student credentials.")

    return render(request, "users/student_login.html")


def lecturer_login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)

        if user is not None and user.role == "lecturer":
            login(request, user)
            log_event(user, "auth", f"Lecturer login successful (email: {email})")
            return redirect("lecturer_main")

        log_event(
            None,
            "auth",
            f"Failed lecturer login attempt (email: {email})"
        )
        messages.error(request, "Invalid lecturer credentials.")

    return render(request, "users/lecturer_login.html")


def dean_login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)

        if user is not None and user.role == "dean":
            login(request, user)
            log_event(user, "auth", f"Dean login successful (email: {email})")
            return redirect("dean_main")

        log_event(
            None,
            "auth",
            f"Failed dean login attempt (email: {email})"
        )
        messages.error(request, "Invalid dean credentials.")

    return render(request, "users/dean_login.html")


def admin_login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)

        if user is not None and user.role == "admin":
            login(request, user)
            log_event(user, "auth", f"Admin login successful (email: {email})")
            return redirect("admin_main")

        log_event(
            None,
            "auth",
            f"Failed admin login attempt (email: {email})"
        )
        messages.error(request, "Invalid admin credentials.")

    return render(request, "users/admin_login.html")


@login_required
def admin_logs(request):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    logs = SystemLog.objects.select_related("user").order_by("-timestamp")

    # SEARCH
    search = request.GET.get("search", "")
    if search:
        logs = logs.filter(message__icontains=search)

    # CATEGORY
    category = request.GET.get("category", "")
    if category:
        logs = logs.filter(category=category)

    # USER FILTER
    user_id = request.GET.get("user", "")
    if user_id:
        logs = logs.filter(user_id=user_id)

    # PAGINATION
    paginator = Paginator(logs, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "users/dashboard/contents/admin/admin_logs.html", {
        "page_obj": page_obj,
        "categories": ["system", "registration", "assessment", "auth"],
        "users": User.objects.all().order_by("first_name"),
    })


# =============================
# DASHBOARD VIEWS (for redirect targets)
# =============================


@login_required(login_url='student_login')
def student_dashboard(request):
    if request.user.role != "student":
        return redirect("student_login")
    return render(request, "users/dashboard/student_dashboard_layout.html")

@login_required(login_url='lecturer_login')
def lecturer_dashboard(request):
    if request.user.role != "lecturer":
        return redirect("lecturer_login")
    return render(request, "users/dashboard/lecturer_dashboard_layout.html")

@login_required(login_url='dean_login')
def dean_dashboard(request):
    if request.user.role != "dean":
        return redirect("dean_login")
    return render(request, "users/dashboard/dean_dashboard_layout.html")

@login_required(login_url='admin_login')
def admin_dashboard(request):
    if request.user.role != "admin":
        return redirect("admin_login")
    return render(request, "users/dashboard/admin_dashboard_layout.html")


# student
@login_required
def student_main(request):
    user = request.user

    if user.role != "student":
        messages.error(request, "Access denied.")
        return redirect("home")

    # --------------------------------------------------
    # LOAD REGISTRATION PROGRESS
    # --------------------------------------------------
    progress = RegistrationProgress.objects.filter(student=user).first()

    if not progress or not progress.is_submitted:
        # Not registered yet → show simple page with zeros
        context = {
            "enrolled_courses": 0,
            "gpa": None,
            "semester_number": None,
            "student_courses": [],
            "semesters": [],
            "selected_sem_id": None,
            "course_labels": [],
            "grade_points": [],
        }
        return render(
            request,
            "users/dashboard/contents/student/student_main.html",
            context
        )

    # --------------------------------------------------
    # FETCH COURSE REGISTRATION (CURRENT SEMESTER)
    # --------------------------------------------------
    registration = StudentRegistration.objects.filter(
        student=user,
        academic_year=progress.academic_year,
        semester=progress.semester
    ).first()

    if not registration:
        # Should not happen normally
        context = {
            "enrolled_courses": 0,
            "gpa": None,
            "semester_number": None,
            "student_courses": [],
            "semesters": [],
            "selected_sem_id": None,
            "course_labels": [],
            "grade_points": [],
        }
        return render(
            request,
            "users/dashboard/contents/student/student_main.html",
            context
        )

    # Count enrolled courses
    enrolled_courses = registration.courses.count()
    student_courses = registration.courses.all()

    # --------------------------------------------------
    # GPA CALCULATION (CUMULATIVE)
    # --------------------------------------------------
    assessments = Assessment.objects.filter(
        student=user
    ).select_related("course")

    grade_point_map = {
        "A": 4.0, "B+": 3.5, "B": 3.0,
        "C+": 2.5, "C": 2.0, "D+": 1.5,
        "D": 1.0, "F": 0.0,
    }

    total_points = 0
    total_credits = 0

    for a in assessments:
        points = grade_point_map.get(a.grade, 0)
        credits = a.course.credit_hours or 3

        total_points += points * credits
        total_credits += credits

    gpa = round(total_points / total_credits, 2) if total_credits else None

    # --------------------------------------------------
    # SEMESTER NUMBER (CURRENT)
    # --------------------------------------------------
    semester_number = progress.semester.name if progress.semester else None

    # --------------------------------------------------
    # NEW FEATURE: SEMESTER DROPDOWN LIST
    # --------------------------------------------------
  
    # ----------------------------------------
    # Load semesters where the student is registered
    # ----------------------------------------
    all_regs = StudentRegistration.objects.filter(
        student=user
    ).select_related("semester", "semester__academic_year")

    # Turn them into an ordered queryset (NOT dictionaries)
    semesters = (
        Semester.objects.filter(
            id__in=all_regs.values_list("semester_id", flat=True)
        )
        .select_related("academic_year")
        .order_by("start_date")
    )

    # Determine selected semester (via dropdown)
    selected_sem_id = request.GET.get("semester")
    selected_semester = None

    if selected_sem_id:
        selected_semester = semesters.filter(id=selected_sem_id).first()
    else:
        # Default → latest semester by date
        selected_semester = semesters.last() if semesters else None
        selected_sem_id = selected_semester.id if selected_semester else None


    # --------------------------------------------------
    # LOAD COURSE LABELS + GRADE POINTS FOR GRAPH
    # --------------------------------------------------
    course_labels = []
    grade_points = []

    if selected_semester:
        sem_assessments = Assessment.objects.filter(
            student=user,
            semester=selected_semester
        ).select_related("course").order_by("course__code")

        for a in sem_assessments:
            course_labels.append(a.course.code)
            grade_points.append(grade_point_map.get(a.grade, 0))

            print("course labels", grade_points, course_labels)
    # --------------------------------------------------
    # FINAL CONTEXT
    # --------------------------------------------------
    context = {
        "enrolled_courses": enrolled_courses,
        "gpa": gpa,
        "semester_number": semester_number,
        "student_courses": student_courses,

        # NEW:
        "semesters": semesters,
        "selected_sem_id": selected_sem_id,
        "course_labels": json.dumps(course_labels),
        "grade_points": json.dumps(grade_points),
    }

    return render(
        request,
        "users/dashboard/contents/student/student_main.html",
        context
    )


@login_required
def student_course_details(request, course_id):
    user = request.user

    if user.role != "student":
        messages.error(request, "Access denied.")
        return redirect("home")

    # validate course is in student's registration
    registration = (
        StudentRegistration.objects
        .filter(student=user)
        .order_by("-submitted_at")
        .first()
    )

    if not registration:
        messages.error(request, "You are not registered for any courses.")
        return redirect("student_main")

    course = get_object_or_404(
        registration.courses.select_related("program", "semester", "department"),
        id=course_id
    )

    # fetch resources for this course
    resources = (
        Resource.objects
        .filter(course=course)
        .select_related("lecturer", "semester")
        .order_by("-created_at")
    )

    return render(request,
        "users/dashboard/contents/student/student_course_details.html",
        {
            "course": course,
            "resources": resources,
            "lecturer": course.assigned_lecturers.first(),
            "registration": registration
        }
    )


@login_required
def student_academics(request):
    return render(request, "users/dashboard/contents/student/student_academics.html")

@login_required
def register_semester(request):
    return render(request, "users/dashboard/contents/student/register_semester.html")

# lecturer
@login_required
def lecturer_main(request):
    return render(request, "users/dashboard/contents/lecturer/lecturer_main.html")

@login_required
def lecturer_courses(request):
    return render(request, "users/dashboard/contents/lecturer/lecturer_courses.html")



@login_required
def course_detail(request, course_id):
    """
    Course details + resource CRUD (create on same page).
    Only admin or assigned lecturer may add/delete resources.
    All users can view.
    """
    course = get_object_or_404(Course.objects.select_related("program", "semester"), id=course_id)
    user = request.user

    # Permission to manage resources: admin OR assigned lecturer
    can_manage = False
    if getattr(user, "role", None) == "admin":
        can_manage = True
    elif getattr(user, "role", None) == "lecturer":
        if course.assigned_lecturers.filter(id=user.id).exists():
            can_manage = True

    # List resources for this course
    resources = course.resources.select_related("lecturer", "semester").order_by("-created_at")

    # Handle resource creation (only allowed if can_manage)
    if request.method == "POST" and request.POST.get("create_resource"):
        if not can_manage:
            messages.error(request, "You do not have permission to add resources for this course.")
            return redirect("course_detail", course_id=course_id)

        form = ResourceForm(request.POST, request.FILES)
        if form.is_valid():
            resource = form.save(commit=False)
            resource.course = course
            # attach current user if lecturer; admin may leave lecturer blank
            if getattr(user, "role", None) == "lecturer":
                resource.lecturer = user
            resource.save()
            messages.success(request, "Resource added successfully.")
            return redirect("course_detail", course_id=course_id)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        # default form
        initial = {}
        if course.semester_id:
            initial["semester"] = course.semester_id
        form = ResourceForm(initial=initial)

    return render(request, "users/dashboard/contents/lecturer/course_detail.html", {
        "course": course,
        "resources": resources,
        "form": form,
        "can_manage": can_manage,
    })


@login_required
def resource_delete(request, resource_id):
    resource = get_object_or_404(Resource.objects.select_related("course", "lecturer"), id=resource_id)
    user = request.user

    # Only admin or resource owner lecturer can delete
    allowed = False
    if getattr(user, "role", None) == "admin":
        allowed = True
    elif getattr(user, "role", None) == "lecturer" and resource.lecturer_id == user.id:
        allowed = True

    if not allowed:
        messages.error(request, "Access denied.")
        return redirect("course_detail", resource.course_id)

    if request.method == "POST":
        resource.delete()
        messages.success(request, "Resource deleted.")
        return redirect("course_detail", resource.course_id)

    # If GET, show a small confirmation (optional)
    return render(request, "users/dashboard/contents/lecturer/resource_confirm_delete.html", {
        "resource": resource,
    })

@login_required
def lecturer_grades(request):
    return render(request, "users/dashboard/contents/lecturer/lecturer_grades.html")


# admin
@login_required
def student_enrollment(request):
    return render(request, "users/dashboard/contents/admin/student_enrollment.html")

@login_required
def admin_manage_users(request):
    return render(request, "users/dashboard/contents/admin/admin_manage_users.html")

@login_required
def admin_main(request):
    return render(request, "users/dashboard/contents/admin/admin_main.html")

@login_required
def admin_school(request):
    return render(request, "users/dashboard/contents/admin/admin_school.html")

@login_required
def admin_manage_programs(request):
    return render(request, "users/dashboard/contents/admin/admin_manage_programs.html")

@login_required
def admin_reports(request):
    return render(request, "users/dashboard/contents/admin/admin_reports.html")

# logout

def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("home") 

# EXTERNAL FILES
# ---------- EXPORT CSV ----------
def export_users_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="users.csv"'

    writer = csv.writer(response)
    writer.writerow(["First Name", "Last Name", "Email", "Role", "Date Joined"])

    for user in User.objects.all():
        writer.writerow([
            user.first_name,
            user.last_name,
            user.email,
            user.role,
            user.date_joined.strftime("%Y-%m-%d"),
        ])

    return response


# ✅ Manage Users (Admin)
@login_required
def admin_manage_users(request):

    # ---------- CREATE USER ----------
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()
        role = request.POST.get("role", "").strip()

        # Validate
        if not (first_name and last_name and email and password and role):
            messages.error(request, "All fields are required.")
            return redirect("admin_manage_users")

        # Check duplicate email
        if User.objects.filter(email=email).exists():
            messages.error(request, "A user with this email already exists.")
            return redirect("admin_manage_users")

        # Create user
        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            role=role,
            username=email  # or whatever you prefer
        )
        user.set_password(password)
        user.save()

        messages.success(request, f"{role.capitalize()} added successfully.")
        return redirect("admin_manage_users")

    # ---------- VIEW (GET) ----------
    users = User.objects.all().order_by("first_name")

    # SEARCH
    search_query = request.GET.get("search", "")
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    # FILTER BY ROLE
    role_filter = request.GET.get("role", "")
    if role_filter:
        users = users.filter(role=role_filter)

    # PAGINATION
    paginator = Paginator(users, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "users/dashboard/contents/admin/admin_manage_users.html", {
        "page_obj": page_obj,
        "search": search_query,
        "role_filter": role_filter,
    })

# ========== EDIT USER ==========
@login_required
def edit_user(request, id):
    if request.user.role not in ['admin', 'superadmin']:
        messages.error(request, "Access denied.")
        return redirect('home')

    user = get_object_or_404(User, id=id)

    if request.method == "POST":
        user.first_name = request.POST.get("first_name")
        user.last_name = request.POST.get("last_name")
        user.email = request.POST.get("email")
        user.role = request.POST.get("role")

        new_password = request.POST.get("password")
        if new_password:
            user.set_password(new_password)

        user.save()
        messages.success(request, "User updated successfully.")
        return redirect("admin_manage_users")

    return render(request,
                  "users/dashboard/contents/admin/edit_user.html",
                  {"user_obj": user})

@login_required
def delete_user(request, id):
    if request.user.role not in ['admin', 'superadmin']:
        messages.error(request, "Access denied.")
        return redirect('home')

    user = get_object_or_404(User, id=id)

    if request.method == "POST":
        user.delete()
        messages.success(request, "User deleted successfully.")
        return redirect("admin_manage_users")

    return render(request,
                  "users/dashboard/contents/admin/confirm_delete_user.html",
                  {"user_obj": user})

# ✅ Manage Programs (Admin)
@login_required
def admin_manage_programs(request):
    # Only admin
    if getattr(request.user, "role", None) != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    departments = Department.objects.order_by('name')
    deans = User.objects.filter(role='dean').order_by('username')  # list of possible deans

    # CREATE DEPARTMENT
    if request.method == "POST" and request.POST.get("create_department"):
        dept_name = request.POST.get("dept_name", "").strip()
        dean_id = request.POST.get("dean_id")  # new dean selection
        if dept_name:
            # generate department code
            prefix = dept_name[:3].upper()
            random_digits = ''.join([str(random.randint(0, 9)) for _ in range(5)])
            dept_code = f"{prefix}{random_digits}"

            # associate dean if selected
            dean_user = User.objects.filter(id=dean_id, role='dean').first() if dean_id else None

            Department.objects.create(
                name=dept_name,
                code=dept_code,
                dean=dean_user
            )
            messages.success(request, f"Department '{dept_name}' created successfully.")
        return redirect("admin_manage_programs")
    
    # UPDATE DEPARTMENT
    if request.method == "POST" and request.POST.get("update_department"):
        dept_id = request.POST.get("dept_id")
        department = get_object_or_404(Department, id=dept_id)
        dept_name = request.POST.get("dept_name", "").strip()
        dean_id = request.POST.get("dean_id")  # update dean

        if dept_name:
            department.name = dept_name
            if dean_id:
                department.dean = User.objects.filter(id=dean_id, role='dean').first()
            else:
                department.dean = None
            department.save()
            messages.success(request, f"Department '{dept_name}' updated successfully.")
        return redirect("admin_manage_programs")

    # DELETE DEPARTMENT
    if request.method == "POST" and request.POST.get("delete_department"):
        dept_id = request.POST.get("dept_id")
        department = get_object_or_404(Department, id=dept_id)
        department.delete()
        messages.success(request, "Department deleted successfully.")
        return redirect("admin_manage_programs")

    # CREATE PROGRAM
    if request.method == "POST" and request.POST.get("create_program"):
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        department_id = request.POST.get("department_id")
        department = get_object_or_404(Department, id=department_id)

        if name:
             # Generate code: first 3 letters in uppercase + 5 random digits
            prefix = name[:3].upper()
            random_digits = ''.join([str(random.randint(0, 9)) for _ in range(5)])
            prog_code = f"{prefix}{random_digits}"
            
            # Create program
            Program.objects.create(
                name=name,
                description=description,
                department=department,
                code=prog_code
            )
            messages.success(request, f"Program '{name}' created successfully.")
        return redirect("admin_manage_programs")

    # UPDATE PROGRAM
    if request.method == "POST" and request.POST.get("update_program"):
        program_id = request.POST.get("program_id")
        program = get_object_or_404(Program, id=program_id)
        program.name = request.POST.get("name", "").strip()
        program.description = request.POST.get("description", "").strip()
        department_id = request.POST.get("department_id")
        if department_id:
            program.department = get_object_or_404(Department, id=department_id)
        program.save()
        messages.success(request, f"Program '{program.name}' updated successfully.")
        return redirect("admin_manage_programs")
    

        # DELETE DEPARTMENT
    if request.method == "POST" and request.POST.get("delete_department"):
        dept_id = request.POST.get("dept_id")
        department = get_object_or_404(Department, id=dept_id)
        department.delete()
        messages.success(request, "Department deleted successfully.")
        return redirect("admin_manage_programs")

    # DELETE PROGRAM
    if request.method == "POST" and request.POST.get("delete_program"):
        program_id = request.POST.get("program_id")
        program = get_object_or_404(Program, id=program_id)
        program.delete()
        messages.success(request, "Program deleted successfully.")
        return redirect("admin_manage_programs")

    # Pass all departments and programs
    departments = Department.objects.all().order_by("name")
    programs = Program.objects.all().order_by("name")

    return render(request, "users/dashboard/contents/admin/admin_manage_programs.html", {
        "departments": departments,
        "programs": programs,
        "deans": deans
    })

# @login_required
# def student_enrollment(request):
#     if getattr(request.user, "role", None) != "admin":
#         messages.error(request, "Access denied.")
#         return redirect("home")

#     # Fetch all verified and pending payments
#     payments = Payment.objects.select_related("student", "academic_year", "semester").order_by("-created_at")

#     # ============================
#     # CREATE PAYMENT RECORD
#     # ============================
#     if request.method == "POST" and request.POST.get("create_payment"):
#         student_id = request.POST.get("student_id")
#         academic_year_id = request.POST.get("academic_year_id")
#         semester_id = request.POST.get("semester_id")
#         amount_expected = request.POST.get("amount_expected")
#         amount_paid = request.POST.get("amount_paid")
#         reference = request.POST.get("reference")

#         student = get_object_or_404(User, id=student_id, role="student")
#         academic_year = get_object_or_404(AcademicYear, id=academic_year_id)
#         semester = get_object_or_404(Semester, id=semester_id)

#         Payment.objects.create(
#             student=student,
#             academic_year=academic_year,
#             semester=semester,
#             amount_expected=amount_expected,
#             amount_paid=amount_paid,
#             reference=reference,
#             date_paid=timezone.now(),
#             is_verified=False,
#         )

#         messages.success(request, "Payment record added successfully.")
#         return redirect("student_enrollment")

#     # ============================
#     # VERIFY PAYMENT
#     # ============================
#     if request.method == "POST" and request.POST.get("verify_payment"):
#         payment_id = request.POST.get("payment_id")
#         payment = get_object_or_404(Payment, id=payment_id)
#         student = payment.student  # IMPORTANT

#         # 1. Mark payment verified
#         payment.is_verified = True

#         # 2. Mark student as fee paid
#         student.is_fee_paid = True

#         # 3. Generate Student ID + PIN (only if not generated before)
#         if not student.student_id:
#             student.student_id = generate_student_id()

#         if not student.pin_code:
#             student.pin_code = generate_pin()

#         # 4. Save login credentials to USER model
#         student.username = student.student_id     # Correct way (NOT set_username)
#         student.set_password(student.pin_code)    # Hash and save PIN as login password
#         student.save()

#         # 5. Save SAME credentials to PAYMENT model
#         payment.generated_student_id = student.student_id
#         payment.generated_pin = student.pin_code
#         payment.save()

#         messages.success(
#             request,
#             f"Payment verified. Student ID: {student.student_id}, PIN: {student.pin_code}"
#         )
#         return redirect("student_enrollment")


#     # ============================
#     # DELETE PAYMENT
#     # ============================
#     if request.method == "POST" and request.POST.get("delete_payment"):
#         payment_id = request.POST.get("payment_id")
#         payment = get_object_or_404(Payment, id=payment_id)
#         payment.delete()

#         messages.success(request, "Payment record deleted.")
#         return redirect("student_enrollment")
    
#     # ============================
#     # TOGGLE SEMESTER REGISTRATION ACTIVE
#     # ============================
#     if request.method == "POST" and request.POST.get("toggle_sem_reg"):
#         sem_id = request.POST.get("semester_id")
#         semester = get_object_or_404(Semester, id=sem_id)

#         semester.sem_reg_is_active = not semester.sem_reg_is_active
#         semester.save()

#         state = "activated" if semester.sem_reg_is_active else "deactivated"
#         messages.success(request, f"Course registration for {semester.name} has been {state}.")
#         return redirect("student_enrollment")

#     return render(request, "users/dashboard/contents/admin/student_enrollment.html", {
#         "payments": payments,
#         "students": User.objects.filter(role="student"),
#         "years": AcademicYear.objects.all(),
#         "semesters": Semester.objects.all(),
#     })

@login_required
def student_enrollment(request):
    # ---------------------------------------
    # ACCESS CONTROL
    # ---------------------------------------
    if getattr(request.user, "role", None) != "admin":
        log_event(request.user, "auth", "Unauthorized attempt to access student enrollment page")
        messages.error(request, "Access denied.")
        return redirect("home")

    # Fetch all payments
    payments = Payment.objects.select_related("student", "academic_year", "semester").order_by("-created_at")

    # ============================
    # CREATE PAYMENT RECORD
    # ============================
    if request.method == "POST" and request.POST.get("create_payment"):
        student_id = request.POST.get("student_id")
        academic_year_id = request.POST.get("academic_year_id")
        semester_id = request.POST.get("semester_id")
        amount_expected = request.POST.get("amount_expected")
        amount_paid = request.POST.get("amount_paid")
        reference = request.POST.get("reference")

        student = get_object_or_404(User, id=student_id, role="student")
        academic_year = get_object_or_404(AcademicYear, id=academic_year_id)
        semester = get_object_or_404(Semester, id=semester_id)

        Payment.objects.create(
            student=student,
            academic_year=academic_year,
            semester=semester,
            amount_expected=amount_expected,
            amount_paid=amount_paid,
            reference=reference,
            date_paid=timezone.now(),
            is_verified=False,
        )

        # Logging
        log_event(
            request.user,
            "registration",
            f"Created payment record for student {student.get_full_name()} - Ref: {reference}"
        )

        messages.success(request, "Payment record added successfully.")
        return redirect("student_enrollment")

    # ============================
    # VERIFY PAYMENT
    # ============================
    if request.method == "POST" and request.POST.get("verify_payment"):
        payment_id = request.POST.get("payment_id")
        payment = get_object_or_404(Payment, id=payment_id)
        student = payment.student

        # Mark payment verified
        payment.is_verified = True

        # Mark student as fee paid
        student.is_fee_paid = True

        # Generate credentials only if missing
        if not student.student_id:
            student.student_id = generate_student_id()

        if not student.pin_code:
            student.pin_code = generate_pin()

        # Update user login credentials
        student.username = student.student_id
        student.set_password(student.pin_code)
        student.save()

        # Mirror credentials on Payment record
        payment.generated_student_id = student.student_id
        payment.generated_pin = student.pin_code
        payment.save()

        # Logging
        log_event(
            request.user,
            "registration",
            f"Verified payment for {student.get_full_name()} - New ID: {student.student_id}, PIN: {student.pin_code}"
        )

        messages.success(
            request,
            f"Payment verified. Student ID: {student.student_id}, PIN: {student.pin_code}"
        )
        return redirect("student_enrollment")

    # ============================
    # DELETE PAYMENT
    # ============================
    if request.method == "POST" and request.POST.get("delete_payment"):
        payment_id = request.POST.get("payment_id")
        payment = get_object_or_404(Payment, id=payment_id)

        log_event(
            request.user,
            "registration",
            f"Deleted payment record ID {payment_id} for student {payment.student.get_full_name()}"
        )

        payment.delete()

        messages.success(request, "Payment record deleted.")
        return redirect("student_enrollment")

    # ============================
    # TOGGLE SEMESTER REGISTRATION ACTIVE
    # ============================
    if request.method == "POST" and request.POST.get("toggle_sem_reg"):
        sem_id = request.POST.get("semester_id")
        semester = get_object_or_404(Semester, id=sem_id)

        semester.sem_reg_is_active = not semester.sem_reg_is_active
        semester.save()

        state = "activated" if semester.sem_reg_is_active else "deactivated"

        # Logging
        log_event(
            request.user,
            "registration",
            f"Toggled semester registration: {semester.name} was {state}"
        )

        messages.success(request, f"Course registration for {semester.name} has been {state}.")
        return redirect("student_enrollment")

    # Render page
    return render(request, "users/dashboard/contents/admin/student_enrollment.html", {
        "payments": payments,
        "students": User.objects.filter(role="student"),
        "years": AcademicYear.objects.all(),
        "semesters": Semester.objects.all(),
    })



@login_required
def generate_payment_pdf(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)

    # Response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="payment_{payment_id}.pdf"'

    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter

    # ---------------------------------------------
    # HEADER
    # ---------------------------------------------
    title = "STUDENT PAYMENT RECORD"
    p.setFont("Helvetica-Bold", 18)
    p.setFillColor(colors.HexColor("#222222"))
    p.drawCentredString(width / 2, height - 60, title)

    # Underline
 

    # ---------------------------------------------
    # DATA TABLE CONFIG
    # ---------------------------------------------
    y = height - 120
    row_height = 28          # Taller rows for clean vertical spacing
    label_x = 60
    value_x = 240            # Second column begins here
    vertical_line_x = 220    # Divider line position

    data = [
        ("Student", payment.student.get_full_name()),
        ("Student ID", payment.generated_student_id or "N/A"),
        ("PIN", payment.generated_pin or "N/A"),
        ("Email", payment.student.email),
        ("Academic Year", payment.academic_year.name),
        ("Semester", payment.semester.name),
        ("Amount Expected", f"GHS {payment.amount_expected}"),
        ("Amount Paid", f"GHS {payment.amount_paid}"),
        ("Verified", "Yes" if payment.is_verified else "No"),
        ("Reference No.", payment.reference),
        ("Date Paid", payment.date_paid.strftime("%Y-%m-%d %H:%M") if payment.date_paid else "N/A"),
    ]

    # ---------------------------------------------
    # DRAW TABLE ROWS
    # ---------------------------------------------
    for label, value in data:
        row_top = y
        row_bottom = y - row_height

        # Row separator line
        p.setStrokeColor(colors.HexColor("#e6e6e6"))
        p.setLineWidth(0.4)
        p.line(50, row_bottom, width - 50, row_bottom)

        # Vertical divider line
        p.line(vertical_line_x, row_top, vertical_line_x, row_bottom)

        # Vertical centering inside row:
        # Middle = row_bottom + (row_height / 2) - (approx text height / 4)
        text_y = row_bottom + (row_height / 2) - 3

        # Label
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(colors.HexColor("#555555"))
        p.drawString(label_x, text_y, label)

        # Value
        p.setFont("Helvetica", 11)
        p.setFillColor(colors.black)
        p.drawString(value_x, text_y, value)

        y -= row_height

    # ---------------------------------------------
    # FOOTER
    # ---------------------------------------------
    timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
    p.setFont("Helvetica-Oblique", 8)
    p.setFillColor(colors.HexColor("#999999"))
    p.drawRightString(width - 50, 40, f"Generated on {timestamp}")

    p.showPage()
    p.save()
    return response



# DEAN SECTION ------------------------------

@login_required
def dean_main(request):
    return render(request, "users/dashboard/contents/dean/dean_main.html")

@login_required
def assign_lecturers(request):
    return render(request, "users/dashboard/contents/dean/assign_lecturers.html")

@login_required
def assessments(request):
    return render(request, "users/dashboard/contents/dean/assessments.html")

# @login_required
# def manage_courses(request):
#     return render(request, "users/dashboard/contents/dean/courses.html")


@login_required
def manage_courses(request):
    if getattr(request.user, "role", None) not in ["dean", "admin"]:
        messages.error(request, "Access denied.")
        return redirect("home")

    user = request.user

    # Admin sees all programs
    if user.role == "admin":
        programs = Program.objects.select_related('department').order_by('department__name', 'name')
    else:
        # Dean sees only programs in his/her department
        programs = Program.objects.filter(department__dean=user).order_by('name')

    programs = list(programs)

    # All semesters
    semesters = Semester.objects.all().order_by("academic_year__name", "name")

    # All courses under these programs
    courses = Course.objects.filter(program__in=programs) \
        .select_related('program', 'department', 'semester') \
        .order_by('program__name', 'title')

    lecturers = User.objects.filter(role='lecturer').order_by('last_name', 'first_name')

    # ---------- CREATE COURSE ----------
    if request.method == "POST" and request.POST.get("create_course"):
        title = request.POST.get("title", "").strip()
        code = request.POST.get("code", "").strip()
        description = request.POST.get("description", "").strip()
        credit_hours = request.POST.get("credit_hours", "").strip()

        try:
            credit_hours = int(credit_hours) if credit_hours else 3
        except ValueError:
            credit_hours = 3

        program_id = request.POST.get("program_id")
        semester_id = request.POST.get("semester_id")
        lecturer_ids = request.POST.getlist("lecturer_ids")

        if not title or not code or not program_id:
            messages.error(request, "Program, semester, course code, and title are required.")
            return redirect("manage_courses")

        program = Program.objects.filter(id=program_id).first()
        if not program or program not in programs:
            messages.error(request, "Invalid program selected.")
            return redirect("manage_courses")

        semester = Semester.objects.filter(id=semester_id).first() if semester_id else None

        if Semester.objects.filter(id=semester_id).count() == 0:
            semester = None

        if Course.objects.filter(code__iexact=code).exists():
            messages.error(request, "A course with this code already exists.")
            return redirect("manage_courses")

        course = Course.objects.create(
            program=program,
            department=program.department,
            semester=semester,
            title=title,
            code=code,
            description=description,
            credit_hours=credit_hours,
        )

        if lecturer_ids:
            course.assigned_lecturers.set(lecturer_ids)

        messages.success(request, f"Course '{course.title}' created successfully.")
        return redirect("manage_courses")

    # ---------- UPDATE COURSE ----------
    if request.method == "POST" and request.POST.get("update_course"):
        course_id = request.POST.get("course_id")
        course = get_object_or_404(Course, id=course_id)

        title = request.POST.get("title", "").strip()
        code = request.POST.get("code", "").strip()
        description = request.POST.get("description", "").strip()
        credit_hours = request.POST.get("credit_hours", "").strip()

        try:
            credit_hours = int(credit_hours) if credit_hours else course.credit_hours
        except ValueError:
            credit_hours = course.credit_hours

        program_id = request.POST.get("program_id")
        semester_id = request.POST.get("semester_id")
        lecturer_ids = request.POST.getlist("lecturer_ids")

        if not title or not code or not program_id:
            messages.error(request, "Program, semester, course code, and title are required.")
            return redirect("manage_courses")

        program = Program.objects.filter(id=program_id).first()
        if not program or program not in programs:
            messages.error(request, "Invalid program selected.")
            return redirect("manage_courses")

        semester = Semester.objects.filter(id=semester_id).first() if semester_id else None

        if Course.objects.filter(code__iexact=code).exclude(id=course.id).exists():
            messages.error(request, "A course with this code already exists.")
            return redirect("manage_courses")

        # Apply updates
        course.title = title
        course.code = code
        course.description = description
        course.credit_hours = credit_hours
        course.program = program
        course.department = program.department
        course.semester = semester
        course.save()

        course.assigned_lecturers.set(lecturer_ids)

        messages.success(request, f"Course '{course.title}' updated successfully.")
        return redirect("manage_courses")

    # ---------- DELETE COURSE ----------
    if request.method == "POST" and request.POST.get("delete_course"):
        course_id = request.POST.get("course_id")
        course = get_object_or_404(Course, id=course_id)
        course.delete()
        messages.success(request, "Course deleted successfully.")
        return redirect("manage_courses")

    # ---------- RENDER ----------
    return render(request, "users/dashboard/contents/dean/courses.html", {
        "programs": programs,
        "courses": courses,
        "lecturers": lecturers,
        "semesters": semesters,
    })



@login_required
def admin_school(request):
    academic_years = AcademicYear.objects.order_by("-start_date")
    semesters = Semester.objects.select_related("academic_year").order_by("-start_date")
    grades = Grade.objects.order_by("-min_score")  # NEW

    print("function got hit")

    # ----------------------------------------------------
    # --- ACADEMIC YEAR CRUD (UNCHANGED)
    # ----------------------------------------------------
    if request.method == "POST" and request.POST.get("create_academic_year"):
        name = request.POST.get("name", "").strip()
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")
        is_active = request.POST.get("is_active") == "on"

        if not name:
            messages.error(request, "Academic year name is required.")
            return redirect("admin_school")

        AcademicYear.objects.create(
            name=name,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active
        )
        messages.success(request, "Academic year created successfully.")
        return redirect("admin_school")

    if request.method == "POST" and request.POST.get("update_academic_year"):
        year_id = request.POST.get("academic_year_id")
        year = get_object_or_404(AcademicYear, id=year_id)
        year.name = request.POST.get("name")
        year.start_date = request.POST.get("start_date")
        year.end_date = request.POST.get("end_date")
        year.is_active = request.POST.get("is_active") == "on"
        year.save()
        messages.success(request, "Academic year updated successfully.")
        return redirect("admin_school")

    if request.method == "POST" and request.POST.get("delete_academic_year"):
        year_id = request.POST.get("academic_year_id")
        year = get_object_or_404(AcademicYear, id=year_id)
        year.delete()
        messages.success(request, "Academic year deleted.")
        return redirect("admin_school")

    # ----------------------------------------------------
    # --- SEMESTER CRUD (UNCHANGED)
    # ----------------------------------------------------
    if request.method == "POST" and request.POST.get("create_semester"):
        name = request.POST.get("name")
        academic_year_id = request.POST.get("academic_year_id")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")
        is_active = request.POST.get("is_active") == "on"

        if not name or not academic_year_id:
            messages.error(request, "Both semester and academic year are required.")
            return redirect("admin_school")

        academic_year = get_object_or_404(AcademicYear, id=academic_year_id)

        Semester.objects.create(
            name=name,
            academic_year=academic_year,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active
        )
        messages.success(request, "Semester created successfully.")
        return redirect("admin_school")

    if request.method == "POST" and request.POST.get("update_semester"):
        sem_id = request.POST.get("semester_id")
        semester = get_object_or_404(Semester, id=sem_id)
        semester.name = request.POST.get("name")
        semester.start_date = request.POST.get("start_date")
        semester.end_date = request.POST.get("end_date")
        semester.is_active = request.POST.get("is_active") == "on"

        academic_year_id = request.POST.get("academic_year_id")
        if academic_year_id:
            semester.academic_year = get_object_or_404(AcademicYear, id=academic_year_id)

        semester.save()
        messages.success(request, "Semester updated successfully.")
        return redirect("admin_school")

    if request.method == "POST" and request.POST.get("delete_semester"):
        sem_id = request.POST.get("semester_id")
        semester = get_object_or_404(Semester, id=sem_id)
        semester.delete()
        messages.success(request, "Semester deleted.")
        return redirect("admin_school")

    # ----------------------------------------------------
    # --- GRADE CRUD (NEW)
    # ----------------------------------------------------

    # CREATE
    if request.method == "POST" and request.POST.get("create_grade"):
        letter = request.POST.get("letter").upper().strip()
        min_score = request.POST.get("min_score")
        max_score = request.POST.get("max_score")

        if not letter or min_score == "" or max_score == "":
            messages.error(request, "All grade fields are required.")
            return redirect("admin_school")

        Grade.objects.create(
            letter=letter,
            min_score=min_score,
            max_score=max_score,
        )
        messages.success(request, "Grade added successfully.")
        return redirect("admin_school")

    # UPDATE
    if request.method == "POST" and request.POST.get("update_grade"):
        grade_id = request.POST.get("grade_id")
        grade = get_object_or_404(Grade, id=grade_id)

        grade.letter = request.POST.get("letter").upper().strip()
        grade.min_score = request.POST.get("min_score")
        grade.max_score = request.POST.get("max_score")
        grade.save()

        messages.success(request, "Grade updated successfully.")
        return redirect("admin_school")

    # DELETE
    if request.method == "POST" and request.POST.get("delete_grade"):
        grade_id = request.POST.get("grade_id")
        grade = get_object_or_404(Grade, id=grade_id)
        grade.delete()

        messages.success(request, "Grade deleted.")
        return redirect("admin_school")

    # ----------------------------------------------------
    # RENDER PAGE
    # ----------------------------------------------------
    return render(request, "users/dashboard/contents/admin/admin_school.html", {
        "academic_years": academic_years,
        "semesters": semesters,
        "grades": grades,                 # PASS TO FRONTEND
    })


@login_required
def lecturer_courses(request):

    # 🔒 Authorization check: only lecturers or admins can access
    if getattr(request.user, "role", None) not in ["lecturer", "admin"]:
        messages.error(request, "Access denied.")
        return redirect("home")

    # ✅ Fetch courses securely for this lecturer
    courses = (
        Course.objects.filter(assigned_lecturers=request.user)
        .select_related("program", "department", "semester__academic_year")
    )

    return render(request, "users/dashboard/contents/lecturer/lecturer_courses.html", {"courses": courses})

def registration_error(request, message, back_url_name=None, back_url_kwargs=None, status=400):
    """
    Render a clean, dedicated registration error UI with an optional back link.
    - message: error text to display to the student
    - back_url_name: optional named url to link back to (e.g. 'registration_step_3')
    - back_url_kwargs: optional dict of kwargs for reverse()
    - status: HTTP status code (defaults 400)
    """
    back_url = None
    try:
        if back_url_name:
            back_url = reverse(back_url_name, kwargs=(back_url_kwargs or {}))
    except Exception:
        back_url = None

    context = {
        "message": message,
        "back_url": back_url,
        "back_label": "Go back" if back_url else None,
    }
    return render(request, "users/dashboard/contents/student/registration_error.html", context, status=status)


@login_required
def registration_step_1(request):
    user = request.user

    # Only students can access
    if user.role != "student":
        messages.error(request, "Access denied.")
        return redirect("home")

    # Get or create progress record
    progress, _ = RegistrationProgress.objects.get_or_create(student=user)

    # ----------------------------------------------------
    # If ENTIRE registration is done → go straight to final page
    # ----------------------------------------------------
    if progress.is_submitted:
        return redirect("registration_complete")

    # ----------------------------------------------------
    # If Step 1 already done → go to Step 2
    # ----------------------------------------------------
    if progress.step1_completed:
        return redirect("registration_step_2")

    # ----------------------------------------------------
    # Check verified fee payment
    # ----------------------------------------------------
    payment = Payment.objects.filter(
        student=user,
        is_verified=True
    ).order_by("-date_paid").first()

    # CASE A — No verified payment
    if not payment:
        return render(
            request,
            "users/dashboard/contents/student/step1_no_payment.html"
        )

    # CASE B — Verified payment exists → student must confirm
    if request.method == "POST" and request.POST.get("confirm_fees"):

        # Attach academic year & semester to progress
        progress.academic_year = payment.academic_year
        progress.semester = payment.semester
        progress.step1_completed = True
        progress.save()

        return redirect("registration_step_2")

    return render(
        request,
        "users/dashboard/contents/student/step1_confirm_payment.html",
        {"payment": payment}
    )

@login_required
def registration_step_2(request):
    user = request.user

    if user.role != "student":
        messages.error(request, "Access denied.")
        return redirect("home")

    progress = RegistrationProgress.objects.filter(student=user).first()

    # Must complete Step 1
    if not progress or not progress.step1_completed:
        messages.warning(request, "Complete Step 1 first.")
        return redirect("registration_step_1")

    # --- If returning to Step 2 after completing it earlier ---
    # Reset Step 3 & Step 4 because program selection affects everything!
    if progress.step2_completed:
        progress.step2_completed = False
        progress.step3_completed = False
        progress.step4_completed = False
        progress.is_submitted = False

        progress.program = None
        request.session.pop("selected_courses", None)

        progress.save()

    departments = Department.objects.all().order_by("name")
    programs = Program.objects.select_related("department").order_by("name")

    # --- SAVE PROGRAM SELECTION ---
    if request.method == "POST" and request.POST.get("select_program"):
        program_id = request.POST.get("program_id")

        if not program_id:
            messages.error(request, "Please select a program.")
            return redirect("registration_step_2")

        program = Program.objects.filter(id=program_id).first()
        if not program:
            messages.error(request, "Invalid program selected.")
            return redirect("registration_step_2")

        # Save program + mark step completed
        progress.program = program
        progress.step2_completed = True

        # New program means new semester should be auto-set (you already do this earlier)
        # No changes to semester logic here.

        progress.save()

        return redirect("registration_step_3")

    return render(request, "users/dashboard/contents/student/registration_step2.html", {
        "departments": departments,
        "programs": programs,
        "progress": progress
    })


@login_required
def registration_step_3(request):
    user = request.user

    if user.role != "student":
        return registration_error(request, "Access denied.")

    progress = RegistrationProgress.objects.filter(student=user).first()

    # Must complete Step 2
    if not progress or not progress.step2_completed:
        return registration_error(request, "You must complete Step 2 first.")

    # If returning from Step 4 → reset Step 4 only
    if progress.step4_completed:
        progress.step4_completed = False
        progress.is_submitted = False
        progress.save()

    program = progress.program
    semester = progress.semester

    if not program:
        return registration_error(request, "Program selection missing.")

    if not semester:
        return registration_error(request, "No active semester found.")

    # Load courses
    courses = Course.objects.filter(
        program=program,
        semester=semester
    ).order_by("code")

    if not courses.exists():
        return registration_error(request, "No courses available. Contact admin.")

    # COURSE SELECTION SUBMIT
    if request.method == "POST" and request.POST.get("select_courses"):
        selected_ids = request.POST.getlist("course_ids")

        if not selected_ids:
            return registration_error(request, "Select at least one course.")

        # Store selection temporarily
        request.session["selected_courses"] = selected_ids

        progress.step3_completed = True
        progress.save()

        return redirect("registration_step_4")

    return render(request, "users/dashboard/contents/student/registration_step3.html", {
        "courses": courses,
        "progress": progress,
        "program": program,      
        "semester": semester,
    })


# @login_required
# def registration_step_4(request):
#     user = request.user
#     if user.role != "student":
#         return registration_error(request, "Access denied.")

#     progress = RegistrationProgress.objects.filter(student=user).first()
#     if not progress or not progress.step3_completed:
#         return registration_error(request, "Complete Step 3 first.")

#     if progress.is_submitted:
#         return redirect("registration_complete")

#     selected_ids = request.session.get("selected_courses", [])
#     if not selected_ids:
#         return registration_error(request, "Your session expired. Redo Step 3.")

#     program = progress.program
#     semester = progress.semester

#     selected_courses = Course.objects.filter(id__in=selected_ids)

#     if request.method == "POST" and request.POST.get("final_submit"):
#         try:
#             with transaction.atomic():
#                 registration, created = StudentRegistration.objects.get_or_create(
#                     student=user,
#                     academic_year=progress.academic_year,
#                     semester=progress.semester,
#                     defaults={"program": progress.program}
#                 )

#                 registration.courses.set(selected_ids)
#                 registration.save()

#                 progress.step4_completed = True
#                 progress.is_submitted = True
#                 progress.save()

#                 request.session.pop("selected_courses", None)

#         except Exception as e:
#             return registration_error(
#                 request,
#                 f"Registration failed. Error: {e}"
#             )

#         return redirect("registration_complete")

#     return render(request, "users/dashboard/contents/student/registration_step4.html", {
#         "selected_courses": selected_courses,
#         "progress": progress,
#         "program": program,          # <-- FIXED
#         "semester": semester,        # <-- FIXED
#     })


@login_required
def registration_step_4(request):
    user = request.user

    if user.role != "student":
        return registration_error(request, "Access denied.")

    progress = RegistrationProgress.objects.filter(student=user).first()
    if not progress or not progress.step3_completed:
        return registration_error(request, "Complete Step 3 first.")

    # If already submitted → skip ahead
    if progress.is_submitted:
        return redirect("registration_complete")

    selected_ids = request.session.get("selected_courses", [])
    if not selected_ids:
        return registration_error(request, "Your session expired. Redo Step 3.")

    program = progress.program
    semester = progress.semester

    selected_courses = Course.objects.filter(id__in=selected_ids)

    # ----------------------------
    # FINAL SUBMISSION
    # ----------------------------
    if request.method == "POST" and request.POST.get("final_submit"):

        try:
            with transaction.atomic():

                registration, created = StudentRegistration.objects.get_or_create(
                    student=user,
                    academic_year=progress.academic_year,
                    semester=progress.semester,
                    defaults={"program": progress.program}
                )

                # Save course selection
                registration.courses.set(selected_ids)
                registration.save()

                # Save progress
                progress.step4_completed = True
                progress.is_submitted = True
                progress.save()

                # Clear session
                request.session.pop("selected_courses", None)

                # 🔥 LOG SUCCESS
                log_event(
                    user,
                    "registration",
                    f"Student completed registration for {semester.name} ({semester.academic_year.name}). "
                    f"Courses registered: {', '.join([c.code for c in selected_courses])}"
                )

        except Exception as e:
            # 🔥 LOG FAILURE
            log_event(
                user,
                "registration",
                f"Registration failed due to system error: {str(e)}",
                meta=f"user_id={user.id}"
            )

            return registration_error(
                request,
                f"Registration failed. Error: {e}"
            )

        return redirect("registration_complete")

    return render(
        request,
        "users/dashboard/contents/student/registration_step4.html",
        {
            "selected_courses": selected_courses,
            "progress": progress,
            "program": program,
            "semester": semester,
        }
    )



@login_required
def registration_complete(request):
    user = request.user
    if user.role != "student":
        return registration_error(request, "Access denied.")

    progress = RegistrationProgress.objects.filter(student=user).first()
    if not progress or not progress.is_submitted:
        return registration_error(request, "Registration not completed.")

    registration = StudentRegistration.objects.filter(
        student=user,
        academic_year=progress.academic_year,
        semester=progress.semester,
    ).first()

    if not registration:
        return registration_error(
            request,
            "Registration record missing. Contact admin."
        )

    return render(request, "users/dashboard/contents/student/registration_complete.html", {
        "student": user,
        "progress": progress,
        "program": registration.program,
        "semester": registration.semester,
        "selected_courses": registration.courses.all(),
        "is_registration_open": registration.semester.sem_reg_is_active,
    })


@login_required
def student_academics(request):
    user = request.user

    if user.role != "student":
        messages.error(request, "Access denied.")
        return redirect("home")

    # Fetch all assessments for student
    assessments = (
        Assessment.objects
        .filter(student=user)
        .select_related('course', 'semester', 'semester__academic_year')
        .order_by('semester__start_date')
    )

    if not assessments.exists():
        return render(
            request,
            "users/dashboard/contents/student/student_academics.html",
            {"semesters": {}, "cgpa": None}
        )

    # ----------------------------------------------------------
    # LOAD ALL GRADES FROM DB
    # ----------------------------------------------------------
    grade_rules = Grade.objects.order_by("-min_score")  # highest ranges first

    def get_grade_points(score_value):
        """
        Match score to grade rule (e.g. 75 falls into B+ range).
        Returns GPA points based on letter using official formulas or custom mapping.
        """

        score_value = Decimal(score_value)

        for rule in grade_rules:
            if rule.min_score <= score_value <= rule.max_score:
                letter = rule.letter.upper()

                # GPA conversion (can be updated anytime)
                point_map = {
                    "A": 4.0, "A-": 3.7,
                    "B+": 3.5, "B": 3.0, "B-": 2.7,
                    "C+": 2.5, "C": 2.0,
                    "D+": 1.5, "D": 1.0,
                    "F": 0.0,
                }

                return point_map.get(letter, 0.0)

        # No grade rule matched
        return 0.0

    # ----------------------------------------------------------
    # GROUP BY SEMESTER
    # ----------------------------------------------------------
    semester_groups = {}

    for a in assessments:
        sem_key = a.semester.id

        if sem_key not in semester_groups:
            semester_groups[sem_key] = {
                "semester": a.semester,
                "courses": [],
                "gpa": None,
            }

        semester_groups[sem_key]["courses"].append(a)

    # ----------------------------------------------------------
    # CALCULATE SEMESTER GPA
    # ----------------------------------------------------------
    for sem_id, data in semester_groups.items():
        total_points = Decimal("0")
        total_credits = Decimal("0")

        for a in data["courses"]:
            score = a.score
            grade_points = get_grade_points(score)

            credits = a.course.credit_hours or 3

            total_points += Decimal(str(grade_points)) * Decimal(credits)
            total_credits += Decimal(credits)

        data["gpa"] = (
            round(total_points / total_credits, 2)
            if total_credits > 0 else None
        )

    # ----------------------------------------------------------
    # CALCULATE CUMULATIVE GPA (CGPA)
    # ----------------------------------------------------------
    total_points = Decimal("0")
    total_credits = Decimal("0")

    for data in semester_groups.values():
        for a in data["courses"]:
            score = a.score
            grade_points = get_grade_points(score)
            credits = a.course.credit_hours or 3

            total_points += Decimal(str(grade_points)) * Decimal(credits)
            total_credits += Decimal(credits)

    cgpa = round(total_points / total_credits, 2) if total_credits else None

    # ----------------------------------------------------------
    # SORT SEMESTERS (latest first)
    # ----------------------------------------------------------
    sorted_semesters = dict(
        sorted(
            semester_groups.items(),
            key=lambda x: x[1]["semester"].start_date,
            reverse=True
        )
    )

    # ----------------------------------------------------------
    # RETURN UI
    # ----------------------------------------------------------
    return render(
        request,
        "users/dashboard/contents/student/student_academics.html",
        {
            "semesters": sorted_semesters,
            "cgpa": cgpa,
        }
    )


# @login_required
# def lecturer_assessments(request):
#     # Only lecturers allowed
#     if getattr(request.user, "role", None) != "lecturer":
#         messages.error(request, "Access denied.")
#         return redirect("home")

#     user = request.user

#     # Load ONLY active semesters
#     semesters = Semester.objects.filter(is_active=True).select_related(
#         "academic_year"
#     ).order_by("-start_date")

#     # Semester filter
#     semester_id = request.GET.get("semester_id")
#     selected_semester = Semester.objects.filter(id=semester_id).first() if semester_id else None

#     # Base course query
#     base_qs = (
#         Course.objects.filter(assigned_lecturers=user)
#         .select_related("program", "semester", "department")
#         .order_by("program__name", "code")
#     )

#     # Filter by semester
#     if selected_semester:
#         base_qs = base_qs.filter(semester=selected_semester)

#     # ---------------------------------------
#     # SEARCH FILTER
#     # ---------------------------------------
#     search = request.GET.get("search", "").strip()
#     if search:
#         base_qs = base_qs.filter(
#             Q(code__icontains=search) |
#             Q(title__icontains=search) |
#             Q(program__name__icontains=search)
#         )

#     # Pagination (10 items per page)
#     paginator = Paginator(base_qs, 10)
#     page_obj = paginator.get_page(request.GET.get("page"))
#     courses = list(page_obj)

#     # ---------------------------------------
#     # SAFE Python-side student counting
#     # ---------------------------------------
#     program_sem_pairs = [
#         (c.program_id, c.semester_id)
#         for c in courses
#         if c.semester_id
#     ]

#     regs = StudentRegistration.objects.filter(
#         program_id__in=[p for p, s in program_sem_pairs],
#         semester_id__in=[s for p, s in program_sem_pairs]
#     ).values_list("program_id", "semester_id")

#     student_map = {}
#     for prog, sem in regs:
#         key = (prog, sem)
#         student_map[key] = student_map.get(key, 0) + 1

#     for c in courses:
#         c.student_count = student_map.get((c.program_id, c.semester_id), 0)

#     return render(
#         request,
#         "users/dashboard/contents/lecturer/lecturer_assessments.html",
#         {
#             "courses": courses,
#             "semesters": semesters,
#             "selected_semester": selected_semester,
#             "page_obj": page_obj,
#             "search": search,
#         }
#     )

@login_required
def lecturer_assessments(request):
    # ----------------------------------------------
    # ACCESS CONTROL
    # ----------------------------------------------
    if getattr(request.user, "role", None) != "lecturer":
        log_event(request.user, "auth", "Unauthorized access attempt to lecturer assessments page")
        messages.error(request, "Access denied.")
        return redirect("home")

    user = request.user

    # Log initial page visit
    log_event(user, "assessment", "Opened lecturer assessments page")

    # ----------------------------------------------
    # LOAD ACTIVE SEMESTERS
    # ----------------------------------------------
    semesters = (
        Semester.objects.filter(is_active=True)
        .select_related("academic_year")
        .order_by("-start_date")
    )

    # ----------------------------------------------
    # HANDLE FILTERS
    # ----------------------------------------------
    semester_id = request.GET.get("semester_id")
    search = request.GET.get("search", "").strip()

    selected_semester = None
    if semester_id:
        selected_semester = Semester.objects.filter(id=semester_id).first()
        log_event(user, "assessment", f"Filter applied → Semester: {selected_semester}")

    if search:
        log_event(user, "assessment", f"Search performed → Query: '{search}'")

    # ----------------------------------------------
    # BASE COURSE QUERY
    # ----------------------------------------------
    base_qs = (
        Course.objects.filter(assigned_lecturers=user)
        .select_related("program", "semester", "department")
        .order_by("program__name", "code")
    )

    # Filter by semester
    if selected_semester:
        base_qs = base_qs.filter(semester=selected_semester)

    # Search filter
    if search:
        base_qs = base_qs.filter(
            Q(code__icontains=search)
            | Q(title__icontains=search)
            | Q(program__name__icontains=search)
        )

    # ----------------------------------------------
    # PAGINATION
    # ----------------------------------------------
    paginator = Paginator(base_qs, 10)
    page_number = request.GET.get("page")

    if page_number:
        log_event(user, "assessment", f"Visited assessments page → Page number: {page_number}")

    page_obj = paginator.get_page(page_number)
    courses = list(page_obj)

    # ----------------------------------------------
    # SAFE STUDENT COUNT (Python-side)
    # ----------------------------------------------
    program_sem_pairs = [(c.program_id, c.semester_id) for c in courses if c.semester_id]

    regs = StudentRegistration.objects.filter(
        program_id__in=[p for p, s in program_sem_pairs],
        semester_id__in=[s for p, s in program_sem_pairs]
    ).values_list("program_id", "semester_id")

    student_map = {}
    for prog, sem in regs:
        key = (prog, sem)
        student_map[key] = student_map.get(key, 0) + 1

    for c in courses:
        c.student_count = student_map.get((c.program_id, c.semester_id), 0)

    # ----------------------------------------------
    # RENDER PAGE
    # ----------------------------------------------
    return render(
        request,
        "users/dashboard/contents/lecturer/lecturer_assessments.html",
        {
            "courses": courses,
            "semesters": semesters,
            "selected_semester": selected_semester,
            "page_obj": page_obj,
            "search": search,
        }
    )


def get_letter_grade(score):
    from .models import Grade
    grade_obj = Grade.objects.filter(min_score__lte=score, max_score__gte=score).first()
    return grade_obj.letter if grade_obj else "N/A"


@login_required
def lecturer_enter_assessments(request, course_id, semester_id):
    user = request.user

    # Ensure lecturer
    if getattr(user, "role", None) != "lecturer":
        messages.error(request, "Access denied.")
        return redirect("home")

    # Validate course ownership
    course = get_object_or_404(
        Course.objects.select_related("program", "semester"),
        id=course_id,
        assigned_lecturers=user
    )

    semester = get_object_or_404(Semester, id=semester_id)

    # Students registered for this course in this semester
    registrations = StudentRegistration.objects.filter(
        program=course.program,
        semester=semester,
        courses=course
    ).select_related("student")

    students = [reg.student for reg in registrations]

    # Existing assessments → dict keyed by student_id
    existing = {
        a.student_id: a
        for a in Assessment.objects.filter(course=course, semester=semester)
    }

    # ================
    #  GRADE MAPPING
    # ================
    def get_letter_grade(score):
        grade_obj = Grade.objects.filter(
            min_score__lte=score,
            max_score__gte=score
        ).first()
        return grade_obj.letter if grade_obj else "N/A"

    # ===========================
    #  SAVE ASSESSMENTS (POST)
    # ===========================
    if request.method == "POST":
        for stu in students:
            raw_score = request.POST.get(f"score_{stu.id}")

            if raw_score:
                try:
                    score = float(raw_score)
                except ValueError:
                    continue

                grade = get_letter_grade(score)

                if stu.id in existing:
                    # UPDATE
                    a = existing[stu.id]
                    a.score = score
                    a.grade = grade
                    a.recorded_by = user
                    a.save()
                else:
                    # CREATE
                    Assessment.objects.create(
                        student=stu,
                        course=course,
                        program=course.program,
                        semester=semester,
                        score=score,
                        grade=grade,
                        recorded_by=user
                    )

        messages.success(request, "Assessments saved successfully!")
        return redirect("lecturer_enter_assessments", course_id, semester_id)

    # ===========================
    #  FETCH RECORDS FOR DISPLAY
    # ===========================
    records = {
        a.student_id: a
        for a in Assessment.objects.filter(course=course, semester=semester)
    }

    # Attach assessment object to each student (for template)
    for stu in students:
        stu.assessment = records.get(stu.id)

    # ===========================
    #  RENDER TEMPLATE
    # ===========================
    return render(
        request,
        "users/dashboard/contents/lecturer/lecturer_enter_assessments.html",
        {
            "course": course,
            "semester": semester,
            "students": students,
        }
    )

# @login_required
# def student_manage_courses(request):
#     user = request.user
#     if user.role != "student":
#         messages.error(request, "Access denied.")
#         return redirect("home")

#     # Get latest registration
#     registration = (
#         StudentRegistration.objects
#         .filter(student=user)
#         .order_by("-submitted_at")
#         .first()
#     )

#     if not registration:
#         return registration_error(request, "You have not completed registration yet.")

#     semester = registration.semester

#     # 🔥 Block if course registration is locked
#     if not semester.sem_reg_is_active:
#         return registration_error(
#             request,
#             "Course registration is currently closed. Please contact the administrator."
#         )

#     program = registration.program

#     available_courses = Course.objects.filter(
#         program=program,
#         semester=semester
#     ).order_by("code")

#     registered_ids = set(registration.courses.values_list("id", flat=True))

#     # -------------------------
#     # PROCESS ADD / REMOVE
#     # -------------------------
#     if request.method == "POST":

#         # Protect even more: block POST if admin turned off registration mid-session
#         if not semester.sem_reg_is_active:
#             return registration_error(
#                 request,
#                 "Registration is now closed. Your request could not be processed."
#             )

#         course_id = request.POST.get("course_id")
#         action = request.POST.get("action")

#         if not course_id:
#             return registration_error(request, "Invalid course selection.")

#         try:
#             course = Course.objects.get(
#                 id=course_id,
#                 program=program,
#                 semester=semester
#             )
#         except Course.DoesNotExist:
#             return registration_error(request, "Course not found.")

#         # ADD
#         if action == "add":
#             registration.courses.add(course)
#             registration.save()
#             messages.success(request, f"{course.code} added successfully.")

#         # REMOVE
#         elif action == "remove":
#             registration.courses.remove(course)
#             registration.save()
#             messages.warning(request, f"{course.code} removed successfully.")

#         return redirect("student_manage_courses")

#     return render(
#         request,
#         "users/dashboard/contents/student/manage_courses.html",
#         {
#             "registration": registration,
#             "available_courses": available_courses,
#             "registered_ids": registered_ids,
#             "program": program,
#             "semester": semester,
#         }
#     )

@login_required
def student_manage_courses(request):
    user = request.user

    # Unauthorized access
    if user.role != "student":
        log_event(user, "auth", "Unauthorized attempt to access manage courses")
        messages.error(request, "Access denied.")
        return redirect("home")

    # Load latest registration
    registration = (
        StudentRegistration.objects
        .filter(student=user)
        .order_by("-submitted_at")
        .first()
    )

    if not registration:
        log_event(user, "registration", "Tried to manage courses without valid registration")
        return registration_error(request, "You have not completed registration yet.")

    semester = registration.semester

    # 🔥 Registration closed
    if not semester.sem_reg_is_active:
        log_event(
            user,
            "registration",
            f"Attempted course changes but registration window closed for semester {semester.name}"
        )
        return registration_error(
            request,
            "Course registration is currently closed. Please contact the administrator."
        )

    program = registration.program

    # List available courses
    available_courses = Course.objects.filter(
        program=program,
        semester=semester
    ).order_by("code")

    registered_ids = set(registration.courses.values_list("id", flat=True))

    # -------------------------------------------------------------------
    # PROCESS ADD / REMOVE
    # -------------------------------------------------------------------
    if request.method == "POST":

        # Extra safety: block POST if closed mid-session
        if not semester.sem_reg_is_active:
            log_event(
                user,
                "registration",
                f"POST blocked: registration closed mid-session for {semester.name}"
            )
            return registration_error(
                request,
                "Registration is now closed. Your request could not be processed."
            )

        course_id = request.POST.get("course_id")
        action = request.POST.get("action")

        if not course_id:
            log_event(user, "registration", "POST error: Missing course_id")
            return registration_error(request, "Invalid course selection.")

        # Validate course existence
        try:
            course = Course.objects.get(
                id=course_id,
                program=program,
                semester=semester
            )
        except Course.DoesNotExist:
            log_event(
                user,
                "registration",
                f"Tried to modify non-existing or unauthorized course (ID: {course_id})"
            )
            return registration_error(request, "Course not found.")

        # ADD action
        if action == "add":
            registration.courses.add(course)
            registration.save()

            log_event(
                user,
                "registration",
                f"Added course {course.code} - {course.title}"
            )

            messages.success(request, f"{course.code} added successfully.")

        # REMOVE action
        elif action == "remove":
            registration.courses.remove(course)
            registration.save()

            log_event(
                user,
                "registration",
                f"Removed course {course.code} - {course.title}"
            )

            messages.warning(request, f"{course.code} removed successfully.")

        else:
            log_event(
                user,
                "registration",
                f"Invalid action attempted: {action}"
            )
            return registration_error(request, "Invalid action.")

        return redirect("student_manage_courses")

    # -------------------------------------------------------------------
    # RENDER PAGE
    # -------------------------------------------------------------------
    return render(
        request,
        "users/dashboard/contents/student/manage_courses.html",
        {
            "registration": registration,
            "available_courses": available_courses,
            "registered_ids": registered_ids,
            "program": program,
            "semester": semester,
        }
    )