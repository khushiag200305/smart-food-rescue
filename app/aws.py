"""Shared boto3 clients. On EC2 the IAM role supplies credentials, so no keys are needed."""
import functools

from flask import current_app


@functools.lru_cache(maxsize=None)
def _client(service, region):
    import boto3  # imported lazily so local development works without AWS

    return boto3.client(service, region_name=region)


def client(service):
    return _client(service, current_app.config["AWS_REGION"])
