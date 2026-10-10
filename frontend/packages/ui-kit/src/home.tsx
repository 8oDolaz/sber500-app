import { useId, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Button } from "./components";
import clock from "./assets/home/clock.svg";
import person from "./assets/home/person.svg";
import calendar from "./assets/home/calendar.svg";
import calendarMeta from "./assets/home/calendar-meta.svg";
import calendarUnknown from "./assets/home/calendar-unknown.svg";
import pin from "./assets/home/pin.svg";
import pinMeta from "./assets/home/pin-meta.svg";
import telegram from "./assets/home/telegram.svg";
import mascot from "./assets/home/mascot.svg";
import headerGlow from "./assets/home/header-glow.svg";
import bell from "./assets/home/bell.svg";
import invitePerson from "./assets/home/person-invite.svg";
import mascotHelp from "./assets/home/mascot-help.svg";
import clockToday from "./assets/home/clock-today.svg";
import skeletonCircle from "./assets/home/skeleton-circle.svg";
import todaySkeletonTask from "./assets/home/today-skeleton-row.svg";
import todaySkeletonEvent from "./assets/home/today-skeleton-event.svg";
import checkboxDefault from "./assets/home/checkbox-default.svg";
import checkboxHover from "./assets/home/checkbox-hover.svg";
import checkboxPressed from "./assets/home/checkbox-pressed.svg";
import checkboxFocus from "./assets/home/checkbox-focus.svg";
import checkboxSaving from "./assets/home/checkbox-saving.svg";
import checkboxError from "./assets/home/checkbox-error.svg";
import checkboxDisabled from "./assets/home/checkbox-disabled.svg";
import checkedCircle from "./assets/home/checkbox-checked-circle.svg";
import checkmark from "./assets/home/checkmark.svg";

const icons = { clock, person, calendar, calendarMeta, calendarUnknown, pin, pinMeta, telegram, bell, invitePerson, mascotHelp, clockToday };
export type HomeIconName = keyof typeof icons;

/** Intrinsic SVG dimensions are preserved; only the surrounding design slot is sized. */
export function HomeIcon({ name }: { name: HomeIconName }) {
  return <span className={`kn-home-icon kn-home-icon--${name}`} aria-hidden="true"><img src={icons[name]} alt="" /></span>;
}

export function HomeAction({ tone = "neutral", icon, loading, children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: "neutral" | "bot" | "help"; icon?: HomeIconName; loading?: boolean;
}) {
  return <Button {...props} loading={loading} className={`kn-home-action kn-home-action--${tone} ${className}`}>
    {loading ? <span className="kn-home-spinner" aria-hidden="true" /> : icon ? <HomeIcon name={icon} /> : null}
    <span>{children}</span>
  </Button>;
}

export function HomeHeader({ children }: { children: ReactNode }) {
  return <header className="kn-home-hero">
    <img className="kn-home-hero__mascot" src={mascot} alt="" />
    <img className="kn-home-hero__glow" src={headerGlow} alt="" />
    <h1>Привет, семья!</h1>
    <div className="kn-home-hero__action">{children}</div>
  </header>;
}

export type SectionState = "Content" | "Empty" | "Loading" | "Error" | "OfflineEmpty" | "Refreshing" | "Stale" | "Offline" | "AllDone";
export type TaskState = "Open" | "Saving" | "Completed" | "Error" | "Disabled" | "Overdue";

function SectionStatus({ state, onRetry }: { state: SectionState; onRetry?: () => void }) {
  const offline = state === "Offline" || state === "OfflineEmpty";
  if (state !== "Refreshing" && state !== "Stale" && state !== "Offline") return null;
  return <div className="kn-home-section-status" role="status">
    <p>{state === "Refreshing" ? "Обновляем…" : offline ? <>Нет соединения.<br />Показаны сохранённые данные.</> : <>Не удалось обновить.<br />Показаны сохранённые данные.</>}</p>
    {state !== "Refreshing" && <HomeAction disabled={offline} onClick={onRetry}>Повторить</HomeAction>}
  </div>;
}

