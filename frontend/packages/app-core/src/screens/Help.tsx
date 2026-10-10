import { IntroAction, IntroBack, IntroCard, IntroHero, IntroHomeGuide, IntroInviteIcon, IntroPage, IntroSection, IntroTutorial, InviteCard } from "@kainem/ui-kit";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { useServices } from "../context";
import { ru } from "../i18n/ru";
import { useScreenView } from "../useScreenView";
import { useBotAction, useOnline } from "../useHomeRuntime";

/** Figma guide, with the existing family/account actions retained in a disclosure. */
export function Help() {
  useScreenView("help");
  const { state, signOut, updateMe } = useAuth();
  const { api } = useServices();
  const navigate = useNavigate();
  const location = useLocation();
  const online = useOnline();
  const t = ru.help;
  const me = state.status === "authenticated" ? state.me : null;
  const botLink = me?.bot_link ?? null;
  const bot = useBotAction(botLink, me?.active_family_id ?? "");
  const opening = bot.state?.status === "Opening";
  const [switching, setSwitching] = useState<string | null>(null);
  const [switchFailed, setSwitchFailed] = useState(false);
  useEffect(() => { window.scrollTo(0, 0); }, []);

  function back() {
    const previous = location.state as { fromHome?: boolean; homeScrollY?: number } | null;
    if (previous?.fromHome) {
      navigate(-1);
      requestAnimationFrame(() => window.scrollTo(0, previous.homeScrollY ?? 0));
    } else navigate("/home", { replace: true });
  }

  async function switchFamily(familyId: string) {
    if (switching || !online) return;
    setSwitching(familyId); setSwitchFailed(false);
    try {
      const { data } = await api.PUT("/v1/me/active-family", { body: { family_id: familyId } });
      if (!data) throw new Error("family switch failed");
      updateMe(data);
    } catch { setSwitchFailed(true); }
    finally { setSwitching(null); }
  }

  return (
    <IntroPage>
      <IntroHero title={t.title} description={t.description} navigation={<IntroBack onClick={back}>{t.back}</IntroBack>}
        caption="Добавление дел и приглашения — в боте" action={<>
          <IntroAction loading={opening && bot.state?.origin === "header"} disabled={!bot.available || opening}
            onClick={() => void bot.open("header")}>{opening && bot.state?.origin === "header" ? "Открываем бота…" : t.openBot}</IntroAction>
          {!bot.available && <p className="kn-intro-caption">Ссылка на бота пока недоступна.</p>}
          {bot.state?.status === "Error" && bot.state.origin === "header" && <p role="alert" className="kn-intro-error">Не удалось открыть бота. Попробуйте ещё раз.</p>}
        </>} />
      <IntroTutorial />
      <IntroHomeGuide blocks={t.blocks} />
      <IntroSection title="Планируйте вместе">
        <InviteCard className="kn-intro-invite" inviteIcon={<IntroInviteIcon />} opening={opening && bot.state?.origin === "invite"} error={bot.state?.status === "Error" && bot.state.origin === "invite"}
          disabled={!bot.available || (opening && bot.state?.origin !== "invite")} unavailable={!bot.available} onOpen={() => void bot.open("invite")} />
      </IntroSection>
      <details className="kn-intro-account"><summary>Семья и аккаунт</summary><IntroCard>
        {me && me.families.length > 1 ? (
          <section>
            <h2>{t.families}</h2>
            <ul className="kn-intro-options">
              {me.families.map((f) => (
                <li key={f.id}>
                  <button
                    type="button"
                    className="kn-intro-option"
                    aria-pressed={f.id === me.active_family_id}
                    disabled={!online || switching !== null || f.id === me.active_family_id}
                    aria-busy={switching === f.id || undefined}
                    onClick={() => void switchFamily(f.id)}
                  >
                    {f.name}
                    {f.id === me.active_family_id ? ` — ${t.active}` : ""}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {switchFailed && <p role="alert" className="kn-intro-error">Не удалось переключить семью. Попробуйте ещё раз.</p>}
        {!online && <p role="status">Переключение семьи недоступно без сети.</p>}
        <button type="button" className="kn-intro-option" onClick={() => void signOut()}>{t.signOut}</button>
      </IntroCard></details>
      <footer className="kn-intro-footer"><IntroBack onClick={back}>{t.back}</IntroBack></footer>
    </IntroPage>
  );
}
