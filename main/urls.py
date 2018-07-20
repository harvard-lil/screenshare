from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path('slack_event', views.slack_event),
    path('', TemplateView.as_view(template_name='index.html'), name='index'),
]