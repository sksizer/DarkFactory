import type { PayloadClass } from "./task.js";

export class PhaseState {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private readonly _store = new Map<string, any>();

  put(value: object, id?: string): void {
    const key = `${value.constructor.name}:${id ?? "default"}`;
    this._store.set(key, value);
  }

  get<T>(cls: PayloadClass<T>, id?: string): T;
  get<T>(cls: PayloadClass<T>, id: string | undefined, defaultValue: T): T;
  get<T>(cls: PayloadClass<T>, id?: string, defaultValue?: T): T {
    const key = `${cls.name}:${id ?? "default"}`;
    const value = this._store.get(key);
    if (value !== undefined) return value as T;
    if (arguments.length >= 3) return defaultValue as T;
    throw new Error(`PhaseState: no value for ${cls.name}:${id ?? "default"}`);
  }

  has(cls: PayloadClass, id?: string): boolean {
    return this._store.has(`${cls.name}:${id ?? "default"}`);
  }
}