export function PlanningCard({ kind, state, onRetry, children }: { kind: "tasks" | "events"; state: SectionState; onRetry: () => void; children?: ReactNode }) {
  const id = useId();
  const tasks = kind === "tasks";
  const emptyStyle = ["Empty", "Error", "OfflineEmpty", "AllDone"].includes(state);
  const title = state === "Empty" ? tasks ? "Задач пока нет" : "Событий пока нет" : state === "AllDone" ? "Всё сделано" : tasks ? "Задачи" : "События";
  return <section aria-labelledby={id} aria-busy={state === "Loading" || state === "Refreshing" || undefined}
    className={`kn-planning-card ${emptyStyle ? "kn-planning-card--empty" : ""} kn-planning-card--${kind}`} data-state={state}>
    <div className="kn-home-card-header"><h2 id={id}>{title}</h2><HomeIcon name={tasks ? "pin" : "calendar"} /></div>
    {state === "Loading" ? <><span className="kn-visually-hidden" role="status">{tasks ? "Загружаем задачи…" : "Загружаем события…"}</span><SkeletonRows kind={kind} /></> :
      state === "Empty" ? <p className="kn-home-body">{tasks ? <>Добавьте задачу через бота,<br />и она появится здесь</> : <>Добавьте событие через бота,<br />и оно появится здесь</>}</p> :
      state === "AllDone" ? <p className="kn-home-body">Все задачи выполнены.<br />Новые появятся здесь.</p> :
      state === "Error" || state === "OfflineEmpty" ? <div className="kn-home-empty-message" role="status">
        <p className="kn-home-body">{state === "OfflineEmpty" ? <>Нет соединения.<br />Пока не можем загрузить {tasks ? "задачи" : "события"}.</> : <>Не удалось загрузить {tasks ? "задачи" : "события"}.<br />Попробуйте ещё раз.</>}</p>
        <HomeAction disabled={state === "OfflineEmpty"} onClick={onRetry}>Повторить</HomeAction>
      </div> : <ul className="kn-home-list">{children}</ul>}
    <SectionStatus state={state} onRetry={onRetry} />
  </section>;
}

export function SkeletonRows({ kind }: { kind: "tasks" | "events" }) {
  return <div aria-hidden="true" className="kn-home-skeleton">{[0, 1].map(i => <div key={i} className={`kn-home-skeleton__row kn-home-skeleton__row--${kind}`}>
    {kind === "tasks" ? <img src={skeletonCircle} alt="" /> : <span className="kn-home-skeleton__badge" />}
    <span className="kn-home-skeleton__text"><span /><span /></span>
  </div>)}</div>;
}

export function TaskCheckbox({ state, title, onToggle, descriptionId }: { state: TaskState; title: string; onToggle?: () => void; descriptionId?: string }) {
  const inactive = state === "Saving" || state === "Disabled" || state === "Completed";
  return <button type="button" role="checkbox" aria-checked={state === "Completed"} aria-busy={state === "Saving" || undefined}
    aria-label={`${state === "Error" ? "Повторить выполнение" : "Отметить выполненной"}: ${title}`} aria-describedby={descriptionId}
    className={`kn-task-checkbox kn-task-checkbox--${state}`} disabled={inactive} onClick={onToggle}>
    {state === "Completed" ? <><img className="kn-task-checkbox__circle" src={checkedCircle} alt="" /><img className="kn-task-checkbox__check" src={checkmark} alt="" /></> :
      state === "Saving" || state === "Error" || state === "Disabled" ? <img className={state === "Saving" ? "kn-task-checkbox__saving" : ""} src={state === "Saving" ? checkboxSaving : state === "Error" ? checkboxError : checkboxDisabled} alt="" /> : <>
        <img className="kn-task-checkbox__default" src={checkboxDefault} alt="" /><img className="kn-task-checkbox__hover" src={checkboxHover} alt="" />
        <img className="kn-task-checkbox__pressed" src={checkboxPressed} alt="" /><img className="kn-task-checkbox__focus" src={checkboxFocus} alt="" />
      </>}
  </button>;
}

function Metadata({ icon, children, danger = false }: { icon?: HomeIconName; children: ReactNode; danger?: boolean }) {
  return <span className={`kn-home-metadata-item ${danger ? "kn-home-danger" : ""}`}>{icon && <HomeIcon name={icon} />}<span>{children}</span></span>;
}

export function TaskRow({ title, date, time, person, state = "Open", onToggle }: {
  title: string; date?: string | null; time?: string | null; person?: string | null; state?: TaskState; onToggle?: () => void;
}) {
  const statusId = useId();
  const caption = { Open: null, Saving: "Сохраняем…", Completed: "Выполнено", Error: "Не сохранено. Нажмите на круг ещё раз.", Disabled: "Недоступно без сети", Overdue: "Просрочено" }[state];
  return <li className={`kn-home-task kn-home-task--${state}`} data-state={state}>
    <div className="kn-home-task__control"><TaskCheckbox state={state} title={title} onToggle={onToggle} descriptionId={caption ? statusId : undefined} /></div>
    <div className="kn-home-row-body"><p className="kn-home-body">{title}</p>
      <div className="kn-home-metadata">
        <Metadata icon="calendarMeta" danger={state === "Overdue"}>{date ?? (time ? "Без даты" : "Без срока")}</Metadata>
        {time && <Metadata icon="clock">{time}</Metadata>}{person && <Metadata icon="person">{person}</Metadata>}
      </div>
      {caption && <p id={statusId} role={state === "Error" ? "alert" : "status"} className={`kn-home-caption ${state === "Error" || state === "Overdue" ? "kn-home-danger" : ""}`}>{caption}</p>}
    </div>
  </li>;
}

