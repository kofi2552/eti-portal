from django.urls import path
from finance import views

urlpatterns = [
    path("login/", views.finance_login, name="finance_login"),
    path("dashboard/", views.finance_dashboard, name="finance_dashboard"),
    path("dashboard/", views.finance_main, name="finance_main"),
    path("semester-fees/", views.semester_fee_list, name="semester_fee_list"),
    path("payments/create/", views.finance_create_student_payment, name="finance_create_student_payment"),
    path("ajax/program-fee/<int:program_id>/<int:year_id>/<int:semester_id>/",views.ajax_program_fee_components,),
    path("payments/export/csv/", views.finance_export_summary_payments_csv, name="finance_export_summary_payments_csv"),
    path("full-payments/export/csv/", views.finance_export_payments_csv, name="finance_export_payments_csv"),
    path("ajax/program-fee/<int:fee_id>/detail/",views.finance_program_fee_detail,name="finance_program_fee_detail"),
    path("students/<int:student_id>/finance/",views.finance_payment_detail,name="finance_payment_detail",)
]