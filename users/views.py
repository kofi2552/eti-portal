from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from .models import CustomUser as User, Payment, RegistrationProgress, StudentRegistration
from academics.models import Program, Course, AcademicYear, Semester, Assessment, Grade, ProgramLevel, Enrollment
from academics.models import Department, Resource, TranscriptSettings, TranscriptRequest, ProgramCourse, AssessmentCategory, AssessmentType, AssessmentTask, AssessmentTaskScore
from portal.models import SystemLog
from school.models import School
from django.core.paginator import Paginator
from reportlab.lib.utils import ImageReader
from django.conf import settings
import os
import csv, io
import pandas as pd
from django.http import HttpResponse,JsonResponse
import random
import datetime
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
from portal.utils import generate_transcript_json  
from django.db import  IntegrityError
from portal.models import SystemLock, Announcement
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from academics.services.assessment_tasks import create_task_with_scores
from academics.services.assessment_aggregation import recalculate_student_assessment
from decimal import ROUND_HALF_UP
from finance.models import ProgramFee
from academics.models import CourseAnnouncement


# Example assumes your User model has a 'role' field with values:
# "student", "lecturer", "dean", or "admin"

def system_is_locked():
    lock = SystemLock.objects.first()
    return lock.is_locked if lock else False


def generate_student_id():
    # Example: STU + year + random digits
    from datetime import datetime
    year = datetime.now().year % 100
    random_part = get_random_string(4, allowed_chars='0123456789')
    return f"STU{year}{random_part}"


def generate_pin():
    return get_random_string(6, allowed_chars='0123456789')


def get_student_active_semester(student):
    return (
        Enrollment.objects
        .filter(student=student, is_current=True)
        .select_related("semester")
        .first()
    )


def student_login(request):
    # ALWAYS define announcements first
    student_announcements = Announcement.objects.filter(
        role__in=["dean"],
        is_active=True
    ).order_by("-created_at")[:5]

    # Check lock BEFORE processing login
    if system_is_locked():
        messages.error(request, "The system is currently locked. Please try again later.")
        return render(request, "users/student_login.html", {
            "announcements": student_announcements
        })

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None and user.role == "student":
            login(request, user)
            log_event(user, "auth", f"Student login successful ({username})")
            return redirect("student_main")

        log_event(None, "auth", f"Failed student login attempt ({username})")
        messages.error(request, "Invalid student credentials.")

    return render(request, "users/student_login.html", {
        "announcements": student_announcements
    })


    # return render(request, "users/student_login.html")


def lecturer_login(request):
    if system_is_locked():
        messages.error(request, "The system is currently locked. Please try again later.")
        return render(request, "users/lecturer_login.html")

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)

        if user is not None and user.role == "lecturer":
            login(request, user)
            log_event(user, "auth", f"Lecturer login successful ({email})")
            return redirect("lecturer_main")

        log_event(None, "auth", f"Failed lecturer login attempt ({email})")
        messages.error(request, "Invalid lecturer credentials.")

    return render(request, "users/lecturer_login.html")


def dean_login(request):
    if system_is_locked():
        messages.error(request, "The system is currently locked. Please try again later.")
        return render(request, "users/dean_login.html")

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)

        if user is not None and user.role == "dean":
            login(request, user)
            log_event(user, "auth", f"Dean login successful ({email})")
            return redirect("dean_main")

        log_event(None, "auth", f"Failed dean login attempt ({email})")
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


# MAIN STUDENT DASHBOARD -----------------------------------------------------------------student

@login_required
def student_profile(request):
    user = request.user

    if user.role != "student":
        messages.error(request, "Access denied.")
        return redirect("home")

    active_year = AcademicYear.objects.filter(is_active=True).first()
    active_semester = Semester.objects.filter(is_active=True, level=user.level).first()

    return render(request, "users/dashboard/contents/student/student_profile.html", {
        "user": user,
        "active_year": active_year,
        "active_semester": active_semester,
    })


