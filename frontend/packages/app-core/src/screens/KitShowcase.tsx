import { EventRow, HomeAction, InviteCard, PlanningCard, Screen, TaskRow, TodayCard, type SectionState, type TaskState } from "@kainem/ui-kit";
import { useState } from "react";

/** Development-only state catalogue. It does not replace real queries on /home. */
export function KitShowcase() {
  const [state, setState] = useState<SectionState>("Content");
  const [row, setRow] = useState<TaskState>("Open");
  const [timing, setTiming] = useState("DateTime");
  const [eventTiming, setEventTiming] = useState("TodayTime");
  const [person, setPerson] = useState(true);
  const [invite, setInvite] = useState("Default");
  const taskViews = {
    DateTime: { date: "Сегодня", time: "17:00" }, DateOnly: { date: "Завтра" },
    TimeOnly: { time: "17:00" }, None: {},
  };
  const eventViews = {
    DateTime: { date: "Завтра", day: "11", month: "ОКТ", time: "18:00" },
    DateOnly: { date: "Завтра", day: "11", month: "ОКТ" }, TimeOnly: { time: "18:00" }, None: {},
    TodayTime: { today: true, time: "19:00" }, TodayNoTime: { today: true },
  };
  return <Screen variant="home">
    <h1>Компоненты главной</h1>
    <label>Состояние списка <select value={state} onChange={e => setState(e.target.value as SectionState)}>
      {["Content", "Empty", "Loading", "Error", "OfflineEmpty", "Refreshing", "Stale", "Offline", "AllDone"].map(s => <option key={s}>{s}</option>)}
    </select></label>
    <label>Состояние задачи <select value={row} onChange={e => setRow(e.target.value as TaskState)}>
      {["Open", "Saving", "Completed", "Error", "Disabled", "Overdue"].map(s => <option key={s}>{s}</option>)}
    </select></label>
    <label>Данные задачи <select value={timing} onChange={e => setTiming(e.target.value)}>{Object.keys(taskViews).map(s => <option key={s}>{s}</option>)}</select></label>
    <label>Данные события <select value={eventTiming} onChange={e => setEventTiming(e.target.value)}>{Object.keys(eventViews).map(s => <option key={s}>{s}</option>)}</select></label>
    <label><input type="checkbox" checked={person} onChange={e => setPerson(e.target.checked)} /> Указан человек</label>
    <label>Приглашение <select value={invite} onChange={e => setInvite(e.target.value)}>{["Default", "Opening", "Error", "Disabled"].map(s => <option key={s}>{s}</option>)}</select></label>
    <div className="kn-home-cards">
      <TodayCard items={[{ id: "task", kind: "tasks", title: "Собрать форму", time: "17:00" }, { id: "event", kind: "events", title: "Футбол", time: "19:00" }]} state={["Loading", "Refreshing", "Stale", "Offline"].includes(state) ? state : "Content"} onRetry={() => setState("Content")} />
      <PlanningCard kind="tasks" state={state} onRetry={() => setState("Content")}>
        <TaskRow title="Собрать форму" {...taskViews[timing as keyof typeof taskViews]} person={person ? "Маша" : null} state={row} onToggle={() => setRow("Completed")} />
        <TaskRow title="Уточнить расписание" />
      </PlanningCard>
      <PlanningCard kind="events" state={state === "AllDone" ? "Empty" : state} onRetry={() => setState("Content")}>
        <EventRow title="Футбол" {...eventViews[eventTiming as keyof typeof eventViews]} person={person ? "Миша" : null} />
        <EventRow title="Уточнить место" />
      </PlanningCard>
      <InviteCard opening={invite === "Opening"} error={invite === "Error"} disabled={invite === "Disabled"} unavailable={invite === "Disabled"} onOpen={() => setInvite("Opening")} />
      <HomeAction tone="bot" icon="telegram">В бота</HomeAction>
      <HomeAction tone="help" icon="mascotHelp">Как пользоваться</HomeAction>
    </div>
  </Screen>;
}
