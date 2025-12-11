from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from .models import Program, Course
from users.models import CustomUser, Payment, StudentRegistration
from .models import Department, Semester, ProgramCourse, Assessment, Grade,  TranscriptSettings
import csv
from django.http import HttpResponse
import pandas as pd
from collections import defaultdict
from django.http import JsonResponse, HttpResponseBadRequest
from django.core.exceptions import ValidationError
from academics.transition_service import run_program_transition
from portal.models import SystemLock


# -------------------------------
# ADMIN VIEWS
# -------------------------------

@login_required
def admin_transition_page(request):
    # Only admin allowed
    if getattr(request.user, "role", None) != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")
    
    lock_obj = SystemLock.objects.first()

    programs = Program.objects.all().order_by("name")
    return render(request, "users/dashboard/contents/admin/admin_transition.html", {"programs": programs,  "system_lock": lock_obj})


@login_required
def start_program_transition(request):
    # AJAX endpoint (POST) to run the transition
    if request.method != "POST":
        return HttpResponseBadRequest("POST required.")

    if getattr(request.user, "role", None) != "admin":
        return JsonResponse({"success": False, "error": "Access denied."}, status=403)
    
    lock_obj = SystemLock.objects.first()
    if not lock_obj.is_locked:
        return JsonResponse({
            "success": False,
            "error": "System must be LOCKED before running transition."
        }, status=403)

    program_id = request.POST.get("program_id")
    if not program_id:
        return JsonResponse({"success": False, "error": "program_id is required"}, status=400)

    try:
        result = run_program_transition(int(program_id), request.user)
        # Return JSON with logs and summary
        return JsonResponse(result)
    except ValidationError as ve:
        return JsonResponse({"success": False, "error": ve.message}, status=400)
    except Exception as e:
        # Unexpected error - return message (more secure apps may log and return generic message)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def transition_result_page(request):
    # fallback server-rendered results (if you prefer full page render)
    # You may decide to call run_program_transition directly here for non-AJAX usage
    return render(request, "users/dashboard/contents/admin/transition_result.html", {})



@login_required
def assign_dean(request, program_id):
    if request.user.role != 'admin':
        return redirect('forbidden')

    program = get_object_or_404(Program, id=program_id)
    deans = CustomUser.objects.filter(role='dean')

    if request.method == 'POST':
        dean_id = request.POST.get('dean')
        program.dean_id = dean_id
        program.save()
        messages.success(request, "Dean assigned successfully!")
        return redirect('manage_programs')

    return render(request, 'academic/assign_dean.html', {'program': program, 'deans': deans})


# -------------------------------
# DEAN VIEWS
# -------------------------------


@login_required
def assign_lecturer(request, course_id):
    if request.user.role != 'dean':
        return redirect('forbidden')

    course = get_object_or_404(Course, id=course_id, program__dean=request.user)
    lecturers = CustomUser.objects.filter(role='lecturer')

    if request.method == 'POST':
        lecturer_ids = request.POST.getlist('lecturers')
        course.assigned_lecturers.set(lecturer_ids)
        course.save()
        messages.success(request, "Lecturers assigned successfully!")
        return redirect('manage_courses')

    return render(request, 'academic/assign_lecturer.html', {'course': course, 'lecturers': lecturers})


@login_required
def download_score_template(request, course_id, semester_id):
    user = request.user

    if user.role != "lecturer":
        messages.error(request, "Access denied.")
        return redirect("home")

    # Validate course ownership
    course = get_object_or_404(ProgramCourse, id=course_id, assigned_lecturers=user)
    semester = get_object_or_404(Semester, id=semester_id)

    # Fetch registered students
    registrations = StudentRegistration.objects.filter(
        program=course.program,
        semester=semester,
        courses=course
    ).select_related("student")

    students = [reg.student for reg in registrations]

    # 🔥 Fetch existing assessments (dict of student_id → score)
    existing_scores = {
        a.student_id: a.score
        for a in Assessment.objects.filter(course=course, semester=semester)
    }

    # CSV response
    response = HttpResponse(content_type="text/csv")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="scores_template_{course.course_code}_{semester.name}.csv"'

    writer = csv.writer(response)

    # Header
    writer.writerow([
        "student_id",
        "student_name",
        "program",
        "course",
        "semester",
        "score",
    ])

    # Rows
    for stu in students:
        writer.writerow([
            stu.student_id,
            f"{stu.first_name} {stu.last_name}",
            course.program.name,
            course.title,
            semester.name,
            existing_scores.get(stu.id, ""), 
        ])

    return response


