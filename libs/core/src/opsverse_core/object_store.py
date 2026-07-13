import io
from urllib.parse import urlparse

from minio import Minio

from opsverse_core.settings import Settings


class ObjectStore:
    """Thin sync wrapper over MinIO/S3. Call from async code via
    anyio.to_thread.run_sync — the client itself is blocking."""

    def __init__(self, settings: Settings) -> None:
        parsed = urlparse(settings.minio_endpoint)
        self._client = Minio(
            parsed.netloc,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=parsed.scheme == "https",
        )
        self.bucket = settings.minio_bucket_raw

    def ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)

    def put_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        self.ensure_bucket()
        self._client.put_object(self.bucket, key, io.BytesIO(data), len(data), content_type)

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
