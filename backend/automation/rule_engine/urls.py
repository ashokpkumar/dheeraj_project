from django.urls import path

from . import views
from .functions.ocr_extraction import views as ocr_views


urlpatterns = [

    path(
        "functions/",
        views.discover_functions
    ),

    path(
        "rules/save/",
        views.save_rule
    ),

    path(
        "rules/",
        views.list_rules
    ),

    path(
        "rules/<int:rule_id>/",
        views.rule_details
    ),

    path(
        "rules/<int:rule_id>/execute/",
        views.execute_rule
    ),
     path("dashboard/", views.dashboard, name="dashboard"),
     
    path("claims/export/", views.export_claims_csv, name="export_claims_csv"),

      # List all jobs / Create or update a job
    path("scheduler/jobs/",              views.scheduled_jobs, name="scheduled-jobs"),

    # Pause / resume a specific job
    path("scheduler/jobs/<int:job_id>/toggle/", views.toggle_job,  name="toggle-job"),

    # Delete a specific job
    path("scheduler/jobs/<int:job_id>/",        views.delete_job,  name="delete-job"),

    path("functions/refresh/", views.refresh_functions, name="refresh-functions"),

    # ─── OCR Annotation ───────────────────────────────────────────────
    path("ocr/upload/",                    ocr_views.upload_pdf,       name="ocr-upload"),
    path("ocr/page-image/",                ocr_views.page_image,       name="ocr-page-image"),
    path("ocr/uploads/<str:doc_id>/",      ocr_views.discard_upload,   name="ocr-discard-upload"),
    path("ocr/templates/",                 ocr_views.list_templates,   name="ocr-list-templates"),
    path("ocr/templates/save/",            ocr_views.save_template,    name="ocr-save-template"),
    path("ocr/templates/<str:name>/",      ocr_views.get_template,     name="ocr-get-template"),
    path("ocr/templates/<str:name>/delete/", ocr_views.delete_template, name="ocr-delete-template"),
    path("ocr/extract/",                   ocr_views.run_extraction,   name="ocr-run-extraction"),

]
