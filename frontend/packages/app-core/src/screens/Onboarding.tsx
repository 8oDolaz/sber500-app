import { IntroAction, IntroCard, IntroHero, IntroPage, IntroSection, IntroTutorial, Sheet } from "@kainem/ui-kit";
import { useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { useServices } from "../context";
import { ru } from "../i18n/ru";
import { useInstall } from "../useInstall";
import { useScreenView } from "../useScreenView";
import { useOnline } from "../useHomeRuntime";

/** Screen C: product intro, add-to-home-screen, "В семью" → main screen. */
export function Onboarding() {
  useScreenView("onboarding");
  const { api } = useServices();
  const { updateMe } = useAuth();
  const navigate = useNavigate();
  const { mode, sheet, offer, closeSheet } = useInstall();
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const t = ru.onboarding;
  const online = useOnline();
  const [installing, setInstalling] = useState(false);
  const [installFailed, setInstallFailed] = useState(false);
  const installTrigger = useRef<HTMLButtonElement>(null);

  async function toFamily() {
    if (saving || !online) return;
    setSaving(true);
    setFailed(false);
    try {
      const { data } = await api.PATCH("/v1/me", { body: { onboarding_completed: true } });
      if (!data) throw new Error("failed");
      updateMe(data);
      navigate("/home", { replace: true });
    } catch {
      setFailed(true);
      setSaving(false);
    }
  }

  async function install() {
    if (installing) return;
    setInstalling(true); setInstallFailed(false);
    try { await offer(); } catch { setInstallFailed(true); }
    finally { setInstalling(false); }
  }

  const steps = sheet ? t[sheet === "ios" ? "iosSheet" : "manualSheet"] : null;
  return (
    <IntroPage>
      <IntroHero title={<>Все дела семьи.<br />В одном месте.</>} description={t.intro}
        caption="Всё готово. Можно переходить к делам семьи." action={<>
          <IntroAction telegramIcon={false} loading={saving} disabled={!online} onClick={() => void toFamily()}>{saving ? "Сохраняем…" : t.toFamily}</IntroAction>
          {failed && <p role="alert" className="kn-intro-error">{t.failed}</p>}
          {!online && <p role="status" className="kn-intro-caption">Нет соединения. Вернитесь в сеть, чтобы продолжить.</p>}
        </>} />
      {mode !== "hidden" && <IntroSection title="kainem всегда под рукой"><IntroCard>
        <h3>План семьи на главном экране</h3>
        <p>Добавьте приложение на главный экран телефона, чтобы быстро открывать задачи и события.</p>
        <IntroAction telegramIcon={false} loading={installing} onClick={event => { installTrigger.current = event.currentTarget; void install(); }}>{installing ? "Открываем установку…" : t.addToHome}</IntroAction>
        {installFailed && <p role="alert" className="kn-intro-error">Не удалось открыть установку. Попробуйте ещё раз.</p>}
      </IntroCard></IntroSection>}
      <IntroTutorial variant="welcome" />
      <footer className="kn-intro-footer">
        {failed && <p className="kn-intro-error">{t.failed}</p>}
        <IntroAction telegramIcon={false} loading={saving} disabled={!online} onClick={() => void toFamily()}>{saving ? "Сохраняем…" : "Перейти к делам"}</IntroAction>
      </footer>
      {steps ? (
        <Sheet title={steps.title} onClose={closeSheet} returnFocusRef={installTrigger}>
          <ol>
            {steps.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          <IntroAction telegramIcon={false} onClick={closeSheet}>{t.gotIt}</IntroAction>
        </Sheet>
      ) : null}
    </IntroPage>
  );
}
