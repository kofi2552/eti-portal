from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Program, Course
from users.models import CustomUser

# -------------------------------
# ADMIN VIEWS
# -------------------------------
@login_required
def manage_programs(request):
    if request.user.role != 'admin':
        return redirect('forbidden')
    
    programs = Program.objects.all()
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        Program.objects.create(name=name, description=description, created_by=request.user)
        messages.success(request, "Program created successfully!")
        return redirect('manage_programs')

    return render(request, 'academic/manage_programs.html', {'programs': programs})


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
def manage_courses(request):
    if request.user.role != 'dean':
        return redirect('forbidden')

    programs = Program.objects.filter(dean=request.user)
    courses = Course.objects.filter(program__in=programs)

    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code')
        program_id = request.POST.get('program')
        program = Program.objects.get(id=program_id)
        Course.objects.create(program=program, name=name, code=code)
        messages.success(request, "Course added successfully!")
        return redirect('manage_courses')

    return render(request, 'academic/manage_courses.html', {'courses': courses, 'programs': programs})


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
