from django.urls import path
from . import views

urlpatterns = [
    path('interact/', views.interact_with_agent, name='interact_with_agent'),
    path('chat/', views.chat_view, name='chat'),
]
