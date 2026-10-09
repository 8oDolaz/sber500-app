import type { components } from "@kainem/api-client";

type Task = components["schemas"]["TaskOut"];
type Event = components["schemas"]["EventOut"];

const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

function parts(d: Date, timeZone: string) {
  const f = new Intl.DateTimeFormat("ru-RU", {
    timeZone,
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    weekday: "short",
  }).formatToParts(d);
  const get = (t: string) => f.find((p) => p.type === t)?.value ?? "";
  return { day: `${get("day")}.${get("month")}`, time: `${get("hour")}:${get("minute")}`, weekday: get("weekday") };
}

/** "2026-09-26" → "сб 26.09" (a plain date: no timezone shift). */
export function formatDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(y!, m! - 1, d!));
  return `${WEEKDAYS[date.getUTCDay()]} ${String(d).padStart(2, "0")}.${String(m).padStart(2, "0")}`;
}

export function taskMeta(t: Task, timeZone: string): string | null {
  const bits: string[] = [];
  if (t.due_at) {
    const p = parts(new Date(t.due_at), timeZone);
    bits.push(`до ${p.weekday} ${p.day} ${p.time}`);
  } else if (t.due_date) {
    bits.push(`до ${formatDate(t.due_date)}`);
  }
  if (t.assignee_hint) bits.push(t.assignee_hint);
  return bits.length ? bits.join(" · ") : null;
}

export function eventMeta(e: Event, timeZone: string): string {
  const bits: string[] = [];
  if (e.starts_at) {
    const start = parts(new Date(e.starts_at), timeZone);
    let when = `${start.weekday} ${start.day}, ${start.time}`;
    if (e.ends_at) when += `–${parts(new Date(e.ends_at), timeZone).time}`;
    bits.push(when);
  } else if (e.start_date) {
    bits.push(`${formatDate(e.start_date)}, весь день`);
  }
  if (e.participants_hint) bits.push(e.participants_hint);
  return bits.join(" · ");
}
