from django.urls import path

from .views import (
    CurrentTaskView,
    DownloadTaskView,
    StartTaskView,
    StopTaskView,
    TaskListView,
    TaskResultsView,
)

urlpatterns = [
    path("", TaskListView.as_view(), name="task-list"),
    path("current/", CurrentTaskView.as_view(), name="current-task"),
    path("running/", CurrentTaskView.as_view(), name="running-tasks"),
    path("<int:task_id>/download/", DownloadTaskView.as_view(), name="download-task"),
    path("<int:task_id>/results/", TaskResultsView.as_view(), name="task-results"),
    path("<int:task_id>/stop/", StopTaskView.as_view(), name="stop-task-by-id"),
    path("stop/", StopTaskView.as_view(), name="stop-current-task"),
    path("start/", StartTaskView.as_view(), name="start-task"),
]