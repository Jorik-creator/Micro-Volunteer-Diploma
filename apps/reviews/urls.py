from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path(
        "create/<int:request_pk>/",
        views.CreateReviewView.as_view(),
        name="review-create",
    ),
    path("list/<int:user_pk>/", views.ReviewListView.as_view(), name="review-list"),
]
