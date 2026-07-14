export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const hasJsonBody = options?.body !== undefined && !(options.body instanceof FormData);
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: hasJsonBody ? { "Content-Type": "application/json", ...options?.headers } : options?.headers,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `请求失败 (${response.status})`);
  }
  return response.json();
}
