import { describe, expect, it } from "vitest";
import { detectOs, parseLaunchContext } from "./web";

describe("detectOs", () => {
  it.each([
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", 5, "ios"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", 5, "ios"], // iPadOS
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", 0, "desktop"],
    ["Mozilla/5.0 (Linux; Android 15; Pixel 9)", 5, "android"],
  ] as const)("%s → %s", (ua, touch, os) => {
    expect(detectOs(ua, touch)).toBe(os);
  });
});

describe("parseLaunchContext", () => {
  it("keeps utm_* params and ignores others", () => {
    expect(parseLaunchContext("?utm_source=tg&utm_campaign=s500&foo=1")).toEqual({
      utm: { utm_source: "tg", utm_campaign: "s500" },
    });
  });
  it("is empty without params", () => {
    expect(parseLaunchContext("")).toEqual({});
  });
});
