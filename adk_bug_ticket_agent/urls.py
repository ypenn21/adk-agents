from django.urls import path
from . import views

urlpatterns = [
    path("", views.interact_with_agent, name="interact_root"),
    path("interact/", views.interact_with_agent, name="interact_with_agent"),
    path("chat/", views.interact_with_agent, name="chat"),
]
