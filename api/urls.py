from django.urls import path

from .views import HealthView, TargetAccountLoginView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health")
]