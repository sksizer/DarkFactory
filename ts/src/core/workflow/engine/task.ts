import type { TaskEnv, TaskOutput } from "./types.js";

// biome-ignore lint/suspicious/noExplicitAny: construct-signature variance requires any[] here — unknown[] breaks assignability from concrete class types
export type PayloadClass<T = unknown> = new (...args: any[]) => T; // eslint-disable-line @typescript-eslint/no-explicit-any

export type BrandOf<T> = T extends { readonly _brand: infer B extends string }
  ? B
  : never;

export type InputResolver = <T>(cls: PayloadClass<T>, id?: string) => T;

export interface Task<
  TReads extends string = string,
  TWrites extends string = never,
> {
  readonly name: string;
  readonly reads: readonly PayloadClass[];
  readonly writes?: PayloadClass | undefined;
  run(env: TaskEnv, resolve: InputResolver): Promise<TaskOutput> | TaskOutput;
}
