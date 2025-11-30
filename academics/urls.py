from django.urls import path
from . import views

urlpatterns = [
    # Admin routes
    path('programs/', views.manage_programs, name='manage_programs'),
    path('programs/<int:program_id>/assign-dean/', views.assign_dean, name='assign_dean'),

    # Dean routes
    path('courses/', views.manage_courses, name='manage_courses'),
    path('courses/<int:course_id>/assign-lecturer/', views.assign_lecturer, name='assign_lecturer'),
]
