from django.urls import path

from .views import (
    CompletedTasksView,
    CurrentTaskView,
    DeleteTaskView,
    DownloadTaskView,
    StartTaskView,
    StopTaskView,
    TaskListView,
    TaskResultsView,
)

urlpatterns = [
    path("", TaskListView.as_view(), name="task-list"),
    path("completed/", CompletedTasksView.as_view(), name="completed-tasks"),
    path("<int:task_id>/stop/", StopTaskView.as_view(), name="stop-task-by-id"),
    path("<int:task_id>/", DeleteTaskView.as_view(), name="delete-task"),
    path("start/", StartTaskView.as_view(), name="start-task"),
]