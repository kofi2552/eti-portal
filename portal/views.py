from django.shortcuts import render, redirect, get_object_or_404
from .decorators import role_required
from django.contrib.auth.decorators import login_required
from .models import SystemLock
from django.contrib import messages
from .models import Announcement


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

# def home(request):
#     return render(request, "portal/home.html")


def student_login(request):
    return render(request, "portal/login.html", {"role": "Student"})

def lecturer_login(request):
    return render(request, "portal/login.html", {"role": "Lecturer"})

def dean_login(request):
    return render(request, "portal/login.html", {"role": "Dean/HOD"})

def admin_login(request):
    return render(request, "portal/login.html", {"role": "Super Admin"})


@login_required
def toggle_system_lock(request):
    if getattr(request.user, "role", None) != "admin":
        messages.error(request, "Access denied.")
        return redirect("home")

    lock_obj = SystemLock.objects.first()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "lock":
            lock_obj.lock(request.user)
            messages.success(request, "System is now LOCKED.")
        elif action == "unlock":
            lock_obj.unlock()
            messages.success(request, "System is now UNLOCKED.")

        return redirect("admin_transition_page")

    return redirect("admin_transition_page")



def home(request):
    # anns = Announcement.objects.filter(role="admin", is_active=True).order_by("-created_at")[:5]
    return render(request, "portal/home.html")


def auth_portal(request):
    anns = Announcement.objects.filter(role="admin", is_active=True).order_by("-created_at")[:5]
    return render(request, "portal/auth_page.html", {"announcements": anns})

