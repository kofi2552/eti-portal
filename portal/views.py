from django.shortcuts import render, redirect
from .decorators import role_required

def dashboard_redirect(request):
    """Redirect users to the correct dashboard based on role."""
    if not request.user.is_authenticated:
        return redirect('/admin/login/')

    role = request.user.role
    if role == 'student':
        return redirect('student_dashboard')
    elif role == 'lecturer':
        return redirect('lecturer_dashboard')
    elif role == 'dean':
        return redirect('dean_dashboard')
    elif role == 'admin':
        return redirect('admin_dashboard')
    else:
        return redirect('/unauthorized/')


@role_required('student')
def student_dashboard(request):
    return render(request, 'student_dashboard.html')


@role_required('lecturer')
def lecturer_dashboard(request):
    return render(request, 'lecturer_dashboard.html')


@role_required('dean')
def dean_dashboard(request):
    return render(request, 'dean_dashboard.html')


@role_required('admin')
def admin_dashboard(request):
    return render(request, 'admin_dashboard.html')


def unauthorized(request):
    return render(request, 'unauthorized.html')

def home(request):
    return render(request, "portal/home.html")


def student_login(request):
    return render(request, "portal/login.html", {"role": "Student"})

def lecturer_login(request):
    return render(request, "portal/login.html", {"role": "Lecturer"})

def dean_login(request):
    return render(request, "portal/login.html", {"role": "Dean/HOD"})

def admin_login(request):
    return render(request, "portal/login.html", {"role": "Super Admin"})