@login_required
def student_main(request):
    user = request.user

    if user.role != "student":
        messages.error(request, "Access denied.")
        return redirect("home")

    # ---------------------------
    # Active academic year
    # ---------------------------
    active_year = AcademicYear.objects.filter(is_active=True).first()

    # ---------------------------
    # Student's current level
    # ---------------------------
    current_level = getattr(user, "level", None)

    # ---------------------------
    # Active semester for this level
    # ---------------------------
    active_semester = None
    if active_year and current_level:
        active_semester = Semester.objects.filter(
            academic_year=active_year,
            level=current_level,
            is_active=True
        ).first()

    # ---------------------------
    # ENROLLMENT CHECK (single source of truth)
    # ---------------------------
    enrollment = None
    if active_semester and current_level:
        enrollment = Enrollment.objects.filter(
            student=user,
            level=current_level,
            semester=active_semester,
            is_current=True
        ).first()

    registered = enrollment is not None

    registered_semester_name = (
        active_semester.name if registered else "No registration"
    )

    # ---------------------------
    # ENROLLED COURSES
    # ---------------------------
    if registered:
        reg = StudentRegistration.objects.filter(
            student=user,
            academic_year=active_year,
            semester=active_semester
        ).first()
        enrolled_courses = reg.courses.count() if reg else 0
    else:
        enrolled_courses = 0

    # ---------------------------
    # GPA + TOTAL CREDITS (ALL-TIME)
    # ---------------------------
    grade_point_map = {
        "A": 4.0, "A-": 3.7,
        "B+": 3.5, "B": 3.0, "B-": 2.7,
        "C+": 2.5, "C": 2.0,
        "D+": 1.5, "D": 1.0,
        "F": 0.0
    }

    assessments = (
        Assessment.objects
        .filter(student=user)
        .select_related("course")
    )

    total_points = 0
    total_credits = 0

    for a in assessments:
        points = grade_point_map.get(a.grade, 0)
        credits = getattr(a.course, "credit_hours", 3)
        total_points += points * credits
        total_credits += credits

    current_gpa = round(total_points / total_credits, 2) if total_credits else None

    # ---------------------------
    # FEE BALANCE (ACTIVE SEMESTER)
    # ---------------------------
    fee_aggregation = Payment.objects.filter(
        student=user,
        is_verified=True
    ).aggregate(
        total_balance=Sum(
            ExpressionWrapper(
                F("amount_expected") - F("amount_paid"),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        )
    )

    fee_balance = fee_aggregation["total_balance"] or 0

    # ---------------------------
    # GRAPH DATA (UNCHANGED)
    # ---------------------------
    graph_semesters = (
        Semester.objects.filter(
            id__in=Assessment.objects.filter(student=user)
            .values_list("semester_id", flat=True)
        )
        .select_related("academic_year")
        .order_by("start_date")
    )

    selected_sem_id = request.GET.get("semester")
    if selected_sem_id:
        selected_graph_semester = graph_semesters.filter(id=selected_sem_id).first()
    else:
        selected_graph_semester = graph_semesters.last() if graph_semesters else None
        selected_sem_id = selected_graph_semester.id if selected_graph_semester else None

    course_labels = []
    grade_points = []

    if selected_graph_semester:
        sem_assessments = (
            Assessment.objects
            .filter(student=user, semester=selected_graph_semester)
            .select_related("course")
            .order_by("course__course_code")
        )

        for a in sem_assessments:
            code = getattr(a.course, "course_code", "") or getattr(a.course, "code", "")
            course_labels.append(code)
            grade_points.append(grade_point_map.get(a.grade, 0))

    # ---------------------------
    # FINAL CONTEXT
    # ---------------------------
    return render(
        request,
        "users/dashboard/contents/student/student_main.html",
        {
            # React-style stats
            "current_gpa": current_gpa,
            "total_credits": total_credits,
            "max_credits": 120,  # optional / program-based later
            "fee_balance": fee_balance,

            # Existing tiles
            "enrolled_courses": enrolled_courses,
            "semester_number": registered_semester_name,
            "level": current_level,

            # Graph data
            "graph_semesters": graph_semesters,
            "selected_sem_id": selected_sem_id,
            "course_labels": json.dumps(course_labels),
            "grade_points": json.dumps(grade_points),
        }
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
        registration.courses.select_related("program", "semester", "level"),
        id=course_id
    )

    lecturers = course.assigned_lecturers.all()

    # fetch resources for this course
    resources = (
        Resource.objects
        .filter(course=course)
        .select_related("lecturer", "semester")
        .order_by("-created_at")
    )

    # ✅ FETCH ANNOUNCEMENTS FOR THIS PROGRAM COURSE
    announce = (
        CourseAnnouncement.objects
        .filter(
            course=course,
        )
        .select_related("sender")
        .order_by("-created_at")
        
    )


    return render(request,
        "users/dashboard/contents/student/student_course_details.html",
        {
            "course": course,
            "resources": resources,
            "lecturers": lecturers,
            "registration": registration,
            "announce": announce,
        }
    )


@login_required
def register_semester(request):
    return render(request, "users/dashboard/contents/student/register_semester.html")



@login_required
def course_detail(request, course_id):
    """
    Course details + resource CRUD (create on same page).
    Only admin or assigned lecturer may add/delete resources.
    All users can view.
    """
    # print("course id: ", course_id)
    course = get_object_or_404(ProgramCourse.objects.select_related("program", "semester"), id=course_id)
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

            if not resource.semester and course.semester_id:
                resource.semester = course.semester

            resource.save()
            messages.success(request, "Resource added successfully.")
            return redirect("course_detail", course_id=course_id)
        else:
            print("FORM ERRORS:", form.errors)
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
def admin_manage_programs(request):
    return render(request, "users/dashboard/contents/admin/admin_manage_programs.html")


@login_required
def admin_reports(request):
    return render(request, "users/dashboard/contents/admin/admin_reports.html")

# logout
def logout_view(request):
    logout(request)
    # messages.success(request, "You have been logged out successfully.")
    return redirect("portal:home")


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


@login_required
def ajax_get_program_levels(request, program_id):
    try:
        program = Program.objects.get(id=program_id)
        levels = ProgramLevel.objects.filter(program=program).order_by("order")

        data = [
            {"id": lvl.id, "name": lvl.level_name}
            for lvl in levels
        ]

        return JsonResponse({"levels": data}, status=200)

    except Program.DoesNotExist:
        return JsonResponse({"levels": []}, status=404)


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
        award_type = request.POST.get("award_type")
        duration_years = request.POST.get("duration_years")
        sem_per_level = request.POST.get("sems_per_level")

        # Validation
        if not (name and department_id and award_type and duration_years and sem_per_level):
            messages.error(request, "All fields are required.")
            return redirect("admin_manage_programs")

        department = get_object_or_404(Department, id=department_id)

        # Convert fields to correct types
        duration_years = int(duration_years)
        sem_per_level = int(sem_per_level)

        # Generate program code
        prefix = name[:3].upper()
        random_digits = ''.join([str(random.randint(0, 9)) for _ in range(5)])
        prog_code = f"{prefix}{random_digits}"

        Program.objects.create(
            name=name,
            description=description,
            department=department,
            code=prog_code,
            award_type=award_type,
            duration_years=duration_years,
            semesters_per_level=sem_per_level,
        )

        messages.success(request, f"Program '{name}' created successfully.")
        return redirect("admin_manage_programs")


    # UPDATE PROGRAM
    if request.method == "POST" and request.POST.get("update_program"):

        program_id = request.POST.get("program_id")
        program = get_object_or_404(Program, id=program_id)

        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        department_id = request.POST.get("department_id")
        award_type = request.POST.get("award_type")
        duration_years = request.POST.get("duration_years")
        sem_per_level = request.POST.get("sems_per_level")

        if name:
            program.name = name
        program.description = description

        if department_id:
            program.department = get_object_or_404(Department, id=department_id)

        # Assign updated values
        if award_type:
            program.award_type = award_type
        if duration_years:
            program.duration_years = int(duration_years)
        if sem_per_level:
            program.semesters_per_level = int(sem_per_level)

        program.save()

        messages.success(request, f"Program '{program.name}' updated successfully.")
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

    for p in programs:
        p.total_semesters = p.semesters_per_level * p.duration_years


    return render(request, "users/dashboard/contents/admin/admin_manage_programs.html", {
        "departments": departments,
        "programs": programs,
        "deans": deans
    })


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
    # MANAGE PROGRAM FEE RECORD
    # ============================
    if request.method == "POST" and request.POST.get("fee_id"):
        fee_id = request.POST.get("fee_id")
        program_fee = get_object_or_404(ProgramFee, id=fee_id)


        program_fee.is_allowed = not program_fee.is_allowed
        program_fee.save(update_fields=["is_allowed"])

        status = "enabled" if program_fee.is_allowed else "disabled"

        print("toggled: is_allowed")

        log_event(
            request.user,
            "Payments",
            f"Admin {status} finance editing for "
            f"Program: {program_fee.program.name} | "
            f"Semester: {program_fee.semester.name}"
        )

        messages.success(
            request,
            f"Program fee for {program_fee.program.name} "
            f"({program_fee.semester.name}) has been {status}."
        )

        return redirect("student_enrollment")
    
    # ============================
    # ARCHIVE PROGRAM FEE RECORD
    # ============================
    if request.method == "POST" and request.POST.get("delete_fee"):
        fee_id = request.POST.get("del_fee_id")
        program_fee = get_object_or_404(ProgramFee, id=fee_id)


        program_fee.is_archived = not program_fee.is_archived
        program_fee.save(update_fields=["is_archived"])

        status = "archived" if program_fee.is_archived else "unarchived"

        print("archived: is_archived")

        log_event(
            request.user,
            "Payments",
            f"Admin {status} fees for "
            f"Program: {program_fee.program.name} | "
            f"Semester: {program_fee.semester.name}"
        )

        messages.success(
            request,
            f"Program fee for {program_fee.program.name} "
            f"({program_fee.semester.name}) has been {status}."
        )

        return redirect("student_enrollment")


   # ============================
    # VERIFY PAYMENT
    # ============================
    if request.method == "POST" and request.POST.get("verify_payment"):
        payment_id = request.POST.get("payment_id")
        payment = get_object_or_404(Payment, id=payment_id)

        student = payment.student
        program = payment.program
        semester = payment.semester
        academic_year = payment.academic_year

        try:
            with transaction.atomic():

                # ---------------------------------
                # 0. Fetch Program Fee
                # ---------------------------------
                program_fee = ProgramFee.objects.filter(
                    program=program,
                    academic_year=academic_year,
                    semester=semester
                ).first()

                if not program_fee:
                    messages.error(
                        request,
                        "Program fee has not been declared for this program and semester."
                    )
                    return redirect("student_enrollment")

                # ---------------------------------
                # 1. Sum PREVIOUSLY VERIFIED payments
                # ---------------------------------
                previously_verified_total = (
                    Payment.objects.filter(
                        student=student,
                        program=program,
                        academic_year=academic_year,
                        semester=semester,
                        is_verified=True
                    )
                    .exclude(id=payment.id)  # safety
                    .aggregate(total=Sum("amount_paid"))["total"]
                    or Decimal("0")
                )

                # ---------------------------------
                # 2. Include CURRENT payment
                # ---------------------------------
                total_after_verification = (
                    previously_verified_total + payment.amount_paid
                )

                # ---------------------------------
                # 3. Enforce INITIAL PAYMENT RULE
                # ---------------------------------
                if total_after_verification < program_fee.initial_amount:
                    messages.error(
                        request,
                        f"Initial payment not met. "
                        f"Required: GHS {program_fee.initial_amount}, "
                        f"Paid after verification: GHS {total_after_verification}."
                    )
                    return redirect("student_enrollment")

                # ---------------------------------
                # 4. Mark payment as verified
                # ---------------------------------
                payment.is_verified = True
                payment.save()

                # ---------------------------------
                # 5. Get or create Enrollment
                # ---------------------------------
                enrollment, created = Enrollment.objects.get_or_create(
                    student=student,
                    semester=semester,
                    defaults={
                        "program": program,
                        "level": student.level,
                        "payment": payment,   
                        "is_current": True,
                    }
                )

                if not created:
                    enrollment.program = program
                    enrollment.level = student.level
                    enrollment.payment = payment
                    enrollment.is_current = True
                    enrollment.save()

                # Deactivate any other active enrollments
                Enrollment.objects.filter(
                    student=student,
                    is_current=True
                ).exclude(pk=enrollment.pk).update(is_current=False)

                # ---------------------------------
                # 6. Update student profile
                # ---------------------------------
                student.is_fee_paid = True
                student.program = program
                student.department = program.department
                student.level = enrollment.level

                # ---------------------------------
                # 7. Generate ID & PIN (first time)
                # ---------------------------------
                first_time = False

                if not student.student_id:
                    student.student_id = generate_student_id()
                    first_time = True

                if not student.pin_code:
                    student.pin_code = generate_pin()
                    first_time = True

                if first_time:
                    student.username = student.student_id
                    student.set_password(student.pin_code)

                student.save()

                # ---------------------------------
                # 8. Mirror credentials on payment
                # ---------------------------------
                payment.generated_student_id = student.student_id
                payment.generated_pin = student.pin_code
                payment.save()

                # ---------------------------------
                # LOG
                # ---------------------------------
                log_event(
                    request.user,
                    "registration",
                    f"Verified payment for {student.get_full_name()} | "
                    f"Program: {program.name} | "
                    f"Semester: {semester.name} | "
                    f"Total paid so far: GHS {total_after_verification}"
                )

            messages.success(
                request,
                f"Payment verified successfully for {student.get_full_name()}."
            )

        except Exception as e:
            messages.error(request, f"Verification failed: {e}")

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

        # -------------------------------------------------
        # BLOCK activation if no ProgramCourses exist
        # -------------------------------------------------
        if not semester.sem_reg_is_active:
            has_courses = ProgramCourse.objects.filter(
                semester=semester,
                is_active=True
            ).exists()

            if not has_courses:
                log_event(
                    request.user,
                    "registration",
                    f"Blocked semester activation: {semester.name} has no program courses"
                )

                messages.error(
                    request,
                    f"Cannot activate registration for {semester.name}. "
                    "No courses have been configured for this semester."
                )
                return redirect("student_enrollment")

    # -------------------------------------------------
    # Toggle state
    # -------------------------------------------------
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
        "payments": payments_page,     
        "search_query": search_query, 
        "students": User.objects.filter(role="student"),
        "years": AcademicYear.objects.all(),
        "semesters": Semester.objects.all(),
        "programs": Program.objects.all(),
        "fees": ProgramFee.objects.all(),
        "levels": ProgramLevel.objects.all(),
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
    # HEADER (SCHOOL BRANDING)
    # ---------------------------------------------
    school = School.objects.first()

    header_top = height - 50

    # LOGO (LEFT)
    if school and school.logo:
        logo_path = os.path.join(settings.MEDIA_ROOT, school.logo.name)
        if os.path.exists(logo_path):
            p.drawImage(
                ImageReader(logo_path),
                50,
                header_top - 50,
                width=60,
                height=60,
                preserveAspectRatio=True,
                mask="auto"
            )

    # SCHOOL NAME
    p.setFont("Helvetica-Bold", 16)
    p.setFillColor(colors.HexColor("#1f2937"))  # slate-800
    p.drawCentredString(
        width / 2,
        header_top,
        school.name.upper() if school else "OFFICIAL"
    )

    # SCHOOL DETAILS
    p.setFont("Helvetica", 9)
    p.setFillColor(colors.HexColor("#6b7280"))  # gray-500

    details = []
    if school:
        if school.address:
            details.append(school.address)
        if school.phone:
            details.append(f"Tel: {school.phone}")
        if school.email:
            details.append(school.email)

    if details:
        p.drawCentredString(
            width / 2,
            header_top - 18,
            " | ".join(details)
        )

    # DIVIDER LINE (unchanged position)
    p.setStrokeColor(colors.HexColor("#e5e7eb"))
    p.setLineWidth(0.6)
    p.line(50, header_top - 35, width - 50, header_top - 35)

    # DOCUMENT TITLE — centered with breathing room
    p.setFont("Helvetica-Bold", 14)
    p.setFillColor(colors.HexColor("#111827"))
    title_y = header_top - 80   # controls TOP space
    p.drawCentredString(width / 2, title_y, "STUDENT PAYMENT RECORD")

    # 🔑 THIS LINE CREATES THE BOTTOM SPACE
    y = title_y - 40 

    # ---------------------------------------------
    # DATA TABLE CONFIG
    # ---------------------------------------------
    y = title_y - 40
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


@login_required
def toggle_program_fee_allowed(request, fee_id):
    if getattr(request.user, "role", None) not in ["admin", "superadmin"]:
        messages.error(request, "Access denied.")
        return redirect("semester_fee_list")

    program_fee = get_object_or_404(ProgramFee, id=fee_id)

    program_fee.is_allowed = not program_fee.is_allowed
    program_fee.save(update_fields=["is_allowed"])

    status = "enabled" if program_fee.is_allowed else "disabled"

    messages.success(
        request,
        f"Program fee for {program_fee.program.name} "
        f"({program_fee.semester.name}) has been {status}."
    )

    return redirect("semester_fee_list")


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



# -------------------------------------------------- DEAN MANAGE COURSES -----------------------------------------------------


def generate_course_code(title, department):
  
    # Take first two initials from title
    title_initials = "".join(word[0].upper() for word in title.split()[:2])  # FW
    
    # Department initials (can be more than one letter if you prefer)
    dept_initials = "".join(word[0].upper() for word in department.split())  # B or CS
    
    # Random number between 100–999 for flexibility
    number = random.randint(100, 999)
    
    return f"{title_initials}{dept_initials}{number}"


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


    # All courses under these programs
    courses = Course.objects.filter(program__in=programs) \
        .select_related('program', 'department') \
        .order_by('program__name', 'title')

    lecturers = User.objects.filter(role='lecturer').order_by('last_name', 'first_name')

    # ---------- CREATE COURSE ----------
    if request.method == "POST" and request.POST.get("create_course"):
        title = request.POST.get("title", "").strip()
        # code = request.POST.get("code", "").strip()
        description = request.POST.get("description", "").strip()
        credit_hours = request.POST.get("credit_hours", "").strip()

        try:
            credit_hours = int(credit_hours) if credit_hours else 3
        except ValueError:
            credit_hours = 3

        program_id = request.POST.get("program_id")
        lecturer_ids = request.POST.getlist("lecturer_ids")

        program = Program.objects.filter(id=program_id).first()

        # AUTO-GENERATE CODE
        code = generate_course_code(title, program.department.name)

        # Ensure uniqueness
        while Course.objects.filter(code=code).exists():
            code = generate_course_code(title, program.department.name)

        if not title or not code or not program_id:
            messages.error(request, "Program, course code, and title are required.")
            return redirect("manage_courses")


        
        if not program or program not in programs:
            messages.error(request, "Invalid program selected.")
            return redirect("manage_courses")

       
        if Course.objects.filter(code__iexact=code).exists():
            messages.error(request, "A course with this code already exists.")
            return redirect("manage_courses")

        course = Course.objects.create(
            program=program,
            department=program.department,
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
        lecturer_ids = request.POST.getlist("lecturer_ids")

        if not title or not code or not program_id:
            messages.error(request, "Program,  course code, and title are required.")
            return redirect("manage_courses")

        program = Program.objects.filter(id=program_id).first()
        if not program or program not in programs:
            messages.error(request, "Invalid program selected.")
            return redirect("manage_courses")

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
    })


