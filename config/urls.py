"""
URL configuration for the project.

Includes Swagger UI, ReDoc, and OpenAPI Schema endpoints.
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # Redirect root to Swagger UI documentation
    path("", RedirectView.as_view(url="/api/docs/", permanent=False)),

    # Admin
    path("admin/", admin.site.urls),

    # OpenAPI 3.0 Schema & Interactive Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui-alias"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # Application APIs
    path("api/", include("api.urls")),
    path("api/tasks/", include("tasks.urls")),
]
