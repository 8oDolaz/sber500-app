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


# Capture (screens G → H)
SAVE = "Сохранить"
EDIT = "Изменить"
CANCEL = "Отмена"
SAVE_AS_TASK = "Сохранить как задачу"

SAVED = "зафиксировал!"  # H — the bot's reply after confirmation
CANCELLED = "Отменено"
CARD_GONE = "Эта карточка устарела — перешлите сообщение ещё раз."
ALREADY_SAVED = "Уже сохранено"
REPLACED = "Заменено исправленной карточкой ↓"

LLM_UNAVAILABLE = "Сейчас не получается разобрать сообщение."
NOTHING_FOUND = "Не нашёл в сообщении задач или событий."
SAVE_AS_IS = "Сохранить его как задачу?"

REVISE_PROMPT = "Напишите, как правильно — например: «в пятницу в 18:00» или «это задача, срок до 26.09»."
PHOTO_UNAVAILABLE = "Сейчас не получается разобрать фото — напишите текстом, что запланировать."
PHOTO_NOTHING_FOUND = "Не нашёл на фото задач или событий — напишите текстом, что запланировать."
PHOTO_DOWNLOAD_FAILED = "Не получилось загрузить фото — отправьте его ещё раз."

UNSUPPORTED = "Я понимаю текст и фото, а голосовые, видео и файлы пока нет — перешлите сообщение с текстом или фото."
TOO_FAST = "Слишком много сообщений подряд — подождите минуту."


def draft_card(summary: str, family: str | None) -> str:
    card = escape(summary)
    return f"{card}\n<i>в «{escape(family)}»</i>" if family else card


def saved(summary: str | None) -> str:
    # Design H shows just "зафиксировал!"; the summary line keeps several saved cards distinguishable.
    return f"{SAVED}\n<i>{escape(summary)}</i>" if summary else SAVED


def cancelled(summary: str | None) -> str:
    return f"{CANCELLED}: <s>{escape(summary)}</s>" if summary else CANCELLED


def _llm_down(reason: str) -> bool:
    return reason in ("llm_budget", "llm_timeout", "llm_error")


def fallback(reason: str, summary: str) -> str:
    lead = LLM_UNAVAILABLE if _llm_down(reason) else NOTHING_FOUND
    return f"{lead} {SAVE_AS_IS}\n{escape(summary)}"


def photo_failed(reason: str) -> str:
    """A photo without a caption that couldn't be turned into drafts: there is no text to save as-is."""
    return PHOTO_UNAVAILABLE if _llm_down(reason) else PHOTO_NOTHING_FOUND
