def to_uppercase(value: str | None) -> str | None:
    """
    Converts a string to uppercase if it's not None.
    """
    if value is None:
        return None
    return value.upper()

def to_lowercase(value: str | None) -> str | None:
    """
    Converts a string to lowercase if it's not None.
    """
    if value is None:
        return None
    return value.lower()
