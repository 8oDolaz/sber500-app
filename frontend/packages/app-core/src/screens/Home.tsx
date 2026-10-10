import { EventRow, HomeAction, HomeHeader, InviteCard, PlanningCard, Screen, TaskRow, TodayCard, type SectionState, type TodayItem } from "@kainem/ui-kit";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { useServices } from "../context";
import { dayKey, eventPresentation, taskPresentation } from "../data/format";
import { eventsTimezone, useOpenTasks, useSetTaskDone, useUpcomingEvents } from "../data/planning";
import { sectionState, useBotAction, useFamilyClock, useOnline } from "../useHomeRuntime";
import { useScreenView } from "../useScreenView";

export function Home() {
  useScreenView("home");
  const { analytics } = useServices();
  const { state } = useAuth();
  const me = state.status === "authenticated" ? state.me : null;
  const familyId = me?.active_family_id ?? "";
  const navigate = useNavigate(), online = useOnline(), now = useFamilyClock();
  const tasks = useOpenTasks(familyId), events = useUpcomingEvents(familyId), completion = useSetTaskDone(familyId);
  const bot = useBotAction(me?.bot_link, familyId);
  const tz = eventsTimezone(events.data), today = dayKey(now, tz);
  const taskItems = (tasks.data ?? []).map(task => ({ task, view: taskPresentation(task, tz, now, events.data !== undefined) }));
  const eventItems = (events.data?.events ?? []).map(event => ({ event, view: eventPresentation(event, tz, now) }));
  const taskState = sectionState(tasks, taskItems.length, online, completion.hasCompleted);
  const eventState = sectionState(events, eventItems.length, online);
  const todayItems: TodayItem[] = [
    ...taskItems.filter(({ task, view }) => events.data !== undefined && !task.done && view.dateKey === today).map(({ task, view }) => ({ id: task.id, title: task.title, time: view.time, kind: "tasks" as const })),
    ...eventItems.filter(({ view }) => view.today).map(({ event, view }) => ({ id: event.id, title: event.title, time: view.time, kind: "events" as const })),
  ];
  const summaryState: SectionState = !online ? "Offline" : tasks.isError || events.isError ? "Stale" : tasks.isFetching || events.isFetching ? "Refreshing" : "Content";
  function retryAll() { void tasks.refetch(); void events.refetch(); }
  const opening = bot.state?.status === "Opening";
  return <Screen variant="home">
    <HomeHeader><HomeAction tone="bot" icon="telegram" loading={opening && bot.state?.origin === "header"} disabled={!bot.available || opening} onClick={() => void bot.open("header")}>В бота</HomeAction></HomeHeader>
    <div className="kn-home-cards">
      {bot.state?.status === "Error" && bot.state.origin === "header" && <section className="kn-planning-card kn-bot-error" role="alert">
        <h2>Не удалось открыть бота</h2><p className="kn-home-caption">Попробуйте ещё раз или откройте Telegram.</p>
        <HomeAction onClick={() => void bot.open("header")}>Повторить</HomeAction>
      </section>}
      {!familyId ? <section className="kn-planning-card kn-bot-error" aria-labelledby="family-unavailable-title">
        <h2 id="family-unavailable-title">Семья пока не выбрана</h2>
        <p className="kn-home-body">Откройте бота, чтобы создать семью или присоединиться к ней.</p>
      </section> : <>
      {todayItems.length > 0 && <TodayCard items={todayItems} state={summaryState} onRetry={retryAll} />}
      <PlanningCard kind="tasks" state={taskState} onRetry={() => void tasks.refetch()}>
        {taskItems.map(({ task, view }) => <TaskRow key={task.id} title={task.title} {...view}
          state={!online ? "Disabled" : completion.rows[task.id] ?? (task.done ? "Completed" : view.overdue ? "Overdue" : "Open")}
          onToggle={() => completion.mutate({ id: task.id, done: true })} />)}
      </PlanningCard>
      <PlanningCard kind="events" state={eventState} onRetry={() => void events.refetch()}>
        {eventItems.map(({ event, view }) => <EventRow key={event.id} title={event.title} {...view} />)}
      </PlanningCard>
      <InviteCard opening={opening && bot.state?.origin === "invite"} error={bot.state?.status === "Error" && bot.state.origin === "invite"} unavailable={!bot.available}
        disabled={!bot.available || (opening && bot.state?.origin !== "invite")} onOpen={() => void bot.open("invite")} />
      </>}
    </div>
    <footer className="kn-home-footer"><HomeAction tone="help" icon="mascotHelp" onClick={() => { analytics.track("how_to_clicked", {}); navigate("/help", { state: { fromHome: true, homeScrollY: window.scrollY } }); }}>Как пользоваться</HomeAction></footer>
  </Screen>;
}
