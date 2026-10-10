import { IntroAction, IntroFeatures, IntroHero, IntroPage, IntroTutorial } from "@kainem/ui-kit";
import { useAuth } from "../auth/AuthProvider";
import { useTelegramLogin } from "../auth/useTelegramLogin";
import { ru } from "../i18n/ru";
import { useScreenView } from "../useScreenView";
import { useOnline } from "../useHomeRuntime";

/** Final first contact screen. Both CTAs share one persisted Telegram handshake. */
export function Welcome() {
  useScreenView("welcome");
  const { signedIn } = useAuth();
  const { status, start, cancel, openTelegram } = useTelegramLogin(signedIn);
  const t = ru.welcome;
  const online = useOnline();
  const busy = status.kind === "starting" || status.kind === "waiting";

  function action(footer = false) {
    return <IntroAction loading={status.kind === "starting" || (!footer && status.kind === "waiting")}
      disabled={!online || (!footer && busy) || status.kind === "starting"}
      onClick={() => {
        if (status.kind === "waiting") void openTelegram(status.deepLink).catch(() => undefined);
        else void start();
      }}>
      {!online ? t.offline : status.kind === "starting" ? t.starting : status.kind === "waiting" ? footer ? t.reopenTelegram : t.waiting : t.register}
    </IntroAction>;
  }

  return (
    <IntroPage>
      <IntroHero title={<>Все дела семьи.<br />В одном месте.</>} description={t.description}
        caption={t.telegramNote} action={<>
          {action()}
          {status.kind === "error" && <p role="alert" className="kn-intro-error">{t.errors[status.reason]}</p>}
          {!online && <p role="status" className="kn-intro-caption">{t.errors.offline}</p>}
          {status.kind === "waiting" && <div className="kn-intro-link-row">
            <button type="button" className="kn-intro-link" onClick={() => void openTelegram(status.deepLink).catch(() => undefined)}>{t.reopenTelegram}</button>
            <button type="button" className="kn-intro-link" onClick={() => void cancel()}>{t.cancel}</button>
          </div>}
        </>} />
      <IntroTutorial variant="welcome" />
      <IntroFeatures />
      <footer className="kn-intro-footer">{action(true)}<p className="kn-intro-caption">{t.telegramNote}</p></footer>
    </IntroPage>
  );
}
