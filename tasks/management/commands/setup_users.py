from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

User = get_user_model()

USERS_TO_CREATE = [
    {
        "username": "admin",
        "email": "admin@adapt.io",
        "password": "AdminSecure2026!",
        "is_staff": True,
        "is_superuser": True,
        "role": "Administrator (Full Access)",
    },
    {
        "username": "user1",
        "email": "user1@adapt.io",
        "password": "User1Secure2026!",
        "is_staff": True,
        "is_superuser": False,
        "role": "Standard User 1 (Isolated Data)",
    },
    {
        "username": "user2",
        "email": "user2@adapt.io",
        "password": "User2Secure2026!",
        "is_staff": True,
        "is_superuser": False,
        "role": "Standard User 2 (Isolated Data)",
    },
]


class Command(BaseCommand):
    help = "Creates 1 admin and 2 standard users with auth tokens idempotently"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Setting up platform users..."))

        results = []
        for user_data in USERS_TO_CREATE:
            username = user_data["username"]
            email = user_data["email"]
            password = user_data["password"]
            is_staff = user_data["is_staff"]
            is_superuser = user_data["is_superuser"]

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "is_staff": is_staff,
                    "is_superuser": is_superuser,
                },
            )

            # Update password and flags
            user.set_password(password)
            user.email = email
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.is_active = True
            user.save()

            # Ensure Auth Token exists
            token, _ = Token.objects.get_or_create(user=user)

            status_str = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{status_str}] User: {username} | Email: {email} | Role: {user_data['role']}"
                )
            )
            self.stdout.write(f"           Token: {token.key}")

            results.append({
                "username": username,
                "email": email,
                "password": password,
                "token": token.key,
                "role": user_data["role"],
            })

        self.stdout.write(self.style.SUCCESS("\nAll users configured successfully."))

