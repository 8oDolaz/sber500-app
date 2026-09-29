import { Button, Card, Logo, Screen } from "@kainem/ui-kit";
import { useAuth } from "../auth/AuthProvider";
import { ru } from "../i18n/ru";
import { useScreenView } from "../useScreenView";

/** Placeholders so M1 is testable end to end; replaced by screens C and D in M2. */
export function OnboardingStub() {
  useScreenView("onboarding");
  const { state } = useAuth();
  return (
    <Screen>
      <Logo size="xl" />
      <Card minHeight={200} style={{ marginTop: 32 }}>
        {state.status === "authenticated" ? state.me.families[0]?.name : null}
        <br />
        {ru.stub.onboarding}
      </Card>
    </Screen>
  );
}

export function HomeStub() {
  useScreenView("home");
  const { signOut } = useAuth();
  return (
    <Screen variant="home">
      <Logo size="m" />
      <Card minHeight={200} style={{ marginTop: 32 }}>
        {ru.stub.home}
      </Card>
      <div style={{ marginTop: 16 }}>
        <Button onClick={() => void signOut()}>{ru.stub.signOut}</Button>
      </div>
    </Screen>
  );
}
