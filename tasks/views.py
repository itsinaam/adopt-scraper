from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponseRedirect
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Task
from .serializers import (
    StartTaskRequestSerializer,
    TaskResultsResponseSerializer,
    TaskSerializer,
)
from .services import start_task
from .storage import supabase_storage


class CurrentTaskView(APIView):
    """
    Retrieves all currently active RUNNING scraping tasks and their execution states.
    """

    @extend_schema(
        summary="Get Active Running Scraping Tasks",
        description="Returns all active RUNNING tasks (with their full logs and progress). Never returns FAILED or COMPLETED tasks.",
        responses={
            200: OpenApiResponse(
                description="Active running tasks",
                response=inline_serializer(
                    name="CurrentTaskResponse",
                    fields={
                        "running_count": serializers.IntegerField(),
                        "tasks": TaskSerializer(many=True),
                        "task": TaskSerializer(allow_null=True),
                    },
                ),
            )
        },
        tags=["Tasks"],
    )
    def get(self, request):
        running_tasks = list(Task.objects.filter(status=Task.Status.RUNNING).order_by("-created_at"))

        return Response({
            "running_count": len(running_tasks),
            "tasks": TaskSerializer(running_tasks, many=True).data,
            "task": TaskSerializer(running_tasks[0]).data if running_tasks else None,
        })


class TaskListView(APIView):
    """
    Retrieves tasks. By default filters to ONLY RUNNING tasks. Use ?status=all for all tasks, or ?status=failed, ?status=completed.
    """

    @extend_schema(
        summary="List Scraping Tasks",
        description="Returns tasks list. By default only returns RUNNING tasks. Pass ?status=all to include FAILED/COMPLETED, or ?status=failed.",
        responses={
            200: OpenApiResponse(
                description="List of tasks",
                response=inline_serializer(
                    name="TaskListResponse",
                    fields={
                        "running_count": serializers.IntegerField(),
                        "total": serializers.IntegerField(),
                        "tasks": TaskSerializer(many=True),
                    },
                ),
            )
        },
        tags=["Tasks"],
    )
    def get(self, request):
        status_param = request.query_params.get("status")
        queryset = Task.objects.all().order_by("-created_at")

        if status_param:
            if status_param.lower() != "all":
                queryset = queryset.filter(status=status_param.upper())
        else:
            # Default to RUNNING tasks only so FAILED/COMPLETED tasks are not included
            queryset = queryset.filter(status=Task.Status.RUNNING)

        limit = request.query_params.get("limit")
        if limit and limit.isdigit():
            tasks = list(queryset[:int(limit)])
        else:
            tasks = list(queryset[:50])

        running_count = Task.objects.filter(status=Task.Status.RUNNING).count()

        return Response({
            "running_count": running_count,
            "total": len(tasks),
            "tasks": TaskSerializer(tasks, many=True).data,
        })


