from django.urls import path

from . import views

app_name = "conversations"

urlpatterns = [
    path("", views.conversation_list, name="list"),
    path("<int:pk>/", views.conversation_detail, name="detail"),
    path("<int:pk>/messages/", views.messages_json, name="messages"),
    path("<int:pk>/share-phone/", views.share_phone, name="share-phone"),
]
