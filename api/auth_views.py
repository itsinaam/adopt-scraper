from django.contrib.auth import authenticate, get_user_model
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=True,
        help_text="User email address",
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
        help_text="User password",
    )


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    is_staff = serializers.BooleanField()
    is_superuser = serializers.BooleanField()


class UserLoginView(APIView):
    """
    Authenticates a user using email and password, returning an authentication Token.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="User Login",
        description="Authenticates credentials using email and password, and returns an API Token.",
        auth=[],
        request=LoginRequestSerializer,
        responses={
            200: LoginResponseSerializer,
            400: OpenApiResponse(description="Invalid request or validation error"),
            401: OpenApiResponse(description="Invalid email or password"),
            403: OpenApiResponse(description="User account disabled"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        password = serializer.validated_data["password"]

        user_obj = User.objects.filter(email__iexact=email).first()
        if not user_obj:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = authenticate(request, username=user_obj.username, password=password)
        if not user:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"detail": "User account is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )

        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            "token": token.key,
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
        }, status=status.HTTP_200_OK)


class UserMeView(APIView):
    """
    Returns profile information for the currently authenticated user.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get Current User Profile",
        description="Returns username, email, role, and permission flags for the authenticated user.",
        responses={
            200: LoginResponseSerializer,
            401: OpenApiResponse(description="Unauthorized"),
        },
        tags=["Authentication"],
    )
    def get(self, request):
        user = request.user
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "token": token.key,
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": True,
            "is_superuser": user.is_superuser,
        })
