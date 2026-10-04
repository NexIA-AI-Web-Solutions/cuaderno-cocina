"""Commercial defaults without inserting rows during a read request."""
from cuaderno.models import SpaceProfile


def profile_for_space(space) -> SpaceProfile:
    try:
        return SpaceProfile.objects.get(space=space)
    except SpaceProfile.DoesNotExist:
        # Legacy/native Spaces may not yet have commercial configuration.
        # An explicit authorized save persists these defaults when needed.
        return SpaceProfile(space=space)
