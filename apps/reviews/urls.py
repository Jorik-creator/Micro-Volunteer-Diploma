from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path(
        "create/<int:request_pk>/<int:target_pk>/",
        views.CreateReviewView.as_view(),
        name="review-create",
    ),
]