@login_required
def ajax_get_program_course(request, pc_id):
    # Only dean or admin allowed
    if request.user.role not in ["dean", "admin"]:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    pc = get_object_or_404(ProgramCourse, id=pc_id)

    data = {
        "id": pc.id,
        "title": pc.title,
        "code": pc.course_code,
        "credit_hours": pc.credit_hours,
        "active": pc.is_active,
        "lecturer_ids": list(pc.assigned_lecturers.values_list("id", flat=True)),
    }

    return JsonResponse(data)


@login_required
def ajax_update_program_course(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    if request.user.role not in ["dean", "admin"]:
        return JsonResponse({"error": "Unauthorized"}, status=403)


    pc_id = request.POST.get("pc_id")
    pc_title = request.POST.get("pc_title").strip()
    pc_credit = request.POST.get("pc_credit").strip()
    pc_active = request.POST.get("is_active") == "true"
    lecturer_ids = request.POST.getlist("lecturers")  # multiple select

    if not pc_id:
        return JsonResponse({"error": "ProgramCourse ID missing"}, status=400)

    pc = get_object_or_404(ProgramCourse, id=pc_id)

    # Update lecturers
    try:
        pc.title = pc_title
        pc.is_active = pc_active
        pc.credit_hours = int(pc_credit)
        pc.assigned_lecturers.set(lecturer_ids)
        pc.save()
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"success": True})


@login_required
def dean_program_courses_list(request):
    if request.user.role not in ["dean", "admin"]:
        messages.error(request, "Access denied.")
        return redirect("home")

    q = request.GET.get("q", "").strip()
    program_id = request.GET.get("program_id")
    level_id = request.GET.get("level_id")
    semester_id = request.GET.get("semester_id")

    programs = Program.objects.all().order_by("name")
    levels = ProgramLevel.objects.select_related("program").order_by("program__name", "order")
    semesters = Semester.objects.all().order_by("academic_year__start_date", "name")

    queryset = ProgramCourse.objects.select_related(
        "program", "level", "semester"
    ).order_by("program__name", "level__order")

    # SEARCH
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q) |
            Q(course_code__icontains=q)
        )

    # FILTERS
    if program_id:
        queryset = queryset.filter(program_id=program_id)

    if level_id:
        queryset = queryset.filter(level_id=level_id)

    if semester_id:
        queryset = queryset.filter(semester_id=semester_id)

    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    lecturers = User.objects.filter(role="lecturer")

    default_courses = Course.objects.filter(program=None).order_by("title")

    return render(request, "users/dashboard/contents/dean/program_courses_list.html", {
        "q": q,
        "programs": programs,
        "levels": levels,
        "semesters": semesters,
        "selected_program": program_id,
        "selected_level": level_id,
        "selected_semester": semester_id,
        "page_obj": page_obj,
        "lecturers": lecturers,
        "default_courses": default_courses,
    })


@login_required
def ajax_program_levels_courses(request, program_id):
    program = get_object_or_404(Program, id=program_id)

    levels = ProgramLevel.objects.filter(program=program).order_by("order")

    # default courses belonging to this program
    base_courses = Course.objects.filter(program=program).order_by("title")

    return JsonResponse({
        "levels": [{"id": l.id, "name": l.level_name} for l in levels],
        "courses": [{"id": c.id, "title": c.title, "code": c.code} for c in base_courses],
    })


@login_required
def ajax_level_semesters(request, level_id):
    level = get_object_or_404(ProgramLevel, id=level_id)

    semesters = Semester.objects.filter(level=level).order_by("start_date")

    return JsonResponse({
        "semesters": [{"id": s.id, "name": s.name} for s in semesters]
    })