@login_required
def upload_scores_csv(request, course_id, semester_id):
    user = request.user

    if user.role != "lecturer":
        messages.error(request, "Access denied.")
        return redirect("home")

    if request.method != "POST" or "file" not in request.FILES:
        messages.error(request, "No file uploaded.")
        return redirect("lecturer_enter_assessments", course_id, semester_id)

    file = request.FILES["file"]

    # Read CSV
    try:
        df = pd.read_csv(file).fillna("")
    except:
        messages.error(request, "Invalid CSV format.")
        return redirect("lecturer_enter_assessments", course_id, semester_id)

    # Validate required columns
    if "student_id" not in df or "score" not in df:
        messages.error(request, "CSV must have student_id and score columns.")
        return redirect("lecturer_enter_assessments", course_id, semester_id)

    # Fetch course & semester
    course = get_object_or_404(ProgramCourse, id=course_id, assigned_lecturers=user)
    semester = get_object_or_404(Semester, id=semester_id)

    # Grade helper
    def get_letter(score):
        g = Grade.objects.filter(min_score__lte=score, max_score__gte=score).first()
        return g.letter if g else "N/A"

    created, updated = 0, 0

    User = get_user_model()

    for _, row in df.iterrows():
        student_id = row["student_id"]
        score = row["score"]

        if score == "":
            continue  # lecturer didn't fill it

        try:
            score = float(score)
        except:
            continue

        # NEW VALIDATION
        if score < 0 or score > 100:
            messages.error(
                request,
                f"Invalid score '{score}' for student ID {student_id}. Scores must be between 0 and 100."
            )
            return redirect("lecturer_enter_assessments", course_id, semester_id)
    
        student = get_object_or_404(
        User,
        student_id=student_id,
        role="student"
        )
        grade = get_letter(score)

        # Insert or update
        assessment, created_flag = Assessment.objects.update_or_create(
            student=student,
            course=course,
            semester=semester,
            defaults={
                "program": course.program,
                "score": score,
                "grade": grade,
                "recorded_by": user
            }
        )

        if created_flag:
            created += 1
        else:
            updated += 1

    messages.success(
        request,
        f"Scores uploaded successfully. Created: {created}, Updated: {updated}"
    )
    return redirect("lecturer_enter_assessments", course_id, semester_id)


# TRANSCRIPT SYSTEM

def generate_transcript_data(student):
    """
    Build a full transcript nested by:
    LEVEL → SEMESTER → COURSES (score, grade)
    """

    # Fetch all assessments for the student
    assessments = (
        Assessment.objects
        .filter(student=student)
        .select_related("course", "semester", "semester__academic_year", "semester__level")
        .order_by("semester__level__order", "semester__start_date")
    )

    transcript = defaultdict(lambda: defaultdict(list))

    for a in assessments:
        pc = a.course  # ProgramCourse

        level_name = pc.level.level_name if pc.level else "Unknown Level"
        sem_name = f"{pc.semester.name} - {pc.semester.academic_year.name}"

        transcript[level_name][sem_name].append({
            "course_code": pc.course_code,
            "course_title": pc.title,
            "credit_hours": pc.credit_hours,
            "score": float(a.score),
            "grade": a.grade,
        })

    # Compute CGPA
    grade_points = {
        "A": 4.0, "B+": 3.5, "B": 3.0,
        "C+": 2.5, "C": 2.0, "D+": 1.5,
        "D": 1.0, "F": 0.0,
    }

    total_points = 0
    total_credits = 0

    for level, semesters in transcript.items():
        for sem, courses in semesters.items():
            for c in courses:
                gp = grade_points.get(c["grade"], 0)
                credits = c["credit_hours"]
                total_points += gp * credits
                total_credits += credits

    cgpa = round(total_points / total_credits, 2) if total_credits else None

    return {
        "student_name": student.get_full_name(),
        "student_id": student.student_id,
        "cgpa": cgpa,
        "levels": transcript,  # nested structure
    }



