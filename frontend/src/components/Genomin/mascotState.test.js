import { describe, it, expect } from "vitest";
import { pickMascotState } from "./mascotState";

const base = { entering: false, open: false, hover: false, sleeping: false, typing: false, notFound: false, found: false };

describe("pickMascotState", () => {
  it("closed widget: hover beats sleep, sleep beats entrance", () => {
    expect(pickMascotState(base)).toBe("idle");
    expect(pickMascotState({ ...base, entering: true })).toBe("entrance");
    expect(pickMascotState({ ...base, entering: true, sleeping: true })).toBe("sleep");
    expect(pickMascotState({ ...base, sleeping: true, hover: true })).toBe("hover");
  });

  it("open widget follows the search and never sleeps", () => {
    const open = { ...base, open: true, sleeping: true };
    expect(pickMascotState(open)).toBe("open");
    expect(pickMascotState({ ...open, found: true })).toBe("found");
    expect(pickMascotState({ ...open, notFound: true })).toBe("notFound");
    expect(pickMascotState({ ...open, found: true, typing: true })).toBe("typing");
  });
});
