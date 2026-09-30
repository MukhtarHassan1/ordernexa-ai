import asyncio
import json
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings


class ObjectStorage:
    def __init__(self) -> None:
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_root_user,
            aws_secret_access_key=settings.minio_root_password,
            region_name="us-east-1",
            config=Config(
                signature_version="s3v4",
            ),
        )

        self.bucket = settings.minio_bucket

    async def put_bytes(
        self,
        *,
        object_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )

    async def put_json(
        self,
        *,
        object_key: str,
        payload: dict[str, Any],
    ) -> None:
        raw = json.dumps(
            payload,
            indent=2,
            default=str,
        ).encode("utf-8")

        await self.put_bytes(
            object_key=object_key,
            data=raw,
            content_type="application/json",
        )

    async def get_bytes(
        self,
        object_key: str,
    ) -> bytes:
        response = await asyncio.to_thread(
            self.client.get_object,
            Bucket=self.bucket,
            Key=object_key,
        )

        return await asyncio.to_thread(
            response["Body"].read
        )

    async def exists(
        self,
        object_key: str,
    ) -> bool:
        try:
            await asyncio.to_thread(
                self.client.head_object,
                Bucket=self.bucket,
                Key=object_key,
            )

            return True

        except ClientError as exc:
            code = (
                exc.response
                .get("Error", {})
                .get("Code")
            )

            if code in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return False

            raise

    async def bucket_exists(self) -> bool:
        try:
            await asyncio.to_thread(
                self.client.head_bucket,
                Bucket=self.bucket,
            )

            return True

        except ClientError:
            return False


object_storage = ObjectStorage()