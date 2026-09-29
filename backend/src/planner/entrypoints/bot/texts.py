"""All bot copy (screens E–H from SPEC §3). HTML parse mode: escape anything user-provided."""

from html import escape

FAMILY_REGISTERED = "<b>Пространство семьи зарегистрировано!</b>"  # E1

# E2 — self-contained so a native forward to relatives works ("Пересылается в лс людям").
# Design copy had a typo ("и он добавиться"); fixed. TODO(design): confirm wording.
INVITE = "Отправь ссылку-приглашение родным, и они добавятся в семью:\n{invite_link}"

# E3
FINISH_REGISTRATION = "Завершите регистрацию семьи. Вот пространство семьи — {magic_link}"

LOGGED_IN = "Вы вошли ✅ Вернитесь в приложение kainem.\nЕсли оно не открылось само, вот ссылка — {magic_link}"

HANDSHAKE_EXPIRED = (
    "Ссылка для входа устарела. Вернитесь в приложение и нажмите «Зарегистрироваться» ещё раз.\n"
    "Или откройте пространство семьи по этой ссылке — {magic_link}"
)

INVITE_SOON = "Приглашения в семью заработают совсем скоро 🙌"


def invite(invite_link: str) -> str:
    return INVITE.format(invite_link=escape(invite_link))


def finish_registration(magic_link: str) -> str:
    return FINISH_REGISTRATION.format(magic_link=escape(magic_link))


def logged_in(magic_link: str) -> str:
    return LOGGED_IN.format(magic_link=escape(magic_link))


def handshake_expired(magic_link: str) -> str:
    return HANDSHAKE_EXPIRED.format(magic_link=escape(magic_link))
