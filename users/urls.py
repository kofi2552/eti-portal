from django.urls import path
from . import views

urlpatterns = [
    path("student/login/", views.student_login, name="student_login"),
    path("lecturer/login/", views.lecturer_login, name="lecturer_login"),
    path("dean/login/", views.dean_login, name="dean_login"),
    path("admin/login/", views.admin_login, name="admin_login"),
    path("admin/logs/", views.admin_logs, name="admin_logs"),
    path("admin/dashboard/", views.admin_dashboard, name="admin_dashboard"),

    path("student/", views.student_main, name="student_main"),
    path("student/academics/", views.student_academics, name="student_academics"),
    path("student/manage-courses/", views.student_manage_courses, name="student_manage_courses"),
    path("student/course/<int:course_id>/",views.student_course_details, name="student_course_details"),
    path("student/registeration/step-1/", views.registration_step_1, name="registration_step_1"),
    path("student/registeration/step-2/", views.registration_step_2, name="registration_step_2"),
    path("student/registeration/step-3/", views.registration_step_3, name="registration_step_3"),
    path("student/registeration/step-4/", views.registration_step_4, name="registration_step_4"),
    path("student/registeration/complete/", views.registration_complete, name="registration_complete"),

    path("lecturer/", views.lecturer_main, name="lecturer_main"),
    path("lecturer/courses/", views.lecturer_courses, name="lecturer_courses"),
    path("lecturer/assessments/", views.lecturer_assessments, name="lecturer_assessments"),
    path("lecturer/courses/<int:course_id>/enter/<int:semester_id>/", views.lecturer_enter_assessments, name='lecturer_enter_assessments'),
    path("lecturer/grades/", views.lecturer_grades, name="lecturer_grades"),
    path("lecturer/courses/<int:course_id>/", views.course_detail, name="course_detail"),
    path("lecturer/resources/<int:resource_id>/delete/", views.resource_delete, name="resource_delete"),

    path("admin/", views.admin_main, name="admin_main"),
    path("admin/manage-users/", views.admin_manage_users, name="admin_manage_users"),
    path("admin/enroll/students/", views.student_enrollment, name="student_enrollment"),
    path("admin/enroll/students/payments/pdf/<int:payment_id>/", views.generate_payment_pdf, name="payment_pdf"),
    path("admin/manage-school/", views.admin_school, name="admin_school"),
    path("admin/manage-users/edit/<int:id>/", views.edit_user, name="edit_user"),
    path("admin/manage-users/delete/<int:id>/", views.delete_user, name="delete_user"),
    path("admin/export-users-csv/", views.export_users_csv, name="export_users_csv"),
    path("admin/manage-programs/", views.admin_manage_programs, name="admin_manage_programs"),
    path("admin/reports/", views.admin_reports, name="admin_reports"),

    
    path("dean/", views.dean_main, name="dean_main"),
    path("dean/assign-lecturers/", views.assign_lecturers, name="assign_lecturers"),
    path("dean/manage-courses/", views.manage_courses, name="manage_courses"),
    path("dean/assessments/", views.assessments, name="assessments"),

    path("logout/", views.logout_view, name="logout"),
]