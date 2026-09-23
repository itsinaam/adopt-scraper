from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponseRedirect
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import permissions, serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .email_cleaner import process_csv_leads
from .models import CSVProcessTask, Task
from .serializers import (
    CompletedTaskSerializer,
    CSVProcessTaskSerializer,
    CSVProcessTaskUploadSerializer,
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
        queryset = Task.objects.filter(status=Task.Status.RUNNING)
        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            queryset = queryset.filter(user=request.user)

        running_tasks = list(queryset.order_by("-created_at", "-id"))

        return Response({
            "running_count": len(running_tasks),
            "tasks": TaskSerializer(running_tasks, many=True).data,
            "task": TaskSerializer(running_tasks[0]).data if running_tasks else None,
        })


class TaskListView(APIView):
    """
    Retrieves tasks. By default filters to ONLY RUNNING tasks. Use ?status=all for all tasks, or ?status=failed, ?status=completed.
    Regular users only see their own tasks; superusers can view all tasks or filter by ?user_id=.
    """

    @extend_schema(
        summary="List Scraping Tasks",
        description="Returns tasks list scoped to the authenticated user. By default only returns RUNNING tasks. Pass ?status=all to include FAILED/COMPLETED, or ?status=failed.",
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
        queryset = Task.objects.all().order_by("-created_at", "-id")

        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            queryset = queryset.filter(user=request.user)
        elif request.user and request.user.is_authenticated and request.user.is_superuser:
            user_id_param = request.query_params.get("user_id")
            if user_id_param and user_id_param.isdigit():
                queryset = queryset.filter(user_id=int(user_id_param))

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

        running_qs = Task.objects.filter(status=Task.Status.RUNNING)
        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            running_qs = running_qs.filter(user=request.user)
        running_count = running_qs.count()

        return Response({
            "running_count": running_count,
            "total": len(tasks),
            "tasks": TaskSerializer(tasks, many=True).data,
        })


class CompletedTasksView(APIView):
    """
    Retrieves scraping tasks filtered by status with download URLs and key metrics.
    """

    @extend_schema(
        summary="List Completed Scraping Tasks",
        description=(
            "Returns lightweight task records. Use ?status=completed, failed, running, "
            "or all. The default is completed."
        ),
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=["completed", "failed", "running", "all"],
                default="completed",
                description="Filter tasks by execution status.",
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="List of completed tasks",
                response=inline_serializer(
                    name="CompletedTasksResponse",
                    fields={
                        "total": serializers.IntegerField(),
                        "tasks": CompletedTaskSerializer(many=True),
                    },
                ),
            ),
            404: OpenApiResponse(description="Completed task not found"),
        },
        tags=["Tasks"],
    )
    def get(self, request, task_id: int = None):
        status_param = request.query_params.get("status", "completed").lower()
        valid_statuses = {
            "completed": Task.Status.COMPLETED,
            "failed": Task.Status.FAILED,
            "running": Task.Status.RUNNING,
        }
        if status_param != "all" and status_param not in valid_statuses:
            return Response(
                {"detail": "status must be one of: completed, failed, running, all."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        base_qs = Task.objects.all()
        if status_param != "all":
            base_qs = base_qs.filter(status=valid_statuses[status_param])
        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            base_qs = base_qs.filter(user=request.user)

        if task_id is not None:
            task = base_qs.filter(pk=task_id).first()
            if not task:
                return Response(
                    {"detail": "Task not found for the requested status filter."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            serializer = CompletedTaskSerializer(task, context={"request": request})
            return Response({"task": serializer.data}, status=status.HTTP_200_OK)

        queryset = base_qs.order_by("-completed_at", "-created_at")

        limit = request.query_params.get("limit")
        if limit and limit.isdigit():
            tasks = list(queryset[:int(limit)])
        else:
            tasks = list(queryset[:100])

        serializer = CompletedTaskSerializer(tasks, many=True, context={"request": request})
        return Response({
            "total": len(tasks),
            "tasks": serializer.data,
        }, status=status.HTTP_200_OK)


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
        queryset = Task.objects.all()
        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            queryset = queryset.filter(user=request.user)

        task = queryset.filter(pk=task_id).first()
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
        combinations_download_link = task.combinations_url or f"/api/tasks/{task.pk}/download/?file=combinations"
        data = {
            "task_id": task.pk,
            "task_name": task.task_name,
            "status": task.status,
            "account_email": task.account_email,
            "filters": task.filters,
            "total_scraped_leads": task.total_scraped_leads,
            "total_candidates_generated": task.total_candidates_generated,
            "total_verified_emails": task.total_verified_emails,
            "download_url": download_link,
            "combinations_download_url": combinations_download_link,
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
        queryset = Task.objects.all()
        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            queryset = queryset.filter(user=request.user)

        task = queryset.filter(pk=task_id).first()
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

        requested_file = request.query_params.get("file", "leads")
        if requested_file not in {"leads", "combinations"}:
            return Response(
                {"detail": "file must be either 'leads' or 'combinations'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        selected_path = task.result_path if requested_file == "leads" else task.combinations_path
        selected_url = task.result_url if requested_file == "leads" else task.combinations_url

        # 1. If stored in Supabase Storage or a direct URL is available
        if selected_path and selected_path.startswith("tasks/"):
            signed_url = supabase_storage.create_signed_url(selected_path, expires_in=3600)
            if signed_url:
                return HttpResponseRedirect(signed_url)

        if selected_url:
            return HttpResponseRedirect(selected_url)

        # 2. Fallback to local filesystem if available
        if selected_path:
            results_directory = (Path(settings.BASE_DIR) / "results").resolve()
            result_path = Path(selected_path).resolve()
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
        description=(
            "Creates and spawns a background Adapt.io scraping task. Set verification=true "
            "to verify email candidates; set verification=false to skip verification and "
            "receive separate leads and combinations CSV files."
        ),
        request=StartTaskRequestSerializer,
        examples=[
            OpenApiExample(
                "Standard Search Example with Task Name",
                summary="Lead Scraping with Task Name & Filters",
                description="Starts scraping with custom task_name and filter constraints.",
                value={
                    "task_name": "Tech Executives US & UK",
                    "verification": False,
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
                "Explicit Credentials Example",
                summary="Lead Scraping with Explicit Credentials",
                description="Example payload with custom task_name, explicit email and password.",
                value={
                    "task_name": "Finance Leaders Campaign",
                    "email": "umer@techfy.io",
                    "password": "your_adapt_password",
                    "verification": True,
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
                description="Starts scraping with task_name without filter constraints.",
                value={
                    "task_name": "Minimal Scraping Run",
                    "verification": True,
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
        task_name = serializer.validated_data.get("task_name", "")
        verification = serializer.validated_data.get("verification", True)

        now = timezone.now()
        task = Task.objects.create(
            user=request.user if request.user and request.user.is_authenticated else None,
            task_name=task_name,
            account_email=account_email,
            filters=filters,
            verification=verification,
            status=Task.Status.RUNNING,
            current_step="STARTING",
            progress=0,
            message="Task is starting...",
            logs=[
                {
                    "timestamp": now.isoformat(),
                    "message": f"Scraping task '{task_name or account_email}' initialized and queued.",
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


class RetryTaskView(APIView):
    """Retries a failed scraping task using its saved filters and account."""

    @extend_schema(
        summary="Retry Failed Scraping Task",
        description=(
            "Restarts a FAILED task with the same account and filters. "
            "Provide password in the request only when ADAPT_PASSWORD is not configured."
        ),
        request=inline_serializer(
            name="RetryTaskRequest",
            fields={
                "password": serializers.CharField(required=False, write_only=True),
            },
        ),
        responses={
            202: OpenApiResponse(description="Task retry accepted"),
            400: OpenApiResponse(description="Task is not failed or password is missing"),
            404: OpenApiResponse(description="Task not found"),
        },
        tags=["Tasks"],
    )
    def post(self, request, task_id: int):
        queryset = Task.objects.all()
        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            queryset = queryset.filter(user=request.user)

        task = queryset.filter(pk=task_id).first()
        if task is None:
            return Response(
                {"detail": "Task not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if task.status != Task.Status.FAILED:
            return Response(
                {"detail": "Only FAILED tasks can be retried.", "status": task.status},
                status=status.HTTP_400_BAD_REQUEST,
            )

        import os
        password = request.data.get("password") or os.getenv("ADAPT_PASSWORD", "").strip()
        if not password:
            return Response(
                {"detail": "Password is required in the request or ADAPT_PASSWORD environment variable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        task.status = Task.Status.RUNNING
        task.current_step = "STARTING"
        task.progress = 0
        task.message = "Task retry is starting..."
        task.error = ""
        task.completed_at = None
        task.total_scraped_leads = 0
        task.total_candidates_generated = 0
        task.total_verified_emails = 0
        task.verified_leads = []
        task.result_path = ""
        task.result_url = ""
        task.combinations_path = ""
        task.combinations_url = ""
        task.started_at = now
        task.add_log("Failed task retry initialized and queued.", step="RETRYING")
        task.save()

        start_task(task.id, password)

        return Response(
            {"detail": f"Task {task.id} retry started.", "task": TaskSerializer(task).data},
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
        queryset = Task.objects.filter(status=Task.Status.RUNNING)
        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            queryset = queryset.filter(user=request.user)

        if task_id is not None:
            task = queryset.filter(pk=task_id).first()
        else:
            task = queryset.first()

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


class DeleteTaskView(APIView):
    """
    Deletes a scraping task by ID.
    Regular users can only delete their own tasks; superusers can delete any task.
    """

    @extend_schema(
        summary="Delete Scraping Task",
        description="Permanently deletes a scraping task by ID. Regular users can only delete their own tasks.",
        responses={
            200: OpenApiResponse(
                description="Task deleted successfully",
                response=inline_serializer(
                    name="DeleteTaskResponse",
                    fields={
                        "detail": serializers.CharField(),
                        "task_id": serializers.IntegerField(),
                    },
                ),
            ),
            404: OpenApiResponse(description="Task not found or not owned by user"),
        },
        tags=["Tasks"],
    )
    def delete(self, request, task_id: int):
        queryset = Task.objects.all()
        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            queryset = queryset.filter(user=request.user)

        task = queryset.filter(pk=task_id).first()
        if task is None:
            return Response(
                {"detail": "Task not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        task.delete()
        return Response(
            {
                "detail": f"Task {task_id} has been deleted successfully.",
                "task_id": task_id,
            },
            status=status.HTTP_200_OK,
        )


class CSVProcessUploadView(APIView):
    """
    Uploads a CSV file of prospect leads, removes personal/free emails,
    preserves existing business emails, and generates a single standard professional
    email combination (first.last@domain) for contacts lacking a business email.
    """
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Upload and Process Leads CSV",
        description=(
            "Uploads a CSV file of leads. Automatically removes personal emails "
        ),
        request=CSVProcessTaskUploadSerializer,
        responses={
            201: CSVProcessTaskSerializer,
            400: OpenApiResponse(description="Validation error or invalid file"),
        },
        tags=["CSV Processing"],
    )
    def post(self, request):
        serializer = CSVProcessTaskUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        task_name = serializer.validated_data.get("task_name") or uploaded_file.name

        user = request.user if request.user and request.user.is_authenticated else None

        task = CSVProcessTask.objects.create(
            user=user,
            task_name=task_name,
            file_name=uploaded_file.name,
            status=CSVProcessTask.Status.PENDING,
        )

        try:
            process_csv_leads(uploaded_file, task)
        except Exception as exc:
            task.status = CSVProcessTask.Status.FAILED
            task.error = str(exc)
            task.add_log(f"Failed to process CSV: {exc}")
            task.completed_at = timezone.now()
            task.save(update_fields=["status", "error", "logs", "completed_at", "updated_at"])
            return Response(
                {"detail": f"Failed to process CSV file: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        output_serializer = CSVProcessTaskSerializer(task, context={"request": request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class CSVTaskListView(APIView):
    """
    Retrieves a list of CSV processing tasks.
    """

    @extend_schema(
        summary="List CSV Processing Tasks",
        description="Returns list of previously processed CSV tasks scoped to the user.",
        responses={
            200: inline_serializer(
                name="CSVTaskListResponse",
                fields={
                    "total": serializers.IntegerField(),
                    "tasks": CSVProcessTaskSerializer(many=True),
                },
            ),
        },
        tags=["CSV Processing"],
    )
    def get(self, request):
        queryset = CSVProcessTask.objects.all().order_by("-created_at")
        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            queryset = queryset.filter(user=request.user)

        status_param = request.query_params.get("status")
        if status_param and status_param.lower() != "all":
            queryset = queryset.filter(status=status_param.upper())

        limit = request.query_params.get("limit")
        if limit and limit.isdigit():
            tasks = list(queryset[:int(limit)])
        else:
            tasks = list(queryset[:50])

        serializer = CSVProcessTaskSerializer(tasks, many=True, context={"request": request})
        return Response({
            "total": len(tasks),
            "tasks": serializer.data,
        }, status=status.HTTP_200_OK)


class DownloadCSVTaskView(APIView):
    """
    Downloads or redirects to the CSV file generated by a completed CSV processing task.
    """

    @extend_schema(
        summary="Download CSV Task Result",
        description="Returns the processed CSV file or redirects to its signed Supabase storage URL.",
        responses={
            200: OpenApiResponse(description="Direct CSV file download stream"),
            302: OpenApiResponse(description="Redirect to signed Supabase Storage download URL"),
            404: OpenApiResponse(description="Task not found or result file missing"),
            409: OpenApiResponse(description="Task is still running or failed"),
        },
        tags=["CSV Processing"],
    )
    def get(self, request, task_id: int):
        queryset = CSVProcessTask.objects.all()
        if request.user and request.user.is_authenticated and not request.user.is_superuser:
            queryset = queryset.filter(user=request.user)

        task = queryset.filter(pk=task_id).first()
        if task is None:
            return Response(
                {"detail": "CSV processing task not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if task.status != CSVProcessTask.Status.COMPLETED:
            return Response(
                {"detail": f"The CSV task is {task.status.lower()} and not ready."},
                status=status.HTTP_409_CONFLICT,
            )

        # 1. If stored in Supabase Storage and result_url starts with http
        if task.result_url and task.result_url.startswith("http"):
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


