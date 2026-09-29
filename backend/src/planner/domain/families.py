"""Family (tenant) rules — ARCHITECTURE §5.2. Pure: no I/O, no frameworks."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"  # the "Лидер": created the family
    ADULT = "adult"  # the "Акцептор" by default
    TEEN = "teen"
    CHILD = "child"
    CAREGIVER = "caregiver"


INVITE_START_PREFIX = "inv_"
LOGIN_START_PREFIX = "login_"


def family_name_for(first_name: str | None) -> str:
    name = (first_name or "").strip()
    return f"Семья {name}" if name else "Моя семья"


def invite_deep_link(bot_username: str, token: str) -> str:
    return f"https://t.me/{bot_username}?start={INVITE_START_PREFIX}{token}"


def login_deep_link(bot_username: str, nonce: str) -> str:
    return f"https://t.me/{bot_username}?start={LOGIN_START_PREFIX}{nonce}"
