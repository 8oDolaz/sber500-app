import { describe, expect, it } from "vitest";
import { eventMeta, formatDate, taskMeta } from "./format";

const task = { id: "t", title: "x", due_date: null, due_at: null, assignee_hint: null, done: false };
const event = { id: "e", title: "x", all_day: false, starts_at: null, ends_at: null, start_date: null, participants_hint: null };

describe("format", () => {
  it("formats plain dates without timezone shifts", () => {
    expect(formatDate("2026-09-26")).toBe("сб 26.09");
  });
  it("task meta: deadline and assignee", () => {
    expect(taskMeta({ ...task, due_date: "2026-09-26", assignee_hint: "Дима" }, "Europe/Moscow")).toBe("до сб 26.09 · Дима");
    expect(taskMeta({ ...task, due_date: "2026-09-26", due_at: "2026-09-26T15:00:00Z" }, "Europe/Moscow")).toBe(
      "до сб 26.09 18:00",
    );
    expect(taskMeta(task, "Europe/Moscow")).toBeNull();
  });
  it("event meta in the family's timezone", () => {
    expect(
      eventMeta({ ...event, starts_at: "2026-09-29T10:00:00Z", ends_at: "2026-09-29T11:30:00Z", participants_hint: "Даша" }, "Europe/Moscow"),
    ).toBe("вт 29.09, 13:00–14:30 · Даша");
    expect(eventMeta({ ...event, all_day: true, start_date: "2026-10-02" }, "Europe/Moscow")).toBe("пт 02.10, весь день");
  });
});
