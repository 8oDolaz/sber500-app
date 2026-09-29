import { describe, expect, it } from "vitest";
import { challengeFor, createVerifier } from "./pkce";

describe("pkce", () => {
  it("matches the RFC 7636 example", async () => {
    expect(await challengeFor("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")).toBe(
      "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    );
  });
  it("creates 43-char url-safe verifiers", () => {
    const v = createVerifier();
    expect(v).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(createVerifier()).not.toBe(v);
  });
});
