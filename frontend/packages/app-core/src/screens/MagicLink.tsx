import { Button, Logo, Screen } from "@kainem/ui-kit";
import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { homeRouteFor, useAuth } from "../auth/AuthProvider";
import { useServices } from "../context";
import { ru } from "../i18n/ru";

/** `/auth/tg?token=…` — the single-use link from the bot message. */
export function MagicLink() {
  const [params] = useSearchParams();
  const { api, analytics } = useServices();
  const { state, signedIn } = useAuth();
  const navigate = useNavigate();
  const [failed, setFailed] = useState(false);
  const attempted = useRef(false); // StrictMode runs effects twice; the token is single-use
  const token = params.get("token");

  useEffect(() => {
    if (attempted.current || !token) return;
    attempted.current = true;
    void (async () => {
      try {
        const { data } = await api.POST("/v1/auth/magic", {
          body: { token, anonymous_id: await analytics.getAnonymousId() },
        });
        if (data) await signedIn(data);
        else setFailed(true);
      } catch {
        setFailed(true);
      }
    })();
  }, [api, analytics, signedIn, token]);

  if (!token) return <Navigate to="/" replace />;
  if (attempted.current && !failed && state.status === "authenticated") {
    return <Navigate to={homeRouteFor(state) ?? "/"} replace />;
  }
  return (
    <Screen variant="centered">
      <Logo size="xl" />
      {failed ? (
        <div className="kn-stack" style={{ marginTop: 32, width: "100%", textAlign: "center" }}>
          <p role="alert">{ru.magicLink.expired}</p>
          <Button onClick={() => navigate("/welcome", { replace: true })}>{ru.magicLink.loginViaTelegram}</Button>
        </div>
      ) : (
        <p>{ru.magicLink.signingIn}</p>
      )}
    </Screen>
  );
}
