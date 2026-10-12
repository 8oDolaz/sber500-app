from planner.bootstrap import Container
from planner.entrypoints.bot.app import build_dispatcher
from planner.infra.telemetry import BOT_UPDATES
from tests.integration.telegram import fake_bot, message_update


async def test_plain_start_registers_family_and_counts_update(container: Container) -> None:
    bot, session = fake_bot()
    dp = build_dispatcher(container)
    before = BOT_UPDATES.labels(update_type="message", status="ok")._value.get()
    await dp.feed_update(bot, message_update("/start"))
    texts = session.texts()
    assert texts[0] == "<b>Пространство семьи зарегистрировано!</b>"
    assert "https://t.me/kainem_test_bot?start=inv_" in texts[1]
    assert "https://app.test/auth/tg?token=" in texts[2]
    assert texts[2].endswith(f"\n\n{texts[1]}")
    assert BOT_UPDATES.labels(update_type="message", status="ok")._value.get() == before + 1


async def test_second_start_logs_in_without_new_family(container: Container) -> None:
    bot, session = fake_bot()
    dp = build_dispatcher(container)
    await dp.feed_update(bot, message_update("/start"))
    await dp.feed_update(bot, message_update("/start"))
    assert len(session.texts()) == 4
    assert session.texts()[3].startswith("Вы вошли")
    assert session.texts()[3].endswith(f"\n\n{session.texts()[1]}")
