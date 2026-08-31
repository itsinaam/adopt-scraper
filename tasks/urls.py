from django.urls import path

from .views import (
    CurrentTaskView,
    DownloadTaskView,
    StartTaskView,
    TaskResultsView,
)

urlpatterns = [
    path("current/", CurrentTaskView.as_view(), name="current-task"),
    path("<int:task_id>/download/", DownloadTaskView.as_view(), name="download-task"),
    path("<int:task_id>/results/", TaskResultsView.as_view(), name="task-results"),
    path("start/", StartTaskView.as_view(), name="start-task"),
]