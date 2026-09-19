from django.urls import path

from .views import (
    CSVProcessUploadView,
    CSVTaskListView,
    CompletedTasksView,
    DeleteTaskView,
    RetryTaskView,
    StartTaskView,
    StopTaskView,
    TaskListView,
)

urlpatterns = [
    path("", TaskListView.as_view(), name="task-list"),
    path("completed/", CompletedTasksView.as_view(), name="completed-tasks"),
    path("<int:task_id>/stop/", StopTaskView.as_view(), name="stop-task-by-id"),
    path("<int:task_id>/retry/", RetryTaskView.as_view(), name="retry-task-by-id"),
    path("<int:task_id>/", DeleteTaskView.as_view(), name="delete-task"),
    path("start/", StartTaskView.as_view(), name="start-task"),
    # CSV Upload, Cleaning & Combinations Endpoints
    path("process-csv/", CSVProcessUploadView.as_view(), name="process-csv"),
    path("csv-tasks/", CSVTaskListView.as_view(), name="csv-task-list")
]