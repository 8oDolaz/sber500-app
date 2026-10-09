import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, taken from a verified access token (never from client input)."""

    user_id: uuid.UUID
    family_id: uuid.UUID | None
    session_chain_id: uuid.UUID | None = None