@login_required
def ajax_duplicate_program_course(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    program_id = request.POST.get("program_id")
    level_id = request.POST.get("level_id")
    semester_id = request.POST.get("semester_id")
    base_course_id = request.POST.get("base_course_id")

    # Validate required fields
    if not program_id or not level_id or not base_course_id or not semester_id:
        return JsonResponse({"error": "Missing required fields"}, status=400)

    program = get_object_or_404(Program, id=program_id)
    level = get_object_or_404(ProgramLevel, id=level_id)
    base_course = get_object_or_404(Course, id=base_course_id)

    semester = None
    if semester_id:
        semester = get_object_or_404(Semester, id=semester_id)

    # DUPLICATE CHECK
    exists = ProgramCourse.objects.filter(
        program=program,
        level=level,
        base_course=base_course
    ).exists()

    if exists:
        return JsonResponse({
            "exists": True,
            "message": (
                f"This course has already been duplicated into "
                f"{program.name} • {level.level_name}."
            )
        })


    # Generate code dynamically based on level
    code = ProgramCourse.generate_code_for(base_course.title, level)

    # Create ProgramCourse
    pc = ProgramCourse.objects.create(
        program=program,
        level=level,
        semester=semester,
        title=base_course.title,
        course_code=code,
        credit_hours=base_course.credit_hours,
        base_course=base_course, 
    )

    # Copy lecturers
    pc.assigned_lecturers.set(base_course.assigned_lecturers.all())

    return JsonResponse({
            "success": True,
            "message": "Course duplicated successfully",
            "pc_id": pc.id,
            "code": code,
        })


@login_required
def ajax_delete_program_course(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    if request.user.role not in ["dean", "admin"]:
        return JsonResponse({"error": "Not authorized"}, status=403)

    import json
    data = json.loads(request.body.decode("utf-8"))
    pc_id = data.get("id")

    pc = ProgramCourse.objects.filter(id=pc_id).first()
    if not pc:
        return JsonResponse({"error": "Course mapping not found"}, status=404)

    pc.delete()
    return JsonResponse({"success": True})


# -------------------------------------- END DEAN MANAGE COURSE --------------------------------------------------


@login_required
def admin_school_setup(request):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("portal:home")

    school = School.objects.first()
    grades = Grade.objects.order_by("-min_score")

    if not school:
        school = School.objects.create(name="Unnamed School")

    if request.method == "POST" and request.POST.get("update_school"):
        school.name = request.POST.get("name")
        school.motto = request.POST.get("motto")
        school.address = request.POST.get("address")
        school.email = request.POST.get("email")
        school.phone = request.POST.get("phone")
        school.website = request.POST.get("website")
        school.signee_name = request.POST.get("signee_name", "")

        if "logo" in request.FILES:
            school.logo = request.FILES["logo"]

        if "signature" in request.FILES:
            school.signature = request.FILES["signature"]

        school.save()

        messages.success(request, "School information updated successfully.")
        return redirect("admin_school_setup")
    
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
            return redirect("admin_school_setup")

        Grade.objects.create(
            letter=letter,
            min_score=min_score,
            max_score=max_score,
        )
        messages.success(request, "Grade added successfully.")
        return redirect("admin_school_setup")

    # UPDATE
    if request.method == "POST" and request.POST.get("update_grade"):
        grade_id = request.POST.get("grade_id")
        grade = get_object_or_404(Grade, id=grade_id)

        grade.letter = request.POST.get("letter").upper().strip()
        grade.min_score = request.POST.get("min_score")
        grade.max_score = request.POST.get("max_score")
        grade.save()

        messages.success(request, "Grade updated successfully.")
        return redirect("admin_school_setup")

    # DELETE
    if request.method == "POST" and request.POST.get("delete_grade"):
        grade_id = request.POST.get("grade_id")
        grade = get_object_or_404(Grade, id=grade_id)
        grade.delete()

        messages.success(request, "Grade deleted.")
        return redirect("admin_school_setup")
    
    # ============================
    # ASSESSMENT TYPE CRUD
    # ============================
    assessment_types = AssessmentType.objects.order_by("name")

    if request.method == "POST":

        # CREATE
        if request.POST.get("create_assessment_type"):
            AssessmentType.objects.create(
                name=request.POST.get("name"),
                description=request.POST.get("description", "")
            )
            messages.success(request, "Assessment type created.")
            return redirect("admin_grade_settings")

        # UPDATE
        if request.POST.get("update_assessment_type"):
            at = get_object_or_404(
                AssessmentType,
                id=request.POST.get("assessment_type_id")
            )
            at.name = request.POST.get("name")
            at.description = request.POST.get("description", "")
            at.save()

            messages.success(request, "Assessment type updated.")
            return redirect("admin_grade_settings")

        # DELETE
        if request.POST.get("delete_assessment_type"):
            at = get_object_or_404(
                AssessmentType,
                id=request.POST.get("assessment_type_id")
            )
            at.delete()

            messages.success(request, "Assessment type deleted.")
            return redirect("admin_grade_settings")

    return render(
        request,
        "users/dashboard/contents/admin/admin_school_setup.html",
        {
            "school": school, 
            "assessment_types": assessment_types,
            "grades": grades
         }
    )


@login_required
def admin_manage_semesters(request):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    programs = Program.objects.all().order_by("name")
    years = AcademicYear.objects.all().order_by("-start_date")

    # FILTER selected program + level (optional)
    program_id = request.GET.get("program")
    level_id = request.GET.get("level")

    selected_program = Program.objects.filter(id=program_id).first() if program_id else None
    selected_level = ProgramLevel.objects.filter(id=level_id).first() if level_id else None

    # Load levels for selected program
    levels = ProgramLevel.objects.filter(program=selected_program) if selected_program else []

    # Load semesters for selected level
    semesters = Semester.objects.filter(level=selected_level).order_by("start_date") if selected_level else []

    # ---------------------------------------------------------
    # CREATE SEMESTER
    # ---------------------------------------------------------
    if request.method == "POST" and request.POST.get("create_semester"):
        level_id = request.POST.get("level_id")
        year_id = request.POST.get("academic_year_id")

        level = get_object_or_404(ProgramLevel, id=level_id)
        year = get_object_or_404(AcademicYear, id=year_id)

        name = request.POST.get("name")
        start_date = request.POST.get("start_date") or None
        end_date = request.POST.get("end_date") or None

        Semester.objects.create(
            name=name,
            academic_year=year,
            level=level,
            start_date=start_date,
            end_date=end_date,
            is_active=False,
            sem_reg_is_active=False,
        )

        messages.success(request, "Semester created successfully.")
        return redirect(f"{request.path}?program={level.program.id}&level={level.id}")

    # ---------------------------------------------------------
    # UPDATE SEMESTER
    # ---------------------------------------------------------
    if request.method == "POST" and request.POST.get("update_semester"):
        sem_id = request.POST.get("semester_id")
        sem = get_object_or_404(Semester, id=sem_id)

        sem.name = request.POST.get("name")
        sem.start_date = request.POST.get("start_date") or None
        sem.end_date = request.POST.get("end_date") or None
        sem.is_active = request.POST.get("is_active") == "on"
        sem.sem_reg_is_active = request.POST.get("sem_reg_is_active") == "on"

        sem.save()

        messages.success(request, "Semester updated successfully.")
        return redirect(f"{request.path}?program={sem.level.program.id}&level={sem.level.id}")

    # ---------------------------------------------------------
    # DELETE SEMESTER
    # ---------------------------------------------------------
    if request.method == "POST" and request.POST.get("delete_semester"):
        sem_id = request.POST.get("semester_id")
        sem = get_object_or_404(Semester, id=sem_id)

        prog_id = sem.level.program.id
        level_id = sem.level.id

        sem.delete()

        messages.success(request, "Semester deleted.")
        return redirect(f"{request.path}?program={prog_id}&level={level_id}")

    return render(request, "users/dashboard/contents/admin/admin_manage_semesters.html", {
        "programs": programs,
        "levels": levels,
        "years": years,
        "selected_program": selected_program,
        "selected_level": selected_level,
        "semesters": semesters,
    })


@login_required
def admin_school(request):
    academic_years = AcademicYear.objects.order_by("-start_date")
    semesters = Semester.objects.select_related("academic_year").order_by("-start_date")

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
        
        # Enforce correct format e.g., 2024/2025
        # if len(name) != 16 or "/" not in name:
        #     messages.error(request, "Academic year name must be in the format YYYY/YYYY (e.g., 2024/2025).")
        #     return redirect("admin_school")

        AcademicYear.objects.create(
            name=name,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active,
            is_ready= False,
        )
        messages.success(request, "Academic year created successfully.")
        return redirect("admin_school")

    if request.method == "POST" and request.POST.get("update_academic_year"):
        year_id = request.POST.get("academic_year_id")
        year = get_object_or_404(AcademicYear, id=year_id)

        # Parse incoming values safely
        new_is_active = request.POST.get("is_active") == "on"
        new_is_ready  = request.POST.get("is_ready") == "on"

        # ============================
        # 1️⃣ Prevent: Active year → Ready
        # ============================
        if year.is_active and new_is_ready:
            messages.error(request,
                "You cannot set the ACTIVE academic year as 'Ready'. Select a non-active year instead."
            )
            return redirect("admin_school")

        # ============================
        # 2️⃣ Ensure only ONE year can be ready
        # ============================
        if new_is_ready:
            other_ready_year = AcademicYear.objects.exclude(id=year.id).filter(is_ready=True).first()
            if other_ready_year:
                messages.error(
                    request,
                    f"'{other_ready_year.name}' is already marked as READY. "
                    "Only one academic year can be ready at a time."
                )
                return redirect("admin_school")

        # ============================
        # 3️⃣ Ensure only ONE year can be active
        # ============================
        if new_is_active:
            other_active_year = AcademicYear.objects.exclude(id=year.id).filter(is_active=True).first()
            if other_active_year:
                messages.error(
                    request,
                    f"'{other_active_year.name}' is already ACTIVE. "
                    "Only one academic year can be active at a time."
                )
                return redirect("admin_school")

        # ============================
        # 4️⃣ Apply updates
        # ============================
        year.name = request.POST.get("name")
        year.start_date = request.POST.get("start_date")
        year.end_date = request.POST.get("end_date")
        year.is_active = new_is_active
        year.is_ready = new_is_ready
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

    programs = Program.objects.all().order_by("name")
    years = AcademicYear.objects.all().order_by("-start_date")

    # FILTER selected program + level (optional)
    program_id = request.GET.get("program")
    level_id = request.GET.get("level")

    selected_program = Program.objects.filter(id=program_id).first() if program_id else None
    selected_level = ProgramLevel.objects.filter(id=level_id).first() if level_id else None

    # Load levels for selected program
    levels = ProgramLevel.objects.filter(program=selected_program) if selected_program else []

    # Load semesters for selected level
    semesters = Semester.objects.filter(level=selected_level).order_by("start_date") if selected_level else []

    # ---------------------------------------------------------
    # CREATE SEMESTER
    # ---------------------------------------------------------
    if request.method == "POST" and request.POST.get("create_semester"):
        level_id = request.POST.get("level_id")
        year_id = request.POST.get("academic_year_id")

        level = get_object_or_404(ProgramLevel, id=level_id)
        year = get_object_or_404(AcademicYear, id=year_id)

        name = request.POST.get("name")
        start_date = request.POST.get("start_date") or None
        end_date = request.POST.get("end_date") or None

        Semester.objects.create(
            name=name,
            academic_year=year,
            level=level,
            start_date=start_date,
            end_date=end_date,
            is_active=False,
            sem_reg_is_active=False,
        )

        messages.success(request, "Semester created successfully.")
        return redirect(f"{request.path}?program={level.program.id}&level={level.id}")

    # ---------------------------------------------------------
    # UPDATE SEMESTER
    # ---------------------------------------------------------
    if request.method == "POST" and request.POST.get("update_semester"):
        sem_id = request.POST.get("semester_id")
        sem = get_object_or_404(Semester, id=sem_id)

        sem.name = request.POST.get("name")
        sem.start_date = request.POST.get("start_date") or None
        sem.end_date = request.POST.get("end_date") or None
        sem.is_active = request.POST.get("is_active") == "on"
        sem.sem_reg_is_active = request.POST.get("sem_reg_is_active") == "on"

        sem.save()

        messages.success(request, "Semester updated successfully.")
        return redirect(f"{request.path}?program={sem.level.program.id}&level={sem.level.id}")

    # ---------------------------------------------------------
    # DELETE SEMESTER
    # ---------------------------------------------------------
    if request.method == "POST" and request.POST.get("delete_semester"):
        sem_id = request.POST.get("semester_id")
        sem = get_object_or_404(Semester, id=sem_id)

        prog_id = sem.level.program.id
        level_id = sem.level.id

        sem.delete()

        messages.success(request, "Semester deleted.")
        return redirect(f"{request.path}?program={prog_id}&level={level_id}")


    

    # ----------------------------------------------------
    # RENDER PAGE
    # ----------------------------------------------------
    return render(request, "users/dashboard/contents/admin/admin_school.html", {
        "academic_years": academic_years,
        "programs": programs,
        "levels": levels,
        "years": years,
        "selected_program": selected_program,
        "selected_level": selected_level,
        "semesters": semesters,             
    })



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
    # SAFETY: Only reset when explicitly requested
    if request.GET.get("reset") == "1":
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

    # print("progress:", progress)

    # Must complete Step 2
    if not progress or not progress.step2_completed:
        return registration_error(request, "You must complete Step 2 first.")

    # If returning from Step 4 → reset Step 4 only
    if progress.step4_completed:
        progress.step4_completed = False
        progress.is_submitted = False
        progress.save()

    enrollment = get_student_active_semester(user)
    if not enrollment:
        return registration_error(request, "No active enrollment found.")

    program = user.program
    semester = enrollment.semester
    level = user.level
    active_semester = enrollment.semester

    # print("program: ", program)
    # print("sems: ", semester)
  
    # KEEP REGISTRATION SEMESTER IN SYNC
    if progress.semester != active_semester:
        progress.semester = active_semester
        progress.save()

    if not program:
        return registration_error(request, "Program selection missing.")

    if not semester:
        return registration_error(request, "No active semester found.")

    # Load courses
    courses = ProgramCourse.objects.filter(
        program=program,
        level=level,
        semester=active_semester,
        is_active=True,
    ).order_by("course_code")

    print("courses:", courses)

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
        "semester": active_semester,
        "level": level,
    })


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

    enrollment = get_student_active_semester(user)
    if not enrollment:
        return registration_error(request, "No active enrollment found.")

    active_semester = enrollment.semester
    program = user.program
    level = user.level

    # KEEP REGISTRATION SEMESTER UPDATED
    if progress.semester != active_semester:
        progress.semester = active_semester
        progress.save()

    selected_courses = ProgramCourse.objects.filter(id__in=selected_ids)

    # ----------------------------
    # FINAL SUBMISSION
    # ----------------------------
    if request.method == "POST" and request.POST.get("final_submit"):

        try:
            with transaction.atomic():

                registration, created = StudentRegistration.objects.get_or_create(
                    student=user,
                    academic_year=progress.academic_year,
                    semester=active_semester,
                    defaults={"program": progress.program}
                )

                # Save course selection
                registration.courses.set(selected_ids)
                registration.level = level
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
                    f"Student completed registration for {active_semester.name} ({active_semester.academic_year.name}). "
                    f"Courses registered: {', '.join([c.course_code for c in selected_courses])}"
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
            "semester": active_semester,
            "level": level,
        }
    )

 
