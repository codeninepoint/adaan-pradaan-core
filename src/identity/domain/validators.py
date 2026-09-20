from __future__ import annotations

import re

from shared.domain.exceptions import ValidationError

PASSWORD_RE = re.compile(r"^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_password(password: str) -> None:
    if not PASSWORD_RE.match(password):
        raise ValidationError("password does not meet requirements")


def validate_email(email: str) -> None:
    if not EMAIL_RE.match(email):
        raise ValidationError("invalid email format")


def validate_display_name(display_name: str) -> None:
    if not display_name or not display_name.strip() or len(display_name) > 255:
        raise ValidationError("display_name is required")
