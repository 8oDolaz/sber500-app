import type { components } from "@kainem/api-client";
type Task = components["schemas"]["TaskOut"];
type Event = components["schemas"]["EventOut"];
const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
const MONTHS = ["ЯНВ", "ФЕВ", "МАР", "АПР", "МАЙ", "ИЮН", "ИЮЛ", "АВГ", "СЕН", "ОКТ", "НОЯ", "ДЕК"];

export function validTimezone(value?: string | null): string {
  try { new Intl.DateTimeFormat("ru", { timeZone: value || "Europe/Moscow" }).format(); return value || "Europe/Moscow"; }
  catch { return "Europe/Moscow"; }
}
export function validDate(value?: string | null): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const d = new Date(`${value}T12:00:00Z`);
  return Number.isFinite(d.getTime()) && d.toISOString().slice(0, 10) === value ? value : null;
}
function instant(value?: string | null): Date | null {
  if (!value || !/[T ]\d{2}:\d{2}.*(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return null;
  const d = new Date(value); return Number.isFinite(d.getTime()) ? d : null;
}
export function dayKey(date: Date, timeZone: string): string {
  const p = new Intl.DateTimeFormat("en-CA", { timeZone: validTimezone(timeZone), year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
  const get = (type: string) => p.find(x => x.type === type)!.value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}
function timeOf(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("ru-RU", { timeZone: validTimezone(timeZone), hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
}
export function formatDate(value: string): string {
  if (!validDate(value)) return "Без даты";
  const d = new Date(`${value}T12:00:00Z`);
  return `${WEEKDAYS[d.getUTCDay()]} ${value.slice(8, 10)}.${value.slice(5, 7)}`;
}
export function relativeDate(value: string, timeZone: string, now: Date): string {
  const current = dayKey(now, timeZone);
  const delta = (Date.parse(`${value}T12:00:00Z`) - Date.parse(`${current}T12:00:00Z`)) / 86_400_000;
  return delta === 0 ? "Сегодня" : delta === 1 ? "Завтра" : delta === -1 ? "Вчера" : formatDate(value);
}
export function taskPresentation(task: Task, timeZone: string, now = new Date(), timezoneKnown = true) {
  const at = instant(task.due_at);
  // A failed events request must not silently assign Moscow time to another family.
  timeZone = timezoneKnown ? timeZone : "UTC";
  const dateKey = at ? dayKey(at, timeZone) : validDate(task.due_date);
  return {
    dateKey, date: dateKey ? timezoneKnown ? relativeDate(dateKey, timeZone, now) : formatDate(dateKey) : null,
    time: at ? `${timeOf(at, timeZone)}${timezoneKnown ? "" : " UTC"}` : null, person: task.assignee_hint?.trim() || null,
    overdue: !task.done && (at ? at.getTime() < now.getTime() : timezoneKnown && dateKey !== null && dateKey < dayKey(now, timeZone)),
  };
}
export function eventPresentation(event: Event, timeZone: string, now = new Date()) {
  const at = instant(event.starts_at), until = instant(event.ends_at);
  const dateKey = at ? dayKey(at, timeZone) : validDate(event.start_date);
  const endKey = until ? dayKey(until, timeZone) : null;
  return {
    dateKey, today: dateKey !== null && dateKey === dayKey(now, timeZone),
    date: dateKey ? relativeDate(dateKey, timeZone, now) : null,
    time: at ? timeOf(at, timeZone) : null,
    day: dateKey ? String(Number(dateKey.slice(8))) : null,
    month: dateKey ? MONTHS[Number(dateKey.slice(5, 7)) - 1] : null,
    person: event.participants_hint?.trim() || null,
    end: at && until && until > at ? `${endKey !== dateKey ? `${formatDate(endKey!)}, ` : ""}${timeOf(until, timeZone)}` : null,
    allDay: event.all_day === true,
  };
}