@login_required
def registration_complete(request):
    user = request.user

    if user.role != "student":
        return registration_error(request, "Access denied.")

    # ---------------------------------------------
    # Load progress
    # ---------------------------------------------
    progress = RegistrationProgress.objects.filter(student=user).first()
    if not progress:
        return registration_error(request, "You have not started any registration.")

    # ---------------------------------------------
    # Active academic year
    # ---------------------------------------------
    active_year = AcademicYear.objects.filter(is_active=True).first()
    if not active_year:
        return registration_error(request, "No active academic year found.")

    # ---------------------------------------------
    # Old-year protection
    # ---------------------------------------------
    if progress.academic_year != active_year:
        return render(
            request,
            "users/dashboard/contents/student/registration_pending_new_year.html",
            {
                "student": user,
                "active_year": active_year,
            }
        )

    # ---------------------------------------------
    # Must be submitted
    # ---------------------------------------------
    if not progress.is_submitted:
        return registration_error(request, "Registration not completed.")

    # ---------------------------------------------
    # Active enrollment
    # ---------------------------------------------
    enrollment = get_student_active_semester(user)
    if not enrollment:
        return render(
            request,
            "users/dashboard/contents/student/registration_pending_payment.html",
            {
                "student": user,
                "active_year": active_year,
            }
        )

    semester = enrollment.semester

    # ---------------------------------------------
    # Registration record
    # ---------------------------------------------
    registration = StudentRegistration.objects.filter(
        student=user,
        academic_year=semester.academic_year,
        semester=semester
    ).first()

    if not registration:
        return render(
            request,
            "users/dashboard/contents/student/registration_not_done.html",
            {
                "student": user,
                "semester": semester,
                "active_year": active_year,
            }
        )

    # ---------------------------------------------
    # ✅ BUILD COURSE + LECTURER STRUCTURE
    # ---------------------------------------------
    courses_with_lecturers = []

    for pc in registration.courses.all():
        courses_with_lecturers.append({
            "course": pc,
            "lecturers": pc.assigned_lecturers.all(),
        })
    

    # ---------------------------------------------
    # FINAL RENDER
    # ---------------------------------------------
    return render(
        request,
        "users/dashboard/contents/student/registration_complete.html",
        {
            "student": user,
            "progress": progress,
            "program": registration.program,
            "semester": registration.semester,
            "selected_courses": courses_with_lecturers,
            "is_registration_open": registration.semester.sem_reg_is_active,
        }
    )



# -----------------------------
# Grade helpers
# -----------------------------
def resolve_letter_grade(percent, grade_rules):
    for rule in grade_rules:
        if rule.min_score <= percent <= rule.max_score:
            return rule.letter
    return "N/A"


def resolve_grade_points(letter):
    mapping = {
        "A": 4.0, "A-": 3.7,
        "B+": 3.5, "B": 3.0, "B-": 2.7,
        "C+": 2.5, "C": 2.0,
        "D+": 1.5, "D": 1.0,
        "F": 0.0,
    }
    return Decimal(str(mapping.get(letter.upper(), 0.0)))



@login_required
def student_academics(request):
    user = request.user

    if user.role != "student":
        messages.error(request, "Access denied.")
        return redirect("home")

    # -----------------------------------------
    # Academic year selection
    # -----------------------------------------
    all_years = AcademicYear.objects.all().order_by("-start_date")

    year_raw = request.GET.get("year")
    try:
        year_id = int(year_raw) if year_raw else None
    except (ValueError, TypeError):
        year_id = None

    selected_year = (
        all_years.filter(id=year_id).first()
        if year_id
        else AcademicYear.objects.filter(is_active=True).first()
    )

    selected_year_id = str(selected_year.id) if selected_year else None

    # -----------------------------------------
    # Grade rules
    # -----------------------------------------
    grade_rules = Grade.objects.order_by("-min_score")

    # -----------------------------------------
    # Fetch assessment category weights
    # -----------------------------------------
    categories = {
        c.system_role: c
        for c in AssessmentCategory.objects.all()
    }

    internal_weight = Decimal(str(categories["INTERNAL"].weight_percentage))
    external_weight = Decimal(str(categories["EXTERNAL"].weight_percentage))

    # -----------------------------------------
    # Fetch task scores
    # -----------------------------------------
    scores = (
        AssessmentTaskScore.objects
        .filter(
            student=user,
            task__semester__academic_year=selected_year,
            marks_obtained__isnull=False
        )
        .select_related(
            "task",
            "task__course",
            "task__semester",
            "task__assessment_category",
            "task__assessment_type",
        )
    )

    semesters = {}

    # -----------------------------------------
    # Group tasks
    # -----------------------------------------
    for s in scores:
        semester = s.task.semester
        course = s.task.course
        category = s.task.assessment_category.system_role

        sem_block = semesters.setdefault(semester.id, {
            "semester": semester,
            "courses": {},

            # RAW totals
            "internal_raw": Decimal("0"),
            "internal_max": Decimal("0"),
            "external_raw": Decimal("0"),
            "external_max": Decimal("0"),

            # WEIGHTED totals (displayed)
            "internal_total": Decimal("0"),
            "external_total": Decimal("0"),

            "overall_score": Decimal("0"),
            "overall_grade": None,
            "total_credits": Decimal("0"),
            "gpa": None,
        })

        course_block = sem_block["courses"].setdefault(course.id, {
            "course": course,
            "tasks": [],
            "course_total": Decimal("0"),
        })

        task_score = Decimal(str(s.marks_obtained))
        task_total = (
            Decimal(str(s.task.total_marks))
            .quantize(Decimal("0"), rounding=ROUND_HALF_UP)
        )

        percent = (task_score / task_total) * Decimal("100")
        task_grade = resolve_letter_grade(percent, grade_rules)

        course_block["tasks"].append({
            "title": s.task.title,
            "category": category,
            "type": s.task.assessment_type.name,
            "marks": task_score,
            "total": task_total,
            "grade": task_grade,
        })

        # Accumulate RAW totals for semester
        if category == "INTERNAL":
            sem_block["internal_raw"] += task_score
            sem_block["internal_max"] += task_total
        else:
            sem_block["external_raw"] += task_score
            sem_block["external_max"] += task_total

        # Course aggregation (for GPA)
        course_block["course_total"] += task_score

    # -----------------------------------------
    # GPA, credits, weighted totals, overall grade
    # -----------------------------------------
    for sem_data in semesters.values():
        total_points = Decimal("0")
        total_credits = Decimal("0")

        # GPA calculation (standard, per course)
        for course_data in sem_data["courses"].values():
            course = course_data["course"]
            credits = Decimal(str(course.credit_hours or 3))

            percent = course_data["course_total"]  # assumed out of 100
            letter = resolve_letter_grade(percent, grade_rules)
            points = resolve_grade_points(letter)

            total_points += points * credits
            total_credits += credits

        sem_data["total_credits"] = total_credits
        sem_data["gpa"] = (
            round(total_points / total_credits, 2)
            if total_credits > 0 else None
        )

        # -----------------------------------------
        # APPLY WEIGHTS (40 / 60 or admin-defined)
        # -----------------------------------------
        weighted_internal = Decimal("0")
        weighted_external = Decimal("0")

        if sem_data["internal_max"] > 0:
            weighted_internal = (
                (sem_data["internal_raw"] / sem_data["internal_max"])
                * internal_weight
            ).quantize(Decimal("0.0"), rounding=ROUND_HALF_UP)

        if sem_data["external_max"] > 0:
            weighted_external = (
                (sem_data["external_raw"] / sem_data["external_max"])
                * external_weight
            ).quantize(Decimal("0.0"), rounding=ROUND_HALF_UP)


        sem_data["internal_total"] = weighted_internal
        sem_data["external_total"] = weighted_external

        overall = weighted_internal + weighted_external

        # Clamp and round to whole number (no decimals)
        sem_data["overall_score"] = min(
            overall,
            Decimal("100")
        ).quantize(Decimal("0"), rounding=ROUND_HALF_UP)

        sem_data["overall_grade"] = resolve_letter_grade(
            sem_data["overall_score"],
            grade_rules
        )

    # -----------------------------------------
    # Sort semesters (latest first)
    # -----------------------------------------
    semesters = dict(
        sorted(
            semesters.items(),
            key=lambda x: x[1]["semester"].start_date or datetime.date.min,
            reverse=True
        )
    )

    return render(
        request,
        "users/dashboard/contents/student/student_academics.html",
        {
            "semesters": semesters,
            "all_years": all_years,
            "selected_year": selected_year,
            "selected_year_id": selected_year_id,
        }
    )


# LECTURERS DASHBOARD ------------------------------------------------------------------------------------------------------------------------

@login_required
def lecturer_main(request):
    return render(request, "users/dashboard/contents/lecturer/lecturer_main.html")


