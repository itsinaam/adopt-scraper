import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from supabase import Client, create_client
except ImportError:
    Client = None
    create_client = None


class SupabaseStorageService:
    """
    Production-ready wrapper for managing file uploads and downloads
    in Supabase Storage buckets.
    """

    def __init__(self):
        self.url = os.getenv("SUPABASE_URL", "").strip()
        self.key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_KEY")
            or ""
        ).strip()
        self.bucket_name = os.getenv("SUPABASE_STORAGE_BUCKET", "results").strip()
        self._client: Optional[Client] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.key and create_client is not None)

    def get_client(self) -> Optional[Client]:
        if not self.is_configured:
            return None
        if self._client is None:
            self._client = create_client(self.url, self.key)
        return self._client

    def ensure_bucket_exists(self) -> None:
        client = self.get_client()
        if not client:
            return
        try:
            buckets = client.storage.list_buckets()
            existing_bucket_names = [b.name for b in buckets] if buckets else []
            if self.bucket_name not in existing_bucket_names:
                client.storage.create_bucket(
                    self.bucket_name,
                    options={"public": False},
                )
                logger.info("Created Supabase storage bucket: %s", self.bucket_name)
        except Exception as exc:
            logger.warning("Could not auto-verify bucket %s: %s", self.bucket_name, exc)

    def upload_file(
        self,
        file_path: Path | str,
        destination_name: str,
        content_type: str = "text/csv",
    ) -> dict[str, str]:
        """
        Uploads a local file to the configured Supabase Storage bucket.
        Returns a dict containing 'storage_path' and 'signed_url' / 'public_url'.
        """
        client = self.get_client()
        if not client:
            logger.warning("Supabase storage is not configured. Skipping remote upload.")
            return {}

        self.ensure_bucket_exists()

        path_obj = Path(file_path)
        if not path_obj.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        storage_path = f"tasks/{destination_name}"

        with open(path_obj, "rb") as f:
            file_bytes = f.read()

        try:
            # Upload (upsert if already exists)
            client.storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=file_bytes,
                file_options={
                    "content-type": content_type,
                    "upsert": "true",
                },
            )
            logger.info("Successfully uploaded %s to Supabase storage (%s)", destination_name, storage_path)
        except Exception as exc:
            logger.error("Failed to upload %s to Supabase storage: %s", destination_name, exc)
            raise

        download_url = self.create_signed_url(storage_path, expires_in=3600 * 24)
        return {
            "storage_path": storage_path,
            "url": download_url or "",
        }

    def create_signed_url(self, storage_path: str, expires_in: int = 3600) -> Optional[str]:
        """
        Generates a secure temporary signed URL for downloading a file.
        """
        client = self.get_client()
        if not client:
            return None

        try:
            response = client.storage.from_(self.bucket_name).create_signed_url(
                path=storage_path,
                expires_in=expires_in,
            )
            if isinstance(response, dict) and "signedURL" in response:
                return response["signedURL"]
            if isinstance(response, str):
                return response
            if hasattr(response, "signed_url"):
                return response.signed_url
            if hasattr(response, "signedURL"):
                return response.signedURL
            return str(response)
        except Exception as exc:
            logger.error("Failed to generate signed URL for %s: %s", storage_path, exc)
            return None


supabase_storage = SupabaseStorageService()
