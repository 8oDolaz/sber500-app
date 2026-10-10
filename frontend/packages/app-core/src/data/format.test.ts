import { describe, expect, it } from "vitest";
import { dayKey, eventPresentation, formatDate, taskPresentation, validDate, validTimezone } from "./format";
const task = { id: "t", title: "x", due_date: null, due_at: null, assignee_hint: null, done: false };
const event = { id: "e", title: "x", all_day: false, starts_at: null, ends_at: null, start_date: null, participants_hint: null };
const now = new Date("2026-10-10T10:00:00Z");

describe("planning presentation", () => {
  it("preserves plain dates across timezones and rejects impossible dates", () => {
    expect(formatDate("2026-09-26")).toBe("сб 26.09");
    expect(validDate("2026-02-30")).toBeNull();
    expect(taskPresentation({ ...task, due_date: "2026-10-10" }, "Pacific/Honolulu", now)).toMatchObject({ date: "Сегодня", time: null, overdue: false });
  });
  it("does not invent a deadline, a person, midnight or an all-day flag", () => {
    expect(taskPresentation(task, "Europe/Moscow", now)).toMatchObject({ dateKey: null, date: null, time: null, person: null, overdue: false });
    expect(eventPresentation(event, "Europe/Moscow", now)).toMatchObject({ dateKey: null, time: null, today: false, person: null, allDay: false });
    expect(eventPresentation({ ...event, start_date: "2026-10-10" }, "Europe/Moscow", now).allDay).toBe(false);
  });
  it("uses the instant in the family timezone at midnight, even if due_date is UTC", () => {
    const view = taskPresentation({ ...task, due_at: "2026-10-09T23:30:00Z", due_date: "2026-10-09", assignee_hint: " Маша " }, "Europe/Moscow", now);
    expect(view).toMatchObject({ dateKey: "2026-10-10", date: "Сегодня", time: "02:30", person: "Маша", overdue: true });
    expect(dayKey(new Date("2026-10-10T23:30:00Z"), "Europe/Moscow")).toBe("2026-10-11");
  });
  it("keeps a date-only deadline open until the next family day", () => {
    expect(taskPresentation({ ...task, due_date: "2026-10-10" }, "Europe/Moscow", now).overdue).toBe(false);
    expect(taskPresentation({ ...task, due_date: "2026-10-09" }, "Europe/Moscow", now).overdue).toBe(true);
  });
  it("handles DST and does not label an overnight end as the same day", () => {
    expect(eventPresentation({ ...event, starts_at: "2026-10-25T00:30:00Z" }, "Europe/Berlin", now).time).toBe("02:30");
    expect(eventPresentation({ ...event, starts_at: "2026-10-10T20:00:00Z", ends_at: "2026-10-10T22:00:00Z" }, "Europe/Moscow", now).end).toBe("вс 11.10, 01:00");
  });
  it("uses a safe timezone for invalid backend values", () => { expect(validTimezone("bad/zone")).toBe("Europe/Moscow"); });
  it("uses explicit UTC and absolute dates until the family timezone is available", () => {
    expect(taskPresentation({ ...task, due_at: "2026-10-10T20:30:00Z" }, "Europe/Moscow", now, false)).toMatchObject({ date: "сб 10.10", time: "20:30 UTC" });
    expect(taskPresentation({ ...task, due_date: "2026-10-09" }, "Europe/Moscow", now, false).overdue).toBe(false);
  });
});