@login_required
def lecturer_courses(request):

    if getattr(request.user, "role", None) not in ["lecturer", "admin"]:
        messages.error(request, "Access denied.")
        return redirect("home")

    user = request.user

    # BEST WAY: Use the reverse relation
    courses = (
        user.program_courses_taught
        .select_related("program", "level", "semester", "semester__academic_year")
        .filter(is_active=True)
        .order_by("program__name", "level__order", "course_code")
    )

    # print("Courses taught:", courses)

    return render(
        request,
        "users/dashboard/contents/lecturer/lecturer_courses.html",
        {"courses": courses}
    )


# @login_required
# def lecturer_assessments(request):
#     # ----------------------------------------------
#     # ACCESS CONTROL
#     # ----------------------------------------------
#     if getattr(request.user, "role", None) != "lecturer":
#         log_event(request.user, "auth", "Unauthorized access attempt to lecturer assessments page")
#         messages.error(request, "Access denied.")
#         return redirect("home")

#     user = request.user
#     log_event(user, "assessment", "Opened lecturer assessments page")

#     # ----------------------------------------------
#     # LOAD ACTIVE SEMESTERS
#     # ----------------------------------------------
#     semesters = (
#         Semester.objects.filter(is_active=True)
#         .select_related("academic_year")
#         .order_by("-start_date")
#     )

#     # ----------------------------------------------
#     # HANDLE FILTERS
#     # ----------------------------------------------
#     semester_id = request.GET.get("semester_id")
#     search = request.GET.get("search", "").strip()

#     selected_semester = None
#     if semester_id:
#         selected_semester = Semester.objects.filter(id=semester_id).first()
#         log_event(user, "assessment", f"Filter applied → Semester: {selected_semester}")

#     if search:
#         log_event(user, "assessment", f"Search performed → Query: '{search}'")

#     # ----------------------------------------------
#     # BASE ProgramCourse QUERY (courses the lecturer teaches)
#     # ----------------------------------------------
#     base_qs = (
#         ProgramCourse.objects
#         .filter(assigned_lecturers=user, is_active=True)
#         .select_related("program", "level", "semester")  # base_course omitted intentionally
#         .prefetch_related("assigned_lecturers")
#         .order_by("program__name", "course_code")
#     )

#     # Filter by semester if provided
#     if selected_semester:
#         base_qs = base_qs.filter(semester=selected_semester)

#     # Search filter — use ProgramCourse fields and program name
#     if search:
#         base_qs = base_qs.filter(
#             Q(course_code__icontains=search)
#             | Q(title__icontains=search)
#             | Q(program__name__icontains=search)
#             | Q(base_course__code__icontains=search)  # optional helpful match
#             | Q(base_course__title__icontains=search)  # optional
#         )

#     # ----------------------------------------------
#     # PAGINATION (use queryset so count() works)
#     # ----------------------------------------------
#     paginator = Paginator(base_qs, 10)
#     page_number = request.GET.get("page")
#     if page_number:
#         log_event(user, "assessment", f"Visited assessments page → Page number: {page_number}")

#     page_obj = paginator.get_page(page_number)
#     courses_on_page = list(page_obj.object_list)  # ProgramCourse objects shown on this page

#     # ----------------------------------------------
#     # STUDENT COUNT per ProgramCourse (aggregated)
#     # ----------------------------------------------
#     # Get ids of ProgramCourse displayed on this page
#     pc_ids = [c.id for c in courses_on_page]

#     if pc_ids:
#         counts_qs = (
#             StudentRegistration.objects
#             .filter(courses__in=pc_ids)
#             .values("courses")
#             .annotate(student_count=Count("student"))
#         )
#         counts_map = {item["courses"]: item["student_count"] for item in counts_qs}
#     else:
#         counts_map = {}

#     # Attach the computed student_count to each ProgramCourse instance
#     for c in courses_on_page:
#         c.student_count = counts_map.get(c.id, 0)

#     # ----------------------------------------------
#     # RENDER PAGE
#     # ----------------------------------------------
#     return render(
#         request,
#         "users/dashboard/contents/lecturer/lecturer_assessments.html",
#         {
#             "courses": courses_on_page,
#             "semesters": semesters,
#             "selected_semester": selected_semester,
#             "page_obj": page_obj,
#             "search": search,
#         }
#     )


def get_letter_grade(score):
    from .models import Grade
    grade_obj = Grade.objects.filter(min_score__lte=score, max_score__gte=score).first()
    return grade_obj.letter if grade_obj else "N/A"

