from django.urls import path
from jobber_sync import views
from .views import jobber_oauth_start, jobber_oauth_callback
app_name = "jobber_sync"

urlpatterns = [
    path("start/", views.jobber_oauth_start, name="jobber_oauth_start"),
    path("callback/", views.jobber_oauth_callback, name="jobber_oauth_callback"),
]
