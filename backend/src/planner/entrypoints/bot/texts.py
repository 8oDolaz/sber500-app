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

# F — the acceptor's first message. Design copy was a placeholder ("переходи и че то делай"). TODO(design)
INVITE_ACCEPTED = "Ты получил приглашение в пространство семьи «{family}». Переходи — {magic_link}"

ALREADY_MEMBER = "Ты уже в семье «{family}». Вот пространство семьи — {magic_link}"

INVITE_INVALID = (
    "Это приглашение недействительно или устарело. Попроси родных прислать новую ссылку "
    "или создай своё пространство семьи."
)
CREATE_OWN_FAMILY = "Создать своё пространство"

SHARE = "Поделиться"
JOIN = "Присоединиться"

# What the recipient sees when the leader shares through the inline button.
INVITE_CARD = "Присоединяйся к пространству семьи «{family}» в kainem:\n{invite_link}"
INLINE_TITLE = "Пригласить в «{family}»"
INLINE_DESCRIPTION = "Отправить ссылку-приглашение"
INLINE_REGISTER = "Сначала зарегистрируйте семью"

NOT_REGISTERED = "Сначала зарегистрируйте семью — отправьте /start."


def invite(invite_link: str) -> str:
    return INVITE.format(invite_link=escape(invite_link))


def finish_registration(magic_link: str) -> str:
    return FINISH_REGISTRATION.format(magic_link=escape(magic_link))


def logged_in(magic_link: str) -> str:
    return LOGGED_IN.format(magic_link=escape(magic_link))


def handshake_expired(magic_link: str) -> str:
    return HANDSHAKE_EXPIRED.format(magic_link=escape(magic_link))


def invite_accepted(family: str, magic_link: str) -> str:
    return INVITE_ACCEPTED.format(family=escape(family), magic_link=escape(magic_link))


def already_member(family: str, magic_link: str) -> str:
    return ALREADY_MEMBER.format(family=escape(family), magic_link=escape(magic_link))


def invite_card(family: str, invite_link: str) -> str:
    return INVITE_CARD.format(family=escape(family), invite_link=escape(invite_link))
