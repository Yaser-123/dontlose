export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export function fileUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new Error("The local API isn't running. Start the backend on port 8000.");
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let data: { detail?: unknown } | null = null;
  if (text) {
    try {
      data = JSON.parse(text) as { detail?: unknown };
    } catch {
      throw new Error("The local API returned an unreadable response.");
    }
  }
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : "The request failed.");
  }
  return data as T;
}
