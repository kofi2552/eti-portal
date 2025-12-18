# portal/urls.py
from django.urls import path
from . import views

app_name = "portal"

urlpatterns = [
    path('dashboard/', views.dashboard_redirect, name='dashboard'),
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('lecturer/', views.lecturer_dashboard, name='lecturer_dashboard'),
    path('dean/', views.dean_dashboard, name='dean_dashboard'),
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    path('unauthorized/', views.unauthorized, name='unauthorized'),
    path('login/student/', views.student_login, name='student_login'),
    path('login/lecturer/', views.lecturer_login, name='lecturer_login'),
    path('login/dean/', views.dean_login, name='dean_login'),
    path('login/admin/', views.admin_login, name='admin_login'),
    path('users/admin/system-lock', views.toggle_system_lock, name='toggle_system_lock'),
    path('accounts/login/', views.auth_portal, name='auth_portal'),
    path('', views.home, name='home'),
]
