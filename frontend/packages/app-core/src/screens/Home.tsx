import { Card, Chip, List, ListRow, Logo, Screen, SectionTitle } from "@kainem/ui-kit";
import type { ReactNode } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { useServices } from "../context";
import { eventMeta, taskMeta } from "../data/format";
import { eventsTimezone, useOpenTasks, useSetTaskDone, useUpcomingEvents } from "../data/planning";
import { ru } from "../i18n/ru";
import { useScreenView } from "../useScreenView";

/** The third category has no name in the design yet; it stays hidden until it gets one. */
const SHOW_THIRD_SECTION = false;
const MIN_ROWS = 3; // the design's card always shows three rows

function ItemsSection({ title, rows, hint }: { title: string; rows: ReactNode[]; hint?: string }) {
  const placeholders = Math.max(MIN_ROWS - rows.length, 0);
  return (
    <section className="kn-home-section">
      <SectionTitle>{title}</SectionTitle>
      <Card variant="home" minHeight={222}>
        <List>
          {rows}
          {Array.from({ length: placeholders }, (_, i) => (
            <ListRow key={`empty-${i}`}>
              {i === 0 && rows.length === 0 && hint ? <span className="kn-hint">{hint}</span> : null}
            </ListRow>
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
  const { state } = useAuth();
  const navigate = useNavigate();
  const t = ru.home;
  const familyId = state.status === "authenticated" ? (state.me.active_family_id ?? "") : "";

  const tasks = useOpenTasks(familyId);
  const events = useUpcomingEvents(familyId);
  const setDone = useSetTaskDone(familyId);
  const tz = eventsTimezone(events.data);

  const taskRows = (tasks.data ?? []).map((task) => (
    <ListRow
      key={task.id}
      done={task.done}
      meta={taskMeta(task, tz)}
      toggleLabel={task.done ? t.markUndone : t.markDone}
      onToggle={() => setDone.mutate({ id: task.id, done: !task.done })}
    >
      {task.title}
    </ListRow>
  ));
  const eventRows = (events.data?.events ?? []).map((event) => (
    <ListRow key={event.id} meta={eventMeta(event, tz)}>
      {event.title}
    </ListRow>
  ));

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
      <ItemsSection title={t.sections.tasks} rows={taskRows} hint={t.emptyHint} />
      <ItemsSection title={t.sections.events} rows={eventRows} />
      {SHOW_THIRD_SECTION ? <ItemsSection title={t.sections.third} rows={[]} /> : null}
    </Screen>
  );
}
