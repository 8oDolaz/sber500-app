import { Button, Logo, Screen } from "@kainem/ui-kit";
import { Navigate } from "react-router";
import { homeRouteFor, useAuth } from "../auth/AuthProvider";
import { ru } from "../i18n/ru";
import { useScreenView } from "../useScreenView";

/** Screen A: shown while the session is resolved, then hands over to the right screen. */
export function Splash() {
  useScreenView("splash");
  const { state, reload } = useAuth();
  const target = homeRouteFor(state);
  if (target) return <Navigate to={target} replace />;
  return (
    <Screen variant="centered">
      <Logo size="xl" />
      {state.status === "offline" ? (
        <div className="kn-stack" style={{ marginTop: 32, width: "100%", textAlign: "center" }}>
          <p>{ru.offline.text}</p>
          <Button onClick={() => void reload()}>{ru.offline.retry}</Button>
        </div>
      ) : null}
    </Screen>
  );
}
