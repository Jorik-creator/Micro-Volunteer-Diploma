from django.urls import path

from . import views

app_name = "requests"

urlpatterns = [
    # List & map
    path("", views.HelpRequestListView.as_view(), name="list"),
    path("map/", views.MapView.as_view(), name="map"),
    path("map/data/", views.map_data, name="map-data"),
    # Recipient: create / my requests
    path("create/", views.HelpRequestCreateView.as_view(), name="create"),
    path("my/", views.MyRequestsView.as_view(), name="my-requests"),
    # Detail & edit
    path("<int:pk>/", views.HelpRequestDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.HelpRequestUpdateView.as_view(), name="edit"),
    # JSON endpoints
    path("<int:pk>/status/", views.request_status, name="status"),
    # Actions
    path("<int:pk>/cancel/", views.cancel_request, name="cancel"),
    path("<int:pk>/complete/", views.complete_request, name="complete"),
    path("<int:pk>/respond/", views.respond_to_request, name="respond"),
    # Recipient: accept / reject responses
    path("responses/<int:response_id>/accept/", views.accept_volunteer, name="accept"),
    path("responses/<int:response_id>/reject/", views.reject_volunteer, name="reject"),
]
