import type { PayloadClass } from "./task.js";

const NO_DEFAULT: unique symbol = Symbol("PhaseState.NO_DEFAULT");

export class PhaseState {
  private readonly _store = new Map<string, unknown>();

  put(value: object, id?: string): void {
    const key = `${value.constructor.name}:${id ?? "default"}`;
    this._store.set(key, value);
  }

  get<T>(cls: PayloadClass<T>, id?: string): T;
  get<T>(cls: PayloadClass<T>, id: string | undefined, defaultValue: T): T;
  get<T>(
    cls: PayloadClass<T>,
    id?: string,
    defaultValue: T | typeof NO_DEFAULT = NO_DEFAULT
  ): T {
    const key = `${cls.name}:${id ?? "default"}`;
    const value = this._store.get(key);
    if (value !== undefined) return value as T;
    if (defaultValue !== NO_DEFAULT) return defaultValue;
    throw new Error(`PhaseState: no value for ${cls.name}:${id ?? "default"}`);
  }

  has(cls: PayloadClass, id?: string): boolean {
    return this._store.has(`${cls.name}:${id ?? "default"}`);
  }
}
