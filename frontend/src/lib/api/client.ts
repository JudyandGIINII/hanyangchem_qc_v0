import type { paths } from "./generated";

export class ApiError extends Error {
  public readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function apiBase(): string {
  if (typeof window !== "undefined") {
    return window.localStorage.getItem("P3_API_BASE") ?? "http://127.0.0.1:18000";
  }
  return "http://127.0.0.1:18000";
}

export async function apiRequest<T>(
  path: keyof paths | string,
  init: NonNullable<Parameters<typeof fetch>[1]> = {},
  sessionHandle?: string,
): Promise<{ status: number; body: T }> {
  const headers = new Headers(init.headers);
  if (sessionHandle) headers.set("Authorization", `Bearer ${sessionHandle}`);
  const response = await fetch(`${apiBase()}${path}`, { ...init, headers });
  const body = (await response.json()) as T & { message?: string };
  if (!response.ok) throw new ApiError(response.status, body.message ?? `API ${response.status}`);
  return { status: response.status, body };
}
