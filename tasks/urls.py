from django.urls import path

from .views import (
    CompletedTasksView,
    StartTaskView,
    StopTaskView,
    TaskListView,

)

urlpatterns = [
    path("", TaskListView.as_view(), name="task-list"),
    path("completed/", CompletedTasksView.as_view(), name="completed-tasks"),
    path("<int:task_id>/stop/", StopTaskView.as_view(), name="stop-task-by-id"),
    path("start/", StartTaskView.as_view(), name="start-task"),
]