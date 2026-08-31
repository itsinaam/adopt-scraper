from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from scraper.adapt_io.account import authenticate_account_credentials
from .serializers import HealthResponseSerializer, TargetAccountLoginSerializer


class HealthView(APIView):
    """
    Service health check endpoint.
    """

    @extend_schema(
        summary="Health Check",
        description="Verify service availability and responsiveness.",
        responses={200: HealthResponseSerializer},
        tags=["System"],
    )
    def get(self, request):
        return Response({"status": "ok"})


class TargetAccountLoginView(APIView):
    """
    Validates Adapt.io credentials using a headless browser session.
    """

    @extend_schema(
        summary="Authenticate Adapt.io Credentials",
        description="Verifies Adapt.io account email and password by simulating login through Playwright.",
        request=TargetAccountLoginSerializer,
        responses={
            200: OpenApiResponse(
                description="Authentication successful",
                response=inline_serializer(
                    name="TargetAccountLoginSuccessResponse",
                    fields={"email": serializers.EmailField(), "status": serializers.CharField()},
                ),
            ),
            400: OpenApiResponse(description="Invalid request payload"),
            401: OpenApiResponse(description="Authentication failed with Adapt.io"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = TargetAccountLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        try:
            authenticate_account_credentials(
                email=email,
                password=password,
            )
        except Exception:
            return Response(
                {"detail": "Unable to authenticate with Adapt.io."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "email": email,
                "status": "authenticated",
            },
            status=status.HTTP_200_OK,
        )