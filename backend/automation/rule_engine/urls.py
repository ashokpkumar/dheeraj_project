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
]
