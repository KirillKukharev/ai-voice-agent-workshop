def normalize_phone(phone: str) -> str:
    """Normalize phone number for comparison."""
    if not phone:
        return ""
    normalized = phone.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    if normalized.startswith("+"):
        return normalized
    return normalized.lstrip("+")


def matches_phone(record_phone: str, user_phone: str) -> bool:
    """Check if record phone matches user phone (with normalization)."""
    if not record_phone or not user_phone:
        return False

    record_norm = normalize_phone(str(record_phone))
    user_norm = normalize_phone(str(user_phone))

    return (
        record_norm == user_norm
        or record_norm.lstrip("+") == user_norm.lstrip("+")
        or record_norm == user_norm.lstrip("+")
        or record_norm.lstrip("+") == user_norm
    )
