import uuid


def as_uuid(value):
    """
    A record id from a request, or None if it is not a valid id.

    Every LexDesk record has a UUID. Looking one up with anything else would
    raise an error deep in the database layer (a crash, not a "not found");
    checking first turns garbage into a clean refusal.
    """
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None
