from django.urls import path

from . import views

app_name = "moderation"

urlpatterns = [
    path("", views.queue, name="queue"),
    path("verification/apply/", views.apply_for_verification, name="apply"),
    path("verification/code/", views.redeem_code, name="redeem-code"),
    path("verification/<int:pk>/decide/", views.decide_verification, name="decide-verification"),
    path("requests/<int:pk>/decide/", views.decide_request, name="decide-request"),
    path("reports/<int:pk>/decide/", views.decide_report, name="decide-report"),
    path("report/<slug:kind>/<int:pk>/", views.report, name="report"),
    path("users/<int:pk>/revoke/", views.revoke, name="revoke"),
    path("codes/", views.invite_codes, name="codes"),
    path("codes/<int:pk>/deactivate/", views.deactivate_code, name="deactivate-code"),
]
