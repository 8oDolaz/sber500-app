import { Card, Chip, List, ListRow, Logo, Screen, SectionTitle } from "@kainem/ui-kit";
import { useNavigate } from "react-router";
import { useServices } from "../context";
import { ru } from "../i18n/ru";
import { useScreenView } from "../useScreenView";

/** The third category has no name in the design yet; it stays hidden until it gets one. */
const SHOW_THIRD_SECTION = false;
const PLACEHOLDER_ROWS = 3;

function ItemsSection({ title, hint }: { title: string; hint?: string }) {
  // Items arrive with bot capture (M4); until then the design's empty rows are shown.
  return (
    <section className="kn-home-section">
      <SectionTitle>{title}</SectionTitle>
      <Card variant="home" minHeight={222}>
        <List>
          {Array.from({ length: PLACEHOLDER_ROWS }, (_, i) => (
            <ListRow key={i}>{i === 0 && hint ? <span className="kn-hint">{hint}</span> : null}</ListRow>
          ))}
        </List>
      </Card>
    </section>
  );
}

/** Screen D: the main screen a signed-in, onboarded user returns to. */
export function Home() {
  useScreenView("home");
  const { analytics } = useServices();
  const navigate = useNavigate();
  const t = ru.home;

  return (
    <Screen variant="home">
      <header className="kn-home-header">
        <Logo size="m" />
        <Chip
          onClick={() => {
            analytics.track("how_to_clicked", {});
            navigate("/help");
          }}
        >
          {t.howTo}
        </Chip>
      </header>
      <ItemsSection title={t.sections.tasks} hint={t.emptyHint} />
      <ItemsSection title={t.sections.events} />
      {SHOW_THIRD_SECTION ? <ItemsSection title={t.sections.third} /> : null}
    </Screen>
  );
}
