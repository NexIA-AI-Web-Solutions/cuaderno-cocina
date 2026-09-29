"""Bound native import buffers before creating logs or starting workers."""
import io

from django.conf import settings


class ImportUploadTooLarge(ValueError):
    pass


def import_upload_buffers(uploads):
    uploads = list(uploads)
    maximum = getattr(settings, "CUADERNO_IMPORT_MAX_BYTES", 50 * 1024 * 1024)
    maximum_files = getattr(settings, "CUADERNO_IMPORT_MAX_FILES", 100)
    message = "La importación supera el límite de tamaño o número de archivos."
    if len(uploads) > maximum_files or sum(upload.size for upload in uploads) > maximum:
        raise ImportUploadTooLarge(message)
    files, total = [], 0
    for upload in uploads:
        buffer = io.BytesIO()
        # Do not trust metadata alone; enforce the aggregate while streaming.
        for chunk in upload.chunks(chunk_size=64 * 1024):
            total += len(chunk)
            if total > maximum:
                raise ImportUploadTooLarge(message)
            buffer.write(chunk)
        buffer.seek(0)
        files.append({"file": buffer, "name": upload.name})
    return files
