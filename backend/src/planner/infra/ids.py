import uuid

import uuid_utils


def new_id() -> uuid.UUID:
    """UUIDv7: time-ordered, safe as a dedupe key and index-friendly."""
    return uuid.UUID(str(uuid_utils.uuid7()))
