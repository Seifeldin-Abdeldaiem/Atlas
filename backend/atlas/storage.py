"""Private object storage for uploaded files (S3, Cloudflare R2 or MinIO).

Keys are `<org_id>/<dataset_id>/<random>`: no filenames, nothing guessable.
Objects are never public and are only reached through the API or worker.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from uuid import UUID

import boto3
from botocore.config import Config

from .config import get_settings


@lru_cache
def _client():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.storage_endpoint_url,
        region_name=s.storage_region,
        aws_access_key_id=s.storage_access_key_id,
        aws_secret_access_key=s.storage_secret_access_key,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def new_key(org_id: UUID, dataset_id: UUID) -> str:
    return f"{org_id}/{dataset_id}/{secrets.token_hex(16)}"


def put(key: str, data: bytes) -> None:
    s = get_settings()
    extra = {"ServerSideEncryption": s.storage_server_side_encryption} if s.storage_server_side_encryption else {}
    _client().put_object(Bucket=s.storage_bucket, Key=key, Body=data, ContentType="application/octet-stream", **extra)


def get(key: str) -> bytes:
    s = get_settings()
    response = _client().get_object(Bucket=s.storage_bucket, Key=key)
    body = response["Body"]
    try:
        # Never read more than an upload could legally be.
        data = body.read(s.max_upload_bytes + 1)
    finally:
        body.close()
    return data


def get_any(key: str) -> bytes:
    """A file Atlas wrote itself (an export), which may be larger than uploads."""
    s = get_settings()
    response = _client().get_object(Bucket=s.storage_bucket, Key=key)
    body = response["Body"]
    try:
        return body.read(s.max_upload_bytes * 8 + 1)
    finally:
        body.close()


def delete(key: str) -> None:
    _client().delete_object(Bucket=get_settings().storage_bucket, Key=key)
