from django.urls import path
from finance import views, api_views

urlpatterns = [
    path("login/", views.finance_login, name="finance_login"),
    path("dashboard/", views.finance_dashboard, name="finance_dashboard"),
    path("dashboard/", views.finance_main, name="finance_main"),
    path("semester-fees/", views.semester_fee_list, name="semester_fee_list"),
    path("payments/create/", views.finance_create_student_payment, name="finance_create_student_payment"),
    path("ajax/program-fee/<int:program_id>/<int:year_id>/<int:semester_id>/",views.ajax_program_fee_components, name="ajax_program_fee_components"),
    path("payments/export/csv/", views.finance_export_summary_payments_csv, name="finance_export_summary_payments_csv"),
    path("full-payments/export/csv/", views.finance_export_payments_csv, name="finance_export_payments_csv"),
    path("students/export-template/csv/", views.finance_export_student_template_csv, name="finance_export_student_template_csv"),
    path("payments/upload-backlog/csv/", views.finance_upload_backlog_csv, name="finance_upload_backlog_csv"),
    path("payments/save-backlog/", views.finance_save_backlog, name="finance_save_backlog"),
    path("ajax/program-fee/<int:fee_id>/detail/",views.finance_program_fee_detail,name="finance_program_fee_detail"),
    path("students/<int:student_id>/finance/",views.finance_payment_detail,name="finance_payment_detail",),
    
    # Applications & Bank Transactions
    path("applications/", views.finance_applications, name="finance_applications"),
    path("bank-transactions/", views.finance_bank_transactions, name="finance_bank_transactions"),
    path("bank-transactions/<int:tx_id>/verify/", views.finance_verify_bank_transaction, name="finance_verify_bank_transaction"),
    
    # Bank Integration API Endpoints
    path("api/v1/bank/students/validate/", api_views.bank_validate_student, name="bank_validate_student"),
    path("api/v1/bank/payments/notify/", api_views.bank_notify_payment, name="bank_notify_payment"),
    
    # Overpayment Reimbursements
    path("overpayments/<int:op_id>/request-refund/", views.finance_request_reimbursement, name="finance_request_reimbursement"),
    path("overpayments/<int:op_id>/confirm-reimbursement/", views.admin_confirm_reimbursement, name="admin_confirm_reimbursement"),
    path("overpayments/<int:op_id>/reject-reimbursement/", views.admin_reject_reimbursement, name="admin_reject_reimbursement"),

    # Bank Transaction Archival
    path("bank-transactions/<int:tx_id>/request-archive/", views.finance_request_bank_transaction_deletion, name="finance_request_bank_transaction_deletion"),
    path("bank-transactions/<int:tx_id>/confirm-archive/", views.admin_confirm_bank_transaction_deletion, name="admin_confirm_bank_transaction_deletion"),
    path("bank-transactions/<int:tx_id>/reject-archive/", views.admin_reject_bank_transaction_deletion, name="admin_reject_bank_transaction_deletion"),
    path("bank-transactions/export-csv/", views.finance_export_bank_transactions_csv, name="finance_export_bank_transactions_csv"),
    path("ajax/semesters/<int:level_id>/", views.ajax_get_semesters, name="ajax_get_semesters"),
    path("ajax/program-levels/<int:program_id>/", views.ajax_get_program_levels, name="ajax_get_program_levels"),
    path("ajax/student-details/<int:student_id>/", views.ajax_get_student_details, name="ajax_get_student_details"),
]