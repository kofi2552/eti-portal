from django.urls import path
from . import views


urlpatterns = [
    # Admin routes
    # path('programs/', views.manage_programs, name='manage_programs'),
    path('programs/<int:program_id>/assign-dean/', views.assign_dean, name='assign_dean'),

    # Dean routes
    # path('courses/', views.manage_courses, name='manage_courses'),
    path('courses/<int:course_id>/assign-lecturer/', views.assign_lecturer, name='assign_lecturer'),

    path("lecturer/course/<int:course_id>/semester/<int:semester_id>/download-template/", views.download_score_template, name="download_score_template"),

    path("lecturer/course/<int:course_id>/semester/<int:semester_id>/upload-scores/", views.upload_scores_csv, name="upload_scores_csv"),

    path("course-announcements/", views.course_announcements, name="course_announcements"),

    # TRANSCRIPT URLS
    path("admin/transition/", views.admin_transition_page, name="admin_transition_page"),
    path("admin/transition/start/", views.start_program_transition, name="start_program_transition"),
    path("admin/transition/result/", views.transition_result_page, name="transition_result_page"),
]
