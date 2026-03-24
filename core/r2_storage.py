"""Cloudflare R2 storage for E2B sandbox backups."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import AppConfig

logger = logging.getLogger(__name__)

# Maximum backup size: 500 MB
MAX_BACKUP_SIZE = 500 * 1024 * 1024


class R2Storage:
    """S3-compatible client for Cloudflare R2 sandbox backups."""

    def __init__(self, config: AppConfig):
        self._account_id = config.r2_account_id
        self._access_key = config.r2_access_key_id
        self._secret_key = config.r2_secret_access_key
        self._bucket = config.r2_bucket
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self._account_id and self._access_key and self._secret_key)

    def _get_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=f"https://{self._account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name="auto",
            )
        return self._client

    def upload_backup(self, agent_id: str, tar_bytes: bytes, requirements_txt: str = "") -> str:
        """Upload a tar.gz backup to R2. Returns the object key."""
        if len(tar_bytes) > MAX_BACKUP_SIZE:
            raise ValueError(
                f"Backup too large: {len(tar_bytes) / 1024 / 1024:.1f} MB "
                f"(max {MAX_BACKUP_SIZE / 1024 / 1024:.0f} MB)"
            )

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        key = f"sandboxes/{agent_id}/{ts}.tar.gz"
        latest_key = f"sandboxes/{agent_id}/latest.tar.gz"

        client = self._get_client()

        # Upload timestamped backup
        client.put_object(Bucket=self._bucket, Key=key, Body=tar_bytes)
        # Also overwrite "latest" pointer
        client.put_object(Bucket=self._bucket, Key=latest_key, Body=tar_bytes)

        # Upload requirements if provided
        if requirements_txt:
            req_key = f"sandboxes/{agent_id}/{ts}.requirements.txt"
            latest_req_key = f"sandboxes/{agent_id}/latest.requirements.txt"
            client.put_object(Bucket=self._bucket, Key=req_key, Body=requirements_txt.encode())
            client.put_object(
                Bucket=self._bucket, Key=latest_req_key, Body=requirements_txt.encode()
            )

        size_mb = len(tar_bytes) / 1024 / 1024
        logger.info(f"Uploaded backup for {agent_id}: {key} ({size_mb:.1f} MB)")
        return key

    def download_latest_backup(self, agent_id: str) -> tuple[bytes | None, str | None]:
        """Download latest backup. Returns (tar_bytes, requirements_txt) or (None, None)."""
        client = self._get_client()

        tar_bytes = None
        req_txt = None

        try:
            resp = client.get_object(Bucket=self._bucket, Key=f"sandboxes/{agent_id}/latest.tar.gz")
            tar_bytes = resp["Body"].read()
        except client.exceptions.NoSuchKey:
            logger.info(f"No backup found for agent {agent_id}")
            return None, None
        except Exception as e:
            logger.warning(f"Failed to download backup for {agent_id}: {e}")
            return None, None

        try:
            resp = client.get_object(
                Bucket=self._bucket, Key=f"sandboxes/{agent_id}/latest.requirements.txt"
            )
            req_txt = resp["Body"].read().decode()
        except Exception:
            pass  # requirements are optional

        size_mb = len(tar_bytes) / 1024 / 1024 if tar_bytes else 0
        logger.info(f"Downloaded backup for {agent_id} ({size_mb:.1f} MB)")
        return tar_bytes, req_txt

    def list_backups(self, agent_id: str, limit: int = 20) -> list[dict]:
        """List available backups for an agent."""
        client = self._get_client()
        prefix = f"sandboxes/{agent_id}/"

        try:
            resp = client.list_objects_v2(Bucket=self._bucket, Prefix=prefix, MaxKeys=100)
        except Exception as e:
            logger.warning(f"Failed to list backups for {agent_id}: {e}")
            return []

        backups = []
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            # Skip "latest" symlinks and requirements files
            if "/latest." in key or key.endswith(".requirements.txt"):
                continue
            backups.append(
                {
                    "key": key,
                    "size_bytes": obj["Size"],
                    "timestamp": obj["LastModified"].isoformat(),
                }
            )

        # Sort newest first, limit
        backups.sort(key=lambda b: b["timestamp"], reverse=True)
        return backups[:limit]

    def delete_backup(self, agent_id: str, key: str) -> bool:
        """Delete a specific backup."""
        # Ensure key belongs to this agent (prevent path traversal)
        if not key.startswith(f"sandboxes/{agent_id}/"):
            return False
        client = self._get_client()
        try:
            client.delete_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete backup {key}: {e}")
            return False
