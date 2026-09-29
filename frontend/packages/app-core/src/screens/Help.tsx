import { BackButton, Button, Screen } from "@kainem/ui-kit";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { useServices } from "../context";
import { ru } from "../i18n/ru";
import { useScreenView } from "../useScreenView";

/** "Как пользоваться" (chip on screen D). Not in the design yet: TODO(design). */
export function Help() {
  useScreenView("help");
  const { state, signOut, updateMe } = useAuth();
  const { platform, api } = useServices();
  const navigate = useNavigate();
  const t = ru.help;
  const me = state.status === "authenticated" ? state.me : null;
  const botLink = me?.bot_link ?? null;

  async function switchFamily(familyId: string) {
    const { data } = await api.PUT("/v1/me/active-family", { body: { family_id: familyId } });
    if (data) updateMe(data);
  }

  return (
    <Screen>
      <BackButton onClick={() => navigate("/home")}>{t.back}</BackButton>
      <article className="kn-prose">
        <h1 className="kn-logo kn-logo--m" style={{ textAlign: "left", marginTop: 16 }}>
          {t.title}
        </h1>
        {t.blocks.map((b) => (
          <section key={b.title}>
            <h2>{b.title}</h2>
            <p>{b.text}</p>
          </section>
        ))}
        {me && me.families.length > 1 ? (
          <section>
            <h2>{t.families}</h2>
            <ul className="kn-list">
              {me.families.map((f) => (
                <li key={f.id}>
                  <button
                    type="button"
                    className="kn-back"
                    aria-pressed={f.id === me.active_family_id}
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
      </article>
      <div className="kn-stack" style={{ marginTop: 32 }}>
        {botLink ? <Button onClick={() => platform.openLink(botLink)}>{t.openBot}</Button> : null}
        <button type="button" className="kn-back" style={{ alignSelf: "center" }} onClick={() => void signOut()}>
          {t.signOut}
        </button>
      </div>
    </Screen>
  );
}
