from django.urls import path

from . import views


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

]
