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
    path("student/transcript/", views.student_request_transcript, name="student_request_transcript"),
    path("student/profile/", views.student_profile, name="student_profile"),
    path("student/transcript/view", views.student_view_transcript, name="student_view_transcript"),
    path("student/fee-payments/", views.student_fee_payments, name="student_fee_payments"),
    path("notifications/mark-read/", views.mark_announcement_read, name="mark_announcement_read"),


    path("lecturer/", views.lecturer_main, name="lecturer_main"),
    path("lecturer/courses/", views.lecturer_courses, name="lecturer_courses"),
    path("lecturer/assessments/", views.lecturer_assessments, name="lecturer_assessments"),
    path("lecturer/assessments/task/<int:task_id>/",   views.lecturer_assessment_detail,name="lecturer_assessment_detail",),
    path("lecturer/grades/", views.lecturer_grades, name="lecturer_grades"),
    path("lecturer/courses/<int:course_id>/", views.course_detail, name="course_detail"),
    path("lecturer/resources/<int:resource_id>/delete/", views.resource_delete, name="resource_delete"),
    path("lecturer/assessments/task/<int:task_id>/download-csv/",views.download_task_scores_csv,name="download_task_scores_csv",),
    path("lecturer/assessments/task/<int:task_id>/upload-csv/",views.upload_task_scores_csv,name="upload_task_scores_csv",),
   

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
    path("admin/upload-users/", views.upload_users, name="upload_users"),
    path("admin/save-uploaded-users/", views.save_uploaded_users, name="save_uploaded_users"),
    path("program-fee/<int:fee_id>/toggle-allowed/",views.toggle_program_fee_allowed,name="toggle_program_fee_allowed",),


    path("dean/", views.dean_main, name="dean_main"),
    path("dean/assign-lecturers/", views.assign_lecturers, name="assign_lecturers"),
    path("dean/manage-courses/", views.manage_courses, name="manage_courses"),
    path("dean/assessments/", views.assessments, name="assessments"),
    path('dean/program-courses/', views.dean_program_courses_list, name='dean_program_courses_list'),
    path("dean/program-course/<int:pc_id>/json/", views.ajax_get_program_course, name="ajax_get_program_course"),
    path("dean/program-course/update/", views.ajax_update_program_course, name="ajax_update_program_course"),
    path("dean/ajax/program-levels-courses/<int:program_id>/", views.ajax_program_levels_courses),
    path("dean/ajax/level-semesters/<int:level_id>/", views.ajax_level_semesters),
    path("dean/program-course/duplicate/", views.ajax_duplicate_program_course),
    path("dean/program-course/delete/", views.ajax_delete_program_course, name="ajax_delete_program_course"),
    
    
    path("admin/transcripts/", views.admin_transcript_requests, name="admin_transcript_requests"),
    # path("admin/announcements/", views.announcements_list, name="announcements_list"),
    path("admin/transcripts/generate/<int:req_id>/", views.admin_generate_transcript, name="admin_generate_transcript"),
    path("admin/transcripts/approve/<int:req_id>/", views.admin_approve_transcript, name="admin_approve_transcript"),
    path("admin/transcripts/reject/<int:req_id>/", views.admin_reject_transcript, name="admin_reject_transcript"),
    path("admin/transcripts/revoke/<int:req_id>/", views.admin_revoke_transcript, name="admin_revoke_transcript"),
    path("admin/transcripts/toggle/", views.admin_toggle_transcript_lock, name="admin_toggle_transcript_lock"),
    path("admin/transcripts/generate-for-student/", views.admin_generate_transcript_for_student, name="admin_generate_transcript_for_student"),
    path(
    "transcripts/requests/delete/<int:req_id>/",
    views.admin_delete_transcript_request,
    name="admin_delete_transcript_request",
    ),

    path(
    "transcripts/requests/clear-all/",
    views.admin_clear_all_transcript_requests,
    name="admin_clear_all_transcript_requests",
    ),

    path("school/setup/", views.admin_school_setup, name="admin_school_setup"),
    path("admin/ajax/program-levels/<int:program_id>/", views.ajax_get_program_levels, name="ajax_program_levels"),
    path("admin/announcements/", views.announcements_list, name="announcements_list"),

    path("logout/", views.logout_view, name="logout"),
]