class TaskResultsView(APIView):
    """
    Frontend-tailored endpoint returning full verified lead items and scraping metrics.
    """

    @extend_schema(
        summary="Get Task Results (For Frontend UI)",
        description=(
            "Returns detailed task metrics (applied filters, total scraped leads, "
            "candidate pairs generated, verified email count) and the complete JSON list "
            "of verified leads for easy table rendering in Frontend apps."
        ),
        responses={
            200: TaskResultsResponseSerializer,
            404: OpenApiResponse(description="Task not found"),
            409: OpenApiResponse(description="Task is still running and not yet completed"),
        },
        tags=["Tasks"],
    )
    def get(self, request, task_id: int):
        task = Task.objects.filter(pk=task_id).first()
        if task is None:
            return Response(
                {"detail": "Task not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if task.status != Task.Status.COMPLETED:
            return Response(
                {
                    "detail": "Task results are not ready yet.",
                    "status": task.status,
                    "progress": task.progress,
                    "current_step": task.current_step,
                },
                status=status.HTTP_409_CONFLICT,
            )

        download_link = task.result_url or f"/api/tasks/{task.pk}/download/"
        data = {
            "task_id": task.pk,
            "status": task.status,
            "account_email": task.account_email,
            "filters": task.filters,
            "total_scraped_leads": task.total_scraped_leads,
            "total_candidates_generated": task.total_candidates_generated,
            "total_verified_emails": task.total_verified_emails,
            "download_url": download_link,
            "completed_at": task.completed_at,
            "logs": task.logs or [],
            "verified_leads": task.verified_leads,
        }
        return Response(data, status=status.HTTP_200_OK)


class DownloadTaskView(APIView):
    """
    Downloads or redirects to the CSV file generated by a completed task.
    """

    @extend_schema(
        summary="Download Task Result CSV",
        description="Returns the CSV result file for a completed task or redirects to its signed Supabase storage URL.",
        responses={
            200: OpenApiResponse(description="Direct CSV file download stream"),
            302: OpenApiResponse(description="Redirect to signed Supabase Storage download URL"),
            404: OpenApiResponse(description="Task not found or result file missing"),
            409: OpenApiResponse(description="Task is still running or not completed"),
        },
        tags=["Tasks"],
    )
    def get(self, request, task_id: int):
        task = Task.objects.filter(pk=task_id).first()
        if task is None:
            return Response(
                {"detail": "Task not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if task.status != Task.Status.COMPLETED:
            return Response(
                {"detail": "The task result is not ready."},
                status=status.HTTP_409_CONFLICT,
            )

        # 1. If stored in Supabase Storage or result_url is available
        if task.result_path and task.result_path.startswith("tasks/"):
            signed_url = supabase_storage.create_signed_url(task.result_path, expires_in=3600)
            if signed_url:
                return HttpResponseRedirect(signed_url)

        if task.result_url:
            return HttpResponseRedirect(task.result_url)

        # 2. Fallback to local filesystem if available
        if task.result_path:
            results_directory = (Path(settings.BASE_DIR) / "results").resolve()
            result_path = Path(task.result_path).resolve()
            if results_directory in result_path.parents and result_path.is_file():
                return FileResponse(
                    result_path.open("rb"),
                    as_attachment=True,
                    filename=result_path.name,
                    content_type="text/csv",
                )

        return Response(
            {"detail": "Task result file is unavailable."},
            status=status.HTTP_404_NOT_FOUND,
        )


class StartTaskView(APIView):
    """
    Initiates a new background scraping task with the provided Adapt.io credentials and filters.
    """

    @extend_schema(
        summary="Start Lead Scraping Task",
        description="Creates and spawns a background Adapt.io scraping & MailTester verification task.",
        request=StartTaskRequestSerializer,
        examples=[
            OpenApiExample(
                "Filters Only Example (Environment Credentials)",
                summary="Lead Scraping with Only Filters",
                description="Starts scraping using credentials (ADAPT_EMAIL and ADAPT_PASSWORD) configured in environment (.env).",
                value={
                    "filters": {
                        "job_titles": ["CEO", "Founder", "Managing Director"],
                        "industries": ["Information Technology and Services", "Computer Software"],
                        "locations": ["United States", "United Kingdom"],
                        "employee_counts": ["25 - 100", "100 - 250"],
                    },
                },
                request_only=True,
            ),
            OpenApiExample(
                "Standard Search Example",
                summary="Lead Scraping with Filters & Explicit Credentials",
                description="Example payload with explicit email and password.",
                value={
                    "email": "umer@techfy.io",
                    "password": "your_adapt_password",
                    "filters": {
                        "job_titles": ["CFO", "Chief Financial Officer"],
                        "industries": ["Software", "Information Technology"],
                        "locations": ["Lahore", "United States"],
                        "employee_counts": ["0 - 25", "25 - 100"],
                    },
                },
                request_only=True,
            ),
            OpenApiExample(
                "Minimal Search Example",
                summary="Minimal Search without Filters",
                description="Starts scraping without any filter constraints.",
                value={
                    "filters": {},
                },
                request_only=True,
            ),
        ],
        responses={
            202: OpenApiResponse(
                description="Task accepted and started in background",
                response=inline_serializer(
                    name="StartTaskResponse",
                    fields={"task": TaskSerializer()},
                ),
            ),
            400: OpenApiResponse(description="Validation error in payload"),
        },
        tags=["Tasks"],
    )
    def post(self, request):
        serializer = TaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account_email = serializer.validated_data["account_email"]
        password = serializer.validated_data["password"]
        filters = serializer.validated_data.get("filters", {})

        now = timezone.now()
        task = Task.objects.create(
            account_email=account_email,
            filters=filters,
            status=Task.Status.RUNNING,
            current_step="STARTING",
            progress=0,
            message="Task is starting...",
            logs=[
                {
                    "timestamp": now.isoformat(),
                    "message": "Scraping task initialized and queued.",
                    "step": "STARTING",
                }
            ],
            started_at=now,
        )

        start_task(task.id, password)

        return Response(
            {"task": TaskSerializer(task).data},
            status=status.HTTP_202_ACCEPTED,
        )


class StopTaskView(APIView):
    """
    Stops the currently running scraping task or a specific task by ID.
    """

    @extend_schema(
        summary="Stop Scraping Task",
        description="Cancels and marks a running scraping task as STOPPED/FAILED so a new task can be started.",
        request=None,
        responses={
            200: OpenApiResponse(
                description="Task stopped successfully",
                response=inline_serializer(
                    name="StopTaskResponse",
                    fields={
                        "detail": serializers.CharField(),
                        "task": TaskSerializer(),
                    },
                ),
            ),
            404: OpenApiResponse(description="No running task found"),
        },
        tags=["Tasks"],
    )
    def post(self, request, task_id: int = None):
        if task_id is not None:
            task = Task.objects.filter(pk=task_id, status=Task.Status.RUNNING).first()
        else:
            task = Task.objects.filter(status=Task.Status.RUNNING).first()

        if task is None:
            return Response(
                {"detail": "No running task found to stop."},
                status=status.HTTP_404_NOT_FOUND,
            )

        task.status = Task.Status.FAILED
        task.current_step = "STOPPED"
        task.message = "Task was stopped by user."
        task.error = "Manually stopped by user."
        task.completed_at = timezone.now()
        task.add_log("Task was stopped by user.", step="STOPPED")
        task.save(
            update_fields=[
                "status",
                "current_step",
                "message",
                "error",
                "logs",
                "completed_at",
                "updated_at",
            ]
        )

        return Response(
            {
                "detail": f"Task {task.pk} has been stopped.",
                "task": TaskSerializer(task).data,
            },
            status=status.HTTP_200_OK,
        )