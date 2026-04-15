import type { BrandOf, Task } from "./engine/task.js";
import type {
  FailureHandler,
  InputMapping,
  WrappedTask,
} from "./engine/types.js";
import type { Workflow } from "./types.js";

export class WorkflowBuilder<Ctx extends string = never> {
  private readonly _name: string;
  private readonly _description: string;
  private _category: string;
  private readonly _seeds: Array<{ value: unknown }>;
  private readonly _tasks: WrappedTask[];

  constructor(name: string, description: string, category: string) {
    this._name = name;
    this._description = description;
    this._category = category;
    this._seeds = [];
    this._tasks = [];
  }

  cat(category: string): this {
    this._category = category;
    return this;
  }

  seed<T extends { readonly _brand: string }>(
    value: T
  ): WorkflowBuilder<Ctx | BrandOf<T>> {
    this._seeds.push({ value });
    return this as unknown as WorkflowBuilder<Ctx | BrandOf<T>>;
  }

  add<R extends Ctx, W extends string>(
    task: Task<R, W>,
    options?: { onFailure?: FailureHandler }
  ): WorkflowBuilder<Ctx | W> {
    this._tasks.push({
      task,
      inputMapping: undefined,
      outputId: undefined,
      onFailure: options?.onFailure,
    });
    return this as unknown as WorkflowBuilder<Ctx | W>;
  }

  named<R extends Ctx, W extends string>(
    id: string,
    task: Task<R, W>
  ): WorkflowBuilder<Ctx | `${W}:${string}`> {
    this._tasks.push({ task, inputMapping: undefined, outputId: id });
    return this as unknown as WorkflowBuilder<Ctx | `${W}:${string}`>;
  }

  from<R extends Ctx, W extends string>(
    mapping: InputMapping,
    task: Task<R, W>
  ): WorkflowBuilder<Ctx | W> {
    this._tasks.push({ task, inputMapping: mapping, outputId: undefined });
    return this as unknown as WorkflowBuilder<Ctx | W>;
  }

  build(): Workflow {
    return {
      name: this._name,
      description: this._description,
      category: this._category,
      seeds: this._seeds.map((s) => s.value),
      tasks: this._tasks,
    };
  }
}

export function workflow(
  name: string,
  description: string,
  category?: string
): WorkflowBuilder {
  return new WorkflowBuilder(name, description, category ?? "default");
}