@login_required
def lecturer_assessments(request):
    user = request.user

    # -----------------------------
    # ACCESS CONTROL
    # -----------------------------
    if request.method == "POST":
        if system_is_locked():
            messages.error(
                request,
                "Cannot create assessments. System is currently locked."
            )
            return redirect("lecturer_assessments")
    
    if getattr(user, "role", None) != "lecturer":
        messages.error(request, "Access denied.")
        return redirect("home")

    # -----------------------------
    # LOAD SEMESTERS
    # -----------------------------
    semesters = (
        Semester.objects.filter(is_active=True)
        .select_related("academic_year")
        .order_by("-start_date")
    )

    # -----------------------------
    # FILTERS
    # -----------------------------
    semester_id = request.GET.get("semester_id")
    search = request.GET.get("search", "").strip()

    selected_semester = None
    if semester_id:
        selected_semester = Semester.objects.filter(id=semester_id).first()
    else:
        # auto-select latest active semester
        selected_semester = semesters.first()

    # -----------------------------
    # BASE QUERYSET (ONLY OWN TASKS)
    # -----------------------------
    qs = (
        AssessmentTask.objects
        .filter(created_by=user)
        .select_related(
            "course",
            "course__program",
            "assessment_type",
            "assessment_category",
            "semester",
        )
        .order_by("-created_at")
    )

    if selected_semester:
        qs = qs.filter(semester=selected_semester)

    if search:
        qs = qs.filter(
            Q(title__icontains=search)
            | Q(course__course_code__icontains=search)
            | Q(course__title__icontains=search)
            | Q(course__program__name__icontains=search)
        )

    # -----------------------------
    # PAGINATION
    # -----------------------------
    paginator = Paginator(qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    tasks_on_page = list(page_obj.object_list)

    # -----------------------------
    # PROGRESS (graded / total)
    # -----------------------------
    task_ids = [t.id for t in tasks_on_page]

    progress_map = {}
    if task_ids:
        total_qs = (
            AssessmentTaskScore.objects
            .filter(task_id__in=task_ids)
            .values("task_id")
            .annotate(total=Count("id"))
        )

        graded_qs = (
            AssessmentTaskScore.objects
            .filter(task_id__in=task_ids, marks_obtained__isnull=False)
            .values("task_id")
            .annotate(graded=Count("id"))
        )

        total_map = {i["task_id"]: i["total"] for i in total_qs}
        graded_map = {i["task_id"]: i["graded"] for i in graded_qs}

        for task_id in task_ids:
            progress_map[task_id] = {
                "graded": graded_map.get(task_id, 0),
                "total": total_map.get(task_id, 0),
            }

    # attach progress to task objects
    for task in tasks_on_page:
        task.progress = progress_map.get(task.id, {"graded": 0, "total": 0})

    # -----------------------------
    # COURSES FOR MODAL (LECTURER ONLY)
    # -----------------------------
    lecturer_courses = (
        ProgramCourse.objects
        .filter(assigned_lecturers=user, is_active=True)
        .select_related("program")
        .order_by("program__name", "course_code")
    )

    assessment_types = AssessmentType.objects.all()
    assessment_categories = AssessmentCategory.objects.all()

    # -----------------------------
    # CREATE TASK (POST FROM MODAL)
    # -----------------------------
    if request.method == "POST":
        try:
            course = ProgramCourse.objects.get(
                id=request.POST.get("course_id"),
                assigned_lecturers=user
            )

            semester = Semester.objects.get(
                id=request.POST.get("semester_id")
            )

            task = AssessmentTask.objects.create(
                course=course,
                semester=semester,
                assessment_type_id=request.POST.get("assessment_type"),
                assessment_category_id=request.POST.get("assessment_category"),
                title=request.POST.get("title").strip(),
                total_marks=request.POST.get("total_marks"),
                created_by=user,
            )

            # auto-create student score rows
            create_task_with_scores(task=task)

            messages.success(request, "Assessment task created successfully.")

        except Exception as e:
            messages.error(request, f"Failed to create task: {e}")

        return redirect("lecturer_assessments")

    # -----------------------------
    # RENDER
    # -----------------------------
    return render(
        request,
        "users/dashboard/contents/lecturer/lecturer_assessments.html",
        {
            "tasks": tasks_on_page,
            "page_obj": page_obj,
            "semesters": semesters,
            "selected_semester": selected_semester,
            "search": search,
            "system_locked": system_is_locked(),

            # modal data
            "lecturer_courses": lecturer_courses,
            "assessment_types": assessment_types,
            "assessment_categories": assessment_categories,
        }
    )


@login_required
def lecturer_assessment_detail(request, task_id):
    user = request.user

    # ---------------------------------
    # ACCESS CONTROL
    # ---------------------------------
    if getattr(user, "role", None) != "lecturer":
        messages.error(request, "Access denied.")
        return redirect("home")

    task = get_object_or_404(
        AssessmentTask.objects.select_related(
            "course",
            "semester",
            "assessment_type",
            "assessment_category",
        ),
        id=task_id,
        created_by=user,
    )

    # ---------------------------------
    # SYSTEM LOCK CHECK (POST ONLY)
    # ---------------------------------
    if request.method == "POST" and system_is_locked():
        messages.error(
            request,
            "Assessment entry is locked. Please contact administration."
        )
        return redirect("lecturer_assessment_detail", task_id=task.id)

    # ---------------------------------
    # LOAD STUDENT SCORES
    # ---------------------------------
    scores_qs = (
        AssessmentTaskScore.objects
        .filter(task=task)
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )

    # ---------------------------------
    # SAVE SCORES
    # ---------------------------------
    if request.method == "POST":
        errors = False
        affected_students = set()

        for score_obj in scores_qs:
            raw = request.POST.get(f"score_{score_obj.student.id}", "").strip()

            if raw == "":
                score_obj.marks_obtained = None
                score_obj.recorded_by = user
                score_obj.save()
                affected_students.add(score_obj.student)
                continue

            try:
                value = Decimal(raw)
            except Exception:
                errors = True
                continue

            if value < 0 or value > Decimal(str(task.total_marks)):
                errors = True
                continue

            score_obj.marks_obtained = value
            score_obj.recorded_by = user
            score_obj.save()
            affected_students.add(score_obj.student)

        # ---------------------------------
        # RECALCULATE FINAL ASSESSMENTS
        # ---------------------------------
        for student in affected_students:
            recalculate_student_assessment(
                student=student,
                course=task.course,
                semester=task.semester,
                recorded_by=user
            )

        # ---------------------------------
        # FEEDBACK + REDIRECT (ONCE)
        # ---------------------------------
        if errors:
            messages.warning(
                request,
                "Some scores were invalid and were not saved. Please review highlighted entries."
            )
        else:
            messages.success(request, "Assessment scores saved successfully.")

        return redirect("lecturer_assessment_detail", task_id=task.id)

    # ---------------------------------
    # RENDER (GET REQUEST)
    # ---------------------------------
    return render(
        request,
        "users/dashboard/contents/lecturer/lecturer_assessment_detail.html",
        {
            "task": task,
            "scores": scores_qs,
        }
    )


@login_required
def download_task_scores_csv(request, task_id):
    user = request.user

    task = get_object_or_404(
        AssessmentTask,
        id=task_id,
        created_by=user
    )

    scores = (
        AssessmentTaskScore.objects
        .filter(task=task)
        .select_related("student")
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{task.title}.csv"'

    writer = csv.writer(response)
    writer.writerow(["student_id", "student_name", "email", "marks_obtained"])

    for s in scores:
        writer.writerow([
            s.student.id,
            s.student.get_full_name(),
            s.student.email,
            s.marks_obtained or "",
        ])

    return response


@login_required
def upload_task_scores_csv(request, task_id):
    user = request.user

    if request.method == "POST":
        if system_is_locked():
            messages.error(
                request,
                "Assessment entry is locked. Please contact administration."
            )
            return redirect("lecturer_assessment_detail", task_id=task.id)

    task = get_object_or_404(
        AssessmentTask,
        id=task_id,
        created_by=user
    )

    if request.method != "POST":
        return redirect("lecturer_assessment_detail", task_id=task.id)

    file = request.FILES.get("file")
    if not file:
        messages.error(request, "No file uploaded.")
        return redirect("lecturer_assessment_detail", task_id=task.id)

    decoded = file.read().decode("utf-8").splitlines()
    reader = csv.DictReader(decoded)

    score_map = {
        s.student_id: s
        for s in AssessmentTaskScore.objects.filter(task=task)
    }

    errors = []

    for row in reader:
        try:
            student_id = int(row["student_id"])
            raw_score = row["marks_obtained"].strip()

            if raw_score == "":
                continue

            score = float(raw_score)

            if score < 0 or score > float(task.total_marks):
                raise ValueError("Score out of range")

            score_obj = score_map.get(student_id)
            if not score_obj:
                raise ValueError("Student not part of task")

            score_obj.marks_obtained = score
            score_obj.recorded_by = user
            score_obj.save()

        except Exception as e:
            errors.append(str(e))

    if errors:
        messages.warning(request, "Some rows failed validation.")
    else:
        messages.success(request, "Scores uploaded successfully.")

    return redirect("lecturer_assessment_detail", task_id=task.id)


# -------------------end lecturer -------------------------------------------------------------------------------------------------------------------

@login_required
def student_manage_courses(request):
    user = request.user

    # ------------------------------------------------------------------
    # AUTHORIZATION
    # ------------------------------------------------------------------
    if user.role != "student":
        log_event(user, "auth", "Unauthorized attempt to access manage courses")
        messages.error(request, "Access denied.")
        return redirect("home")

    # ------------------------------------------------------------------
    # LOAD ACTIVE REGISTRATION
    # ------------------------------------------------------------------
    registration = (
        StudentRegistration.objects
        .filter(student=user)
        .order_by("-submitted_at")
        .first()
    )

    if not registration:
        log_event(user, "registration", "Tried to manage courses without registration")
        return registration_error(
            request,
            "You have not completed registration yet."
        )

    semester = registration.semester
    program = registration.program

    # ------------------------------------------------------------------
    # REGISTRATION WINDOW CHECK
    # ------------------------------------------------------------------
    if not semester.sem_reg_is_active:
        log_event(
            user,
            "registration",
            f"Course modification blocked — registration closed for {semester.name}"
        )
        return registration_error(
            request,
            "Course registration is currently closed."
        )

    # ------------------------------------------------------------------
    # LOAD AVAILABLE COURSES (ACTIVE ONLY)
    # ------------------------------------------------------------------
    available_courses = ProgramCourse.objects.filter(
        program=program,
        semester=semester,
        is_active=True
    ).order_by("course_code")

    registered_ids = set(
        registration.courses.values_list("id", flat=True)
    )

    # ------------------------------------------------------------------
    # HANDLE ADD / REMOVE ACTIONS
    # ------------------------------------------------------------------
    if request.method == "POST":

        # Safety check (in case admin closes window mid-session)
        if not semester.sem_reg_is_active:
            log_event(
                user,
                "registration",
                f"POST blocked — registration closed mid-session ({semester.name})"
            )
            return registration_error(
                request,
                "Registration is now closed."
            )

        course_id = request.POST.get("course_id")
        action = request.POST.get("action")

        if not course_id or not action:
            log_event(user, "registration", "Invalid POST payload")
            return registration_error(request, "Invalid request.")

        try:
            course = ProgramCourse.objects.get(
                id=course_id,
                program=program,
                semester=semester,
                is_active=True
            )
        except ProgramCourse.DoesNotExist:
            log_event(
                user,
                "registration",
                f"Unauthorized course modification attempt (ID: {course_id})"
            )
            return registration_error(request, "Course not found.")

        # -----------------------------
        # ADD COURSE
        # -----------------------------
        if action == "add":
            if course.id in registered_ids:
                messages.info(
                    request,
                    f"{course.course_code} is already registered."
                )
            else:
                registration.courses.add(course)
                registration.save()

                log_event(
                    user,
                    "registration",
                    f"Added course {course.course_code} - {course.title}"
                )

                messages.success(
                    request,
                    f"{course.course_code} added successfully."
                )

        # -----------------------------
        # REMOVE COURSE
        # -----------------------------
        elif action == "remove":
            if course.id not in registered_ids:
                messages.warning(
                    request,
                    f"{course.course_code} is not registered."
                )
            else:
                registration.courses.remove(course)
                registration.save()

                log_event(
                    user,
                    "registration",
                    f"Removed course {course.course_code} - {course.title}"
                )

                messages.warning(
                    request,
                    f"{course.course_code} removed successfully."
                )

        else:
            log_event(
                user,
                "registration",
                f"Invalid action attempted: {action}"
            )
            return registration_error(request, "Invalid action.")

        return redirect("student_manage_courses")

    # ------------------------------------------------------------------
    # RENDER PAGE
    # ------------------------------------------------------------------
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


# DATA UPLOAD # ------------------------------------------------------------------------------------------------------------------------------------ 
def generate_auto_password(first_name: str):
    if not first_name:
        first_name = "User"

    camel = first_name.strip().capitalize()
    year = datetime.datetime.now().year

    return f"@{camel}{year}"


def upload_users(request):
    preview_data = request.session.get("preview_users")

    if request.method == "POST" and "file" in request.FILES:
        file = request.FILES["file"]

        # Load CSV/Excel
        try:
            if file.name.endswith(".csv"):
                df = pd.read_csv(file).fillna("")
            elif file.name.endswith(".xlsx"):
                df = pd.read_excel(file).fillna("")
            else:
                messages.error(request, "Please upload CSV or Excel file only.")
                return redirect("upload_users")
        except Exception:
            messages.error(request, "Invalid file format.")
            return redirect("upload_users")

        # Convert DataFrame to list of dicts
        preview_data = df.to_dict(orient="records")

        # Save to session temporarily
        request.session["preview_users"] = preview_data
        messages.success(request, "File uploaded. Preview below.")
        return redirect("upload_users")

    return render(request, "users/dashboard/contents/admin/upload_users.html", {
        "preview": preview_data
    })


def save_uploaded_users(request):
    preview_data = request.session.get("preview_users")

    if not preview_data:
        messages.error(request, "No data to save!")
        return redirect("upload_users")

    created = 0
    errors = []

    for row in preview_data:
        try:
            # Required fields
            first_name = row.get("first_name", "").strip()
            last_name = row.get("last_name", "").strip()
            username = row.get("username", "").strip()
            role = row.get("role", "").strip()
            email = row.get("email", "").strip()

            # Optional fields default to None
            student_id = None
            pin_code = None
            department = None
            program = None
            is_fee_paid = False

            user = User.objects.create(
                username=username,
                first_name=first_name,
                last_name=last_name,
                role=role,
                email=email,
                student_id=student_id,
                pin_code=pin_code,
                department=department,
                program=program,
                is_fee_paid=is_fee_paid
            )

            # Auto-generate password
            password = generate_auto_password(first_name)
            user.set_password(password)
            user.save()
            created += 1

        except Exception as e:
            errors.append(str(e))

    request.session["preview_users"] = None

    messages.success(request, f"{created} users saved successfully.")
    if errors:
        messages.error(request, f"Errors: {errors}")

    return redirect("admin_manage_users")


# TRANSCRIPT SYSTEM
@login_required
def student_request_transcript(request):
    user = request.user

    if user.role != "student":
        messages.error(request, "Access denied.")
        return redirect("home")

    settings_obj = TranscriptSettings.objects.first()
    if not settings_obj or not settings_obj.allow_requests:
        return registration_error(request, "Transcript request system is locked by admin.")

    # Load most recent request
    latest = TranscriptRequest.objects.filter(student=user).order_by("-created_at").first()

    # CASE A — Already pending
    if latest and latest.status == "pending":
        messages.info(request, "You already have a pending transcript request.")
        return redirect("student_view_transcript")

    # CASE B — Already approved → Redirect to transcript
    if latest and latest.status == "approved":
        return redirect("student_view_transcript")

    # CASE C — Otherwise create NEW request
    try:
        with transaction.atomic():
            req = TranscriptRequest.objects.create(
                student=user,
                status="pending",
            )

            # Pre-generate transcript JSON
            transcript_json = generate_transcript_json(user)
            req.transcript_json = transcript_json
            req.generated_at = timezone.now()
            req.save()

            log_event(user, "transcript", "Student submitted transcript request")

        messages.success(request, "Transcript request submitted successfully.")
        return redirect("student_view_transcript")

    except Exception as e:
        return registration_error(request, f"Could not submit request: {str(e)}")


@login_required
def student_view_transcript(request):
    user = request.user

    if user.role != "student":
        return registration_error(request, "Access denied.")

    settings_obj = TranscriptSettings.objects.first()
    latest = TranscriptRequest.objects.filter(student=user).order_by("-created_at").first()

    school = School.objects.first()

    program = user.program
    department = user.department

    context = {
        "locked": False,
        "state": None,
        "req": latest,
        "transcript": None,
        "school": school, 
        "program": program,
        "department": department,
    }

    # CASE 1 — Locked by admin
    if not settings_obj or not settings_obj.allow_requests:
        context["locked"] = True
        context["state"] = "locked"
        return render(request, "users/dashboard/contents/student/student_transcript.html", context)

    # CASE 2 — No request ever made
    if not latest:
        context["state"] = "no_request"
        return render(request, "users/dashboard/contents/student/student_transcript.html", context)

    # CASE 3 — Pending approval
    if latest.status == "pending":
        context["state"] = "pending"
        return render(request, "users/dashboard/contents/student/student_transcript.html", context)

    # CASE 4 — Rejected
    if latest.status == "rejected":
        context["state"] = "rejected"
        return render(request, "users/dashboard/contents/student/student_transcript.html", context)
    
    # CASE 5: REVOKED
    if latest.status == "revoked":
        context["state"] = "revoked"
        return render(request, "users/dashboard/contents/student/student_transcript.html", context)


     # CASE 6 — APPROVED (always show LIVE UPDATED transcript)
    if latest.status == "approved":
        context["state"] = "approved"

        # ⭐️ Ignore stored JSON — generate fresh transcript every visit
        context["transcript"] = generate_transcript_json(user)

        return render(request, "users/dashboard/contents/student/student_transcript.html", context)
    
      # CASE 7 — Approved but JSON missing (should not happen but handled)
    if latest.status == "approved" and not latest.transcript_json:
        context["state"] = "approved_no_data"
        return render(request, "users/dashboard/contents/student/student_transcript.html", context)

    # If something unexpected happens
    context["state"] = "error"
    return render(request, "users/dashboard/contents/student/student_transcript.html", context)


@login_required
def admin_transcript_requests(request):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    settings_obj = TranscriptSettings.objects.first()

    students = (
        User.objects.filter(role="student")
        # .filter(registrations__isnull=False)
        # .filter(assessments__isnull=False)
        .distinct()
        .order_by("first_name", "last_name")
            )

    requests_qs = (
        TranscriptRequest.objects
        .select_related("student")
        .order_by("-created_at")
    )

    log_event(request.user, "transcript", "Viewed transcript requests dashboard")

    return render(
        request,
        "users/dashboard/contents/admin/admin_transcript_requests.html",
        {
            "requests": requests_qs,
            "settings": settings_obj,
            "students": students,
        }
    )


@login_required
def admin_approve_transcript(request, req_id):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    req = get_object_or_404(TranscriptRequest, id=req_id)

    if not req.transcript_json:
        messages.error(
            request,
            "Transcript must be generated before approval."
        )
        return redirect("admin_transcript_requests")

    req.status = "approved"
    req.approved_at = timezone.now()
    req.save()

    log_event(
        request.user,
        "transcript",
        f"Approved transcript access for {req.student.get_full_name()}"
    )

    messages.success(request, "Transcript approved.")
    return redirect("admin_transcript_requests")

@login_required
def admin_revoke_transcript(request, req_id):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    req = get_object_or_404(TranscriptRequest, id=req_id)

    req.status = "revoked"
    req.save()

    log_event(request.user, "transcript", f"Revoked transcript access for {req.student.get_full_name()}")

    messages.success(request, f"Transcript access revoked for {req.student.get_full_name()}.")
    return redirect("admin_transcript_requests")


@login_required
def admin_reject_transcript(request, req_id):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    req = get_object_or_404(TranscriptRequest, id=req_id)
    req.status = "rejected"
    req.admin_notes = "Rejected by administrator"
    req.save()

    log_event(
        request.user,
        "transcript",
        f"Rejected transcript for {req.student.get_full_name()}"
    )

    messages.warning(request, "Transcript request rejected.")
    return redirect("admin_transcript_requests")

@login_required
def admin_generate_transcript(request, req_id):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    req = get_object_or_404(TranscriptRequest, id=req_id)

    transcript_json = generate_transcript_json(req.student)

    req.transcript_json = transcript_json
    req.generated_at = timezone.now()
    req.save()

    log_event(
        request.user,
        "transcript",
        f"Generated transcript for {req.student.get_full_name()}"
    )

    messages.success(request, "Transcript generated successfully.")
    return redirect("admin_transcript_requests")

@login_required
def admin_toggle_transcript_lock(request):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    settings_obj, _ = TranscriptSettings.objects.get_or_create(id=1)

    settings_obj.allow_requests = not settings_obj.allow_requests
    settings_obj.save()

    state = "enabled" if settings_obj.allow_requests else "disabled"

    messages.success(request, f"Transcript request system {state}.")
    return redirect("admin_transcript_requests")

@login_required
def admin_generate_transcript_for_student(request):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    if request.method == "POST":
        student_id = request.POST.get("student_id")

        if not student_id:
            messages.error(request, "No student selected.")
            return redirect("admin_transcript_requests")

        student = User.objects.filter(id=student_id, role="student").first()
        if not student:
            messages.error(request, "Invalid student selected.")
            return redirect("admin_transcript_requests")

    # Generate transcript JSON
    transcript_json = generate_transcript_json(student)

    # Create or update the request
    req, _ = TranscriptRequest.objects.update_or_create(
        student=student,
        defaults={
            "status": "approved",
            "transcript_json": transcript_json,
            "generated_at": timezone.now(),
            "approved_at": timezone.now(),
        }
    )

    log_event(request.user, "transcript", f"Admin generated transcript for {student.get_full_name()}")

    return render(
        request,
        "users/dashboard/contents/admin/admin_transcript_preview.html",
        {
            "student": student,
            "transcript": transcript_json,
            "generated_at": req.generated_at,
        }
    )

@login_required
def admin_delete_transcript_request(request, req_id):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    req = TranscriptRequest.objects.filter(id=req_id).first()
    if not req:
        messages.error(request, "Request not found.")
    else:
        req.delete()
        messages.success(request, "Transcript request deleted.")

    return redirect("admin_transcript_requests")

@login_required
def admin_clear_all_transcript_requests(request):
    if request.user.role != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    # Delete ALL transcript requests
    TranscriptRequest.objects.all().delete()

    messages.success(request, "All transcript requests have been cleared.")
    return redirect("admin_transcript_requests")


@login_required
def student_fee_payments(request):
    user = request.user

    if user.role != "student":
        messages.error(request, "Access denied.")
        return redirect("home")

    payments = (
        Payment.objects
        .filter(student=user)
        .select_related("academic_year", "semester", "program")
        .prefetch_related("breakdowns__component__component")
        .order_by("academic_year__start_date", "semester__start_date", "created_at")
    )

    # Lookup declared program fees
    program_fees = {
        (pf.academic_year_id, pf.semester_id): pf
        for pf in ProgramFee.objects.filter(program=user.program)
    }

    finance_blocks = {}

    for payment in payments:
        key = (payment.academic_year, payment.semester)

        if key not in finance_blocks:
            pf = program_fees.get((payment.academic_year_id, payment.semester_id))

            finance_blocks[key] = {
                "academic_year": payment.academic_year,
                "semester": payment.semester,
                "program_fee": pf,
                "payments": [],
                "total_paid": Decimal("0.00"),
                "credit": Decimal("0.00"),
                "balance": None,
                "is_fully_paid": False,
            }

        block = finance_blocks[key]

        block["payments"].append(payment)
        block["total_paid"] += payment.amount_paid
        block["credit"] += payment.credit_balance

    # Final balance per semester
    for block in finance_blocks.values():
        pf = block["program_fee"]
        if pf:
            block["balance"] = max(
                Decimal("0.00"),
                pf.total_amount - block["total_paid"]
            )
            block["is_fully_paid"] = block["balance"] == 0
        else:
            block["balance"] = None

    return render(
        request,
        "users/dashboard/contents/student/fee_payments.html",
        {
            "finance_blocks": finance_blocks,
        }
    )


# -------------------------ANNOUNCEMENTS ------------------------
@login_required
def announcements_list(request):
    user = request.user
    announcements = Announcement.objects.all().order_by("-created_at")

    # Handle create / update / delete
    if request.method == "POST":
        action = request.POST.get("form_action")
        ann_id = request.POST.get("announcement_id")

        # CREATE
        if action == "create":
            Announcement.objects.create(
                created_by=user,
                role=user.role,
                title=request.POST.get("title"),
                message=request.POST.get("body"),
                link=request.POST.get("link", "")
            )
            messages.success(request, "Announcement created.")
            return redirect("announcements_list")

        # UPDATE
        if action == "update":
            ann = get_object_or_404(Announcement, id=ann_id)
            ann.title = request.POST.get("title")
            ann.message = request.POST.get("body")
            ann.link = request.POST.get("link", "")
            ann.save()
            messages.success(request, "Announcement updated.")
            return redirect("announcements_list")

        # DELETE
        if action == "delete":
            ann = get_object_or_404(Announcement, id=ann_id)
            ann.delete()
            messages.success(request, "Announcement deleted.")
            return redirect("announcements_list")

    return render(request, "users/dashboard/contents/admin/announcement_list.html", {
        "announcements": announcements
    })

@login_required
def mark_announcement_read(request):
    ann_id = request.POST.get("announcement_id")

    print("notif clicked")

    announcement = CourseAnnouncement.objects.filter(
        id=ann_id,
        is_active=True
    ).first()

    if not announcement:
        return JsonResponse({"success": False})

    # 🔐 Optional extra safety: ensure student belongs to the course
    # (recommended if you want to be strict)

    announcement.is_active = False
    announcement.save(update_fields=["is_active"])

    return JsonResponse({"success": True})