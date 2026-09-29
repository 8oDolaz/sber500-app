import { BackButton, Button, Screen } from "@kainem/ui-kit";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { useServices } from "../context";
import { ru } from "../i18n/ru";
import { useScreenView } from "../useScreenView";

/** "Как пользоваться" (chip on screen D). Not in the design yet: TODO(design). */
export function Help() {
  useScreenView("help");
  const { state, signOut } = useAuth();
  const { platform } = useServices();
  const navigate = useNavigate();
  const t = ru.help;
  const botLink = state.status === "authenticated" ? state.me.bot_link : null;

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
