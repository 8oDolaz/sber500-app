import "fake-indexeddb/auto";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { transferableAbortController } from "node:util";

// Node's fetch/Request needs Node's AbortSignal, rather than jsdom's separate realm.
globalThis.AbortController = Object.getPrototypeOf(transferableAbortController()).constructor;

afterEach(() => cleanup());
