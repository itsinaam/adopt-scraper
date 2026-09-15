from django.urls import path

from .auth_views import UserLoginView, UserMeView
from .views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/login/", UserLoginView.as_view(), name="user-login"),
    path("auth/me/", UserMeView.as_view(), name="user-me"),
]