from django.urls import path
from . import views

urlpatterns = [
    path('interact/', views.interact_with_agent, name='interact_with_agent'),
    path('new_interact/', views.new_interact_with_agent, name='new_interact_with_agent'),
]