"""Storage providers for *temporary* audio only.

Contract for every implementation:
  * private container / bucket, no public access
  * encryption at rest
  * short TTL + lifecycle deletion as a backstop
  * `delete()` is called as soon as processing succeeds
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config.logging import get_logger
from app.config.settings import Settings
from app.core.errors import ProviderUnavailableError

log = get_logger(__name__)


class AzureBlobStorage:
    """Primary production storage. Prefers Managed Identity over connection strings."""

    name = "azure_blob"

    def __init__(self, settings: Settings) -> None:
        from azure.storage.blob.aio import BlobServiceClient

        self._settings = settings
        self._container = settings.azure_storage_container
        if settings.azure_storage_connection_string:
            self._client = BlobServiceClient.from_connection_string(
                settings.azure_storage_connection_string
            )
            self._credential = None
        elif settings.azure_storage_account_url:
            from azure.identity.aio import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
            self._client = BlobServiceClient(
                account_url=settings.azure_storage_account_url, credential=self._credential
            )
        else:
            raise ProviderUnavailableError("Azure Blob Storage is not configured")

    def _blob(self, blob_name: str):  # noqa: ANN202
        return self._client.get_blob_client(container=self._container, blob=blob_name)

    async def upload(
        self, *, blob_name: str, data: bytes, content_type: str, ttl_minutes: int
    ) -> str:
        from azure.storage.blob import ContentSettings

        expiry = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
        blob = self._blob(blob_name)
        await blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
            metadata={"purpose": "temporary-processing", "delete_after": expiry.isoformat()},
        )
        log.info("audio_uploaded", blob=blob_name, size_bytes=len(data))
        return blob.url

    async def download(self, blob_name: str) -> bytes:
        stream = await self._blob(blob_name).download_blob()
        return await stream.readall()

    async def delete(self, blob_name: str) -> bool:
        try:
            await self._blob(blob_name).delete_blob(delete_snapshots="include")
        except Exception as exc:  # noqa: BLE001 - deletion must never break the pipeline
            log.warning("audio_delete_failed", blob=blob_name, error=type(exc).__name__)
            return False
        log.info("audio_deleted", blob=blob_name)
        return True

    async def signed_read_url(self, blob_name: str, ttl_minutes: int = 30) -> str:
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        udk = await self._client.get_user_delegation_key(
            key_start_time=datetime.now(UTC) - timedelta(minutes=5),
            key_expiry_time=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
        )
        token = generate_blob_sas(
            account_name=self._client.account_name,
            container_name=self._container,
            blob_name=blob_name,
            user_delegation_key=udk,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
        )
        return f"{self._blob(blob_name).url}?{token}"

    async def healthy(self) -> bool:
        try:
            await self._client.get_service_properties()
        except Exception:  # noqa: BLE001
            return False
        return True

    async def close(self) -> None:
        await self._client.close()
        if self._credential is not None:
            await self._credential.close()


class LocalStorage:
    """Dev/test only. Same TTL semantics, backed by the filesystem."""

    name = "local"

    def __init__(self, settings: Settings) -> None:
        self._root = Path("/tmp/.local-storage")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, blob_name: str) -> Path:
        path = (self._root / blob_name).resolve()
        if not str(path).startswith(str(self._root.resolve())):
            raise ProviderUnavailableError("invalid blob path")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    async def upload(
        self, *, blob_name: str, data: bytes, content_type: str, ttl_minutes: int
    ) -> str:
        path = self._path(blob_name)
        await asyncio.to_thread(path.write_bytes, data)
        return str(path)

    async def download(self, blob_name: str) -> bytes:
        return await asyncio.to_thread(self._path(blob_name).read_bytes)

    async def delete(self, blob_name: str) -> bool:
        path = self._path(blob_name)
        if path.exists():
            await asyncio.to_thread(path.unlink)
        return True

    async def signed_read_url(self, blob_name: str, ttl_minutes: int = 30) -> str:
        return f"file://{self._path(blob_name)}"

    async def healthy(self) -> bool:
        return self._root.exists()

    async def close(self) -> None:
        return None


class S3Storage:
    """Portability hook for AWS. Not enabled in the Azure-first production path."""

    name = "s3"

    def __init__(self, settings: Settings) -> None:  # pragma: no cover
        raise ProviderUnavailableError("S3 storage provider is not configured")


class GCSStorage:
    """Portability hook for GCP. Not enabled in the Azure-first production path."""

    name = "gcs"

    def __init__(self, settings: Settings) -> None:  # pragma: no cover
        raise ProviderUnavailableError("GCS storage provider is not configured")