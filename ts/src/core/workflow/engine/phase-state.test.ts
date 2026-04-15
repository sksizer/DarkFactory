import { describe, expect, it } from "bun:test";
import { PhaseState } from "./phase-state.js";

class FakePayload {
  declare readonly _brand: "FakePayload";
  readonly value: string;
  constructor(value: string) {
    this.value = value;
  }
}

class AnotherPayload {
  declare readonly _brand: "AnotherPayload";
  readonly count: number;
  constructor(count: number) {
    this.count = count;
  }
}

describe("PhaseState", () => {
  it("put and get with default id", () => {
    const state = new PhaseState();
    const payload = new FakePayload("hello");
    state.put(payload);
    const result = state.get(FakePayload);
    expect(result).toBe(payload);
    expect(result.value).toBe("hello");
  });

  it("put and get with explicit id", () => {
    const state = new PhaseState();
    const a = new FakePayload("first");
    const b = new FakePayload("second");
    state.put(a, "a");
    state.put(b, "b");
    expect(state.get(FakePayload, "a").value).toBe("first");
    expect(state.get(FakePayload, "b").value).toBe("second");
  });

  it("put overwrites existing value", () => {
    const state = new PhaseState();
    state.put(new FakePayload("original"));
    state.put(new FakePayload("updated"));
    expect(state.get(FakePayload).value).toBe("updated");
  });

  it("get throws for missing key", () => {
    const state = new PhaseState();
    expect(() => state.get(FakePayload)).toThrow(
      "PhaseState: no value for FakePayload:default"
    );
  });

  it("get throws for missing id", () => {
    const state = new PhaseState();
    state.put(new FakePayload("hello"));
    expect(() => state.get(FakePayload, "nonexistent")).toThrow(
      "PhaseState: no value for FakePayload:nonexistent"
    );
  });

  it("get with default value returns default when missing", () => {
    const state = new PhaseState();
    const fallback = new FakePayload("fallback");
    const result = state.get(FakePayload, undefined, fallback);
    expect(result).toBe(fallback);
  });

  it("get with default value returns stored value when present", () => {
    const state = new PhaseState();
    const stored = new FakePayload("stored");
    const fallback = new FakePayload("fallback");
    state.put(stored);
    const result = state.get(FakePayload, undefined, fallback);
    expect(result).toBe(stored);
  });

  it("has returns true when present", () => {
    const state = new PhaseState();
    state.put(new FakePayload("x"));
    expect(state.has(FakePayload)).toBe(true);
  });

  it("has returns false when absent", () => {
    const state = new PhaseState();
    expect(state.has(FakePayload)).toBe(false);
  });

  it("has with explicit id", () => {
    const state = new PhaseState();
    state.put(new FakePayload("x"), "myid");
    expect(state.has(FakePayload, "myid")).toBe(true);
    expect(state.has(FakePayload, "otherid")).toBe(false);
    expect(state.has(FakePayload)).toBe(false);
  });

  it("different payload types are independent", () => {
    const state = new PhaseState();
    state.put(new FakePayload("hello"));
    state.put(new AnotherPayload(42));
    expect(state.get(FakePayload).value).toBe("hello");
    expect(state.get(AnotherPayload).count).toBe(42);
  });

  it("composite key uses constructor name and id", () => {
    const state = new PhaseState();
    state.put(new FakePayload("default-val"));
    state.put(new FakePayload("named-val"), "scan");
    expect(state.get(FakePayload).value).toBe("default-val");
    expect(state.get(FakePayload, "scan").value).toBe("named-val");
  });

  it("type inference works with generic get", () => {
    const state = new PhaseState();
    state.put(new AnotherPayload(99));
    const result = state.get(AnotherPayload);
    const count: number = result.count;
    expect(count).toBe(99);
  });
});