export function EventRow({ title, date, time, day, month, today = false, person, allDay = false, end }: {
  title: string; date?: string | null; time?: string | null; day?: string | null; month?: string | null;
  today?: boolean; person?: string | null; allDay?: boolean; end?: string | null;
}) {
  return <li className={`kn-home-event ${today ? "kn-home-event--today" : ""}`}>
    <div className={`kn-event-badge ${today ? "kn-event-badge--today" : !day ? "kn-event-badge--unknown" : ""}`} aria-hidden="true">
      {today ? time ? <span className="kn-event-badge__time">{time}</span> : <HomeIcon name="clockToday" /> : day ? <><span className="kn-event-badge__day">{day}</span><span className="kn-event-badge__month">{month}</span></> : <HomeIcon name="calendarUnknown" />}
    </div>
    <div className="kn-home-row-body"><p className="kn-home-body">{title}</p>
      {today && <span className="kn-visually-hidden">{time ? `Сегодня, ${time}` : "Сегодня"}</span>}
      <div className="kn-home-metadata">
        {!today && <Metadata>{date ?? "Без даты"}</Metadata>}
        {!today && time && <Metadata icon="clock">{time}</Metadata>}
        {!time && (today || allDay) && <Metadata>{allDay ? "Весь день" : "Без времени"}</Metadata>}
        {end && <Metadata icon="clock">До {end}</Metadata>}
        {person && <Metadata icon="person">{person}</Metadata>}
      </div>
    </div>
  </li>;
}

export type TodayItem = { id: string; title: string; kind: "tasks" | "events"; time?: string | null };
export function TodayCard({ items, state = "Content", onRetry }: { items: TodayItem[]; state?: SectionState; onRetry: () => void }) {
  const id = useId();
  return <section className="kn-planning-card kn-today-card" aria-labelledby={id} aria-busy={state === "Loading" || state === "Refreshing" || undefined} data-state={state}>
    <div className="kn-home-card-header"><div><h2 id={id}>Не забудь</h2><p className="kn-home-caption">Сегодня</p></div><HomeIcon name="bell" /></div>
    {state === "Loading" ? <><span className="kn-visually-hidden" role="status">Загружаем дела на сегодня…</span><div className="kn-today-list" aria-hidden="true">{items.map(item => <div className="kn-today-skeleton-row" key={`${item.kind}-${item.id}`}><img src={item.kind === "tasks" ? todaySkeletonTask : todaySkeletonEvent} alt="" /></div>)}</div></> : <ul className="kn-home-list kn-today-list">{items.map(item => <li key={`${item.kind}-${item.id}`}>
      <HomeIcon name={item.kind === "tasks" ? "pinMeta" : "calendarMeta"} /><span className="kn-home-body">{item.title}</span>
      {item.time && <Metadata icon="clock">{item.time}</Metadata>}
    </li>)}</ul>}
    <SectionStatus state={state} onRetry={onRetry} />
  </section>;
}

export function InviteCard({ opening, error, disabled, unavailable = false, onOpen, className = "", inviteIcon }: { opening: boolean; error: boolean; disabled: boolean; unavailable?: boolean; onOpen: () => void; className?: string; inviteIcon?: ReactNode }) {
  const id = useId();
  return <section className={`kn-planning-card kn-invite-card ${className}`} aria-labelledby={id} data-state={error ? "Error" : opening ? "Opening" : "Default"}>
    <div className="kn-home-card-header"><h2 id={id}>Пригласить в семью</h2>{inviteIcon ?? <HomeIcon name="invitePerson" />}</div>
    <p className="kn-home-caption">Планируйте семейные дела вместе.<br />Приглашение можно получить в боте.</p>
    <HomeAction loading={opening} disabled={disabled} onClick={onOpen}>{opening ? "Открываем бота…" : error ? "Попробовать ещё раз" : "Пригласить через бота"}</HomeAction>
    {error && <p role="alert" className="kn-home-caption kn-home-danger">Не удалось открыть бота. Попробуйте ещё раз.</p>}
    {unavailable && <p className="kn-home-caption">Ссылка на бота пока недоступна.</p>}
  </section>;
}
