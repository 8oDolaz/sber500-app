import { Button, Card, CardButton, Logo, Screen, Sheet } from "@kainem/ui-kit";
import { useState } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { useServices } from "../context";
import { ru } from "../i18n/ru";
import { useInstall } from "../useInstall";
import { useScreenView } from "../useScreenView";

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

  async function toFamily() {
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

  const steps = sheet ? t[sheet === "ios" ? "iosSheet" : "manualSheet"] : null;
  return (
    <Screen>
      <Logo size="xl" />
      <div className="kn-stack" style={{ marginTop: 20 }}>
        <Card align="top" minHeight={428}>
          {t.intro}
        </Card>
        {mode !== "hidden" ? (
          <CardButton minHeight={176} onClick={() => void offer()}>
            {t.addToHome}
          </CardButton>
        ) : null}
      </div>
      <div style={{ marginTop: 17 }}>
        {failed ? (
          <p role="alert" style={{ textAlign: "center", margin: "0 0 12px" }}>
            {t.failed}
          </p>
        ) : null}
        <Button loading={saving} onClick={() => void toFamily()}>
          {t.toFamily}
        </Button>
      </div>
      {steps ? (
        <Sheet title={steps.title} onClose={closeSheet}>
          <ol>
            {steps.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          <Button onClick={closeSheet}>{t.gotIt}</Button>
        </Sheet>
      ) : null}
    </Screen>
  );
}
