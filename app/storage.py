"""File storage: AWS S3 in the cloud, a local ./uploads folder during development.

On EC2 no access keys are needed: boto3 picks up temporary credentials from the
IAM role attached to the instance (see deploy/iam-policy.json).
The bucket stays private; pages show images through short-lived presigned URLs.
"""
import os
import uuid

from flask import current_app, url_for

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
DOC_EXTENSIONS = IMAGE_EXTENSIONS | {"pdf"}


def allowed_file(filename, allowed=IMAGE_EXTENSIONS):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def _s3():
    import boto3  # imported lazily so local development works without AWS

    return boto3.client("s3", region_name=current_app.config["AWS_REGION"])


def upload_file(file_storage, folder="food"):
    """Save an uploaded file and return its storage key, e.g. 'food/3f2a....jpg'."""
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    key = f"{folder}/{uuid.uuid4().hex}.{ext}"  # random name: no clashes, no user-controlled paths
    bucket = current_app.config.get("S3_BUCKET")

    if bucket:
        _s3().upload_fileobj(
            file_storage,
            bucket,
            key,
            ExtraArgs={"ContentType": file_storage.mimetype or "application/octet-stream"},
        )
    else:
        path = os.path.join(current_app.config["LOCAL_UPLOAD_DIR"], key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_storage.save(path)
    return key


def file_url(key, expires=3600):
    """URL a browser can use to display the file (presigned for private S3 buckets)."""
    if not key:
        return None
    bucket = current_app.config.get("S3_BUCKET")
    if bucket:
        return _s3().generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires
        )
    return url_for("main.uploaded_file", key=key)


def delete_file(key):
    if not key:
        return
    bucket = current_app.config.get("S3_BUCKET")
    if bucket:
        _s3().delete_object(Bucket=bucket, Key=key)
    else:
        path = os.path.join(current_app.config["LOCAL_UPLOAD_DIR"], key)
        if os.path.exists(path):
            os.remove(path)
