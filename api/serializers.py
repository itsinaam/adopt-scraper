from rest_framework import serializers


class TargetAccountLoginSerializer(serializers.Serializer):
    """
    Serializer for validating Adapt.io user login credentials.
    """
    email = serializers.EmailField(
        required=True,
        help_text="Adapt.io account email address",
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        required=True,
        help_text="Adapt.io account password",
    )


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField(default="ok", help_text="Service health status")