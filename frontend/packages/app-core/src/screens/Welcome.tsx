import { Button, Card, Logo, Screen, WelcomeText } from "@kainem/ui-kit";
import { useAuth } from "../auth/AuthProvider";
import { useTelegramLogin } from "../auth/useTelegramLogin";
import { ru } from "../i18n/ru";
import { useScreenView } from "../useScreenView";

/** Screen B: welcome + "Зарегистрироваться" → registration continues in the Telegram bot. */
export function Welcome() {
  useScreenView("welcome");
  const { signedIn } = useAuth();
  const { status, start, cancel, openTelegram } = useTelegramLogin(signedIn);
  const t = ru.welcome;

  return (
    <Screen>
      <Logo size="xl" />
      <WelcomeText>{t.text}</WelcomeText>
      <div className="kn-stack" style={{ marginTop: 32 }}>
        <Card minHeight={335}>{t.product}</Card>
        <Card minHeight={147}>{t.telegramNote}</Card>
      </div>
      <div style={{ marginTop: 13 }}>
        {status.kind === "error" ? (
          <p role="alert" style={{ textAlign: "center", margin: "0 0 12px" }}>
            {t.errors[status.reason]}
          </p>
        ) : null}
        {status.kind === "waiting" ? (
          <>
            <Button loading>{t.waiting}</Button>
            <p style={{ textAlign: "center", display: "flex", gap: 16, justifyContent: "center" }}>
              <a
                className="kn-link"
                href={status.deepLink}
                onClick={(e) => {
                  e.preventDefault();
                  openTelegram(status.deepLink);
                }}
              >
                {t.reopenTelegram}
              </a>
              <button type="button" className="kn-link" style={{ border: 0, background: "none", font: "inherit" }} onClick={() => void cancel()}>
                {t.cancel}
              </button>
            </p>
          </>
        ) : (
          <Button loading={status.kind === "starting"} onClick={() => void start()}>
            {t.register}
          </Button>
        )}
      </div>
    </Screen>
  );
}
