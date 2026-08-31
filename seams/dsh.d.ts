/** Structural dsh seams. pre-execute / guard match @deepseek-ai/dsh-tools. */
export type Decision = "allow" | "deny" | "ask";

export interface ToolRegistration {
  name: string;
  description: string;
  parameters: unknown;
  output: {
    schema: unknown;
    render: (args: unknown, value: unknown) => unknown[];
  };
  execute: (args: Record<string, unknown>, exec?: { signal?: AbortSignal }) => Promise<unknown>;
}

export interface ToolExecution {
  name: string;
  arguments: unknown;
}

export interface Context {
  on: (event: string, fn: (...args: unknown[]) => unknown) => void;
  tools: {
    register: (tool: ToolRegistration) => void;
    guard?: (fn: (execution: ToolExecution) => string | undefined) => void;
  };
  sessions?: { append: (type: string, payload: unknown) => void };
}
