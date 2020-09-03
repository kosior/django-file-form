import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files import uploadedfile
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from django.utils.module_loading import import_string

from .util import ModelManager, get_upload_path


class UploadedFileManager(ModelManager):
    def delete_unused_files(self, delete=True, now=None):
        deleted_files = []

        for t in self.get_queryset():
            if t.must_be_deleted(now):
                deleted_files.append(Path(t.uploaded_file.name).name)

                if delete:
                    t.delete()

        temp_path = get_upload_path()

        for f in temp_path.iterdir():
            basename = f.name

            if not self.get_for_file(basename):
                deleted_files.append(basename)

                if delete:
                    f.unlink()

        return deleted_files

    def get_for_file(self, filename):
        path = get_upload_path().joinpath(filename)
        return self.try_get(uploaded_file=path)


def get_upload_to(instance, filename):
    # Full path including filename is needed for custom storage backends.
    path = getattr(settings, 'FILE_FORM_UPLOAD_DIR', 'temp_uploads')
    return os.path.join(path, filename)


if hasattr(settings, 'FILE_FORM_TEMP_STORAGE'):
    storage_class = import_string(settings.FILE_FORM_TEMP_STORAGE)
else:
    storage_class = FileSystemStorage


class UploadedFile(models.Model):
    created = models.DateTimeField(default=timezone.now)
    uploaded_file = models.FileField(max_length=255, storage=storage_class(), upload_to=get_upload_to)
    original_filename = models.CharField(max_length=255)
    field_name = models.CharField(max_length=255, null=True, blank=True)
    file_id = models.CharField(max_length=40)
    form_id = models.CharField(max_length=40)

    objects = UploadedFileManager()

    class Meta(object):
        # Query string to get back existing uploaded file is using form_id and field_name
        index_together = (("form_id", "field_name"),)

    def __str__(self):
        return str(self.original_filename or '')

    def delete(self, *args, **kwargs):
        if self.uploaded_file and self.uploaded_file.storage.exists(self.uploaded_file.name):
            self.uploaded_file.delete()

        super(UploadedFile, self).delete(*args, **kwargs)

    def must_be_deleted(self, now=None):
        now = now or timezone.now()

        return (now - self.created).days >= 1

    def get_uploaded_file(self):
        return UploadedFileWithId(
            file=self.uploaded_file,
            name=self.original_filename,
            file_id=self.file_id
        )


class UploadedFileWithId(uploadedfile.UploadedFile):
    def __init__(self, file_id, **kwargs):
        super(UploadedFileWithId, self).__init__(**kwargs)

        self.file_id = file_id
        self.size = self.file.size

        self.is_placeholder = False
        self.is_s3direct = False

    def get_values(self):
        return dict(id=self.file_id, name=self.name, size=self.size)


class PlaceholderUploadedFile(object):
    def __init__(self, name, file_id=None, size=None):
        self.name = name
        self.file_id = file_id or uuid.uuid4().hex
        if size is None:
            self.size = os.path.getsize(self.name)
        else:
            self.size = size

        self.is_placeholder = True
        self.is_s3direct = False

    def get_values(self):
        return dict(id=self.file_id, placeholder=True, name=self.name, size=self.size)


try:
    from storages.backends.s3boto3 import S3Boto3Storage, S3Boto3StorageFile
    from storages.utils import setting

    class S3UploadedFileWithId(S3Boto3StorageFile):
        def __init__(self, file_id, name, original_name, size, **kwargs):
            boto_storage = S3Boto3Storage(
                bucket_name=setting('AWS_STORAGE_BUCKET_NAME'),
                endpoint_url=setting('AWS_S3_ENDPOINT_URL'),
                access_key=setting('AWS_S3_ACCESS_KEY_ID', setting('AWS_ACCESS_KEY_ID')),
                secret_key=setting('AWS_S3_SECRET_ACCESS_KEY', setting('AWS_SECRET_ACCESS_KEY'))
            )

            super(S3UploadedFileWithId, self).__init__(
                name=name,
                mode='rb',
                storage=boto_storage,
                **kwargs
            )
            self.file_id = file_id
            self.original_name = original_name
            # self.size is derived from S3boto3StorageFile
            # but size is passed for consistency, and potentially
            # for validation
            self.is_placeholder = False
            self.is_s3direct = True

        def get_values(self):
            return dict(id=self.file_id, placeholder=False, name=self.name, size=self.size)

except (ImportError, ImproperlyConfigured):
    # S3 is an optional feature but we keep the symbol
    class S3UploadedFileWithId(object):
        pass
