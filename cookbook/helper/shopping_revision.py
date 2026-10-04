"""Opaque shopping revisions retain PostgreSQL microseconds across JS clients."""
import hashlib
from datetime import timezone


def shopping_revision(entry):
    timestamp = entry.updated_at.astimezone(timezone.utc).isoformat(timespec='microseconds')
    return hashlib.sha256(f'{entry.pk}:{timestamp}'.encode()).hexdigest()
