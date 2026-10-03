export class ApiError extends Error {
  constructor(message: string, public status = 0) { super(message); }
}

export function apiMessage(data: unknown, fallback = "Request failed."): string {
  if (!data || typeof data !== "object") return fallback;
  const object = data as Record<string, unknown>;
  const value = object.error ?? object.detail;
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item: { msg?: string; loc?: unknown[] }) =>
    `${item.loc?.join(".") || "request"}: ${item.msg || "Invalid value"}`).join("; ");
  return fallback;
}

export async function requestJson<T>(url: string, init: RequestInit = {}, timeoutMs = 30_000): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort(init.signal?.reason);
  if (init.signal?.aborted) abort();
  else init.signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), timeoutMs);
  try {
    const response = await fetch(url, { ...init, cache: "no-store", signal: controller.signal });
    const data: unknown = await response.json().catch(() => { throw new ApiError("Server returned an unreadable response.", response.status); });
    if (!response.ok) throw new ApiError(apiMessage(data, `Request failed (${response.status}).`), response.status);
    return data as T;
  } catch (error) {
    if (controller.signal.aborted) throw controller.signal.reason || new DOMException("Request aborted", "AbortError");
    if (error instanceof ApiError) throw error;
    throw new ApiError("Connection lost. Check your network and the worker status.");
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener("abort", abort);
  }
}

export function uploadMedia<T>(form: FormData, onProgress: (percent: number) => void, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    xhr.open("POST", "/api/jobs/upload");
    xhr.timeout = 300_000;
    const finish = () => signal.removeEventListener("abort", abort);
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress(Math.round(100 * event.loaded / event.total)); };
    xhr.onload = () => {
      finish();
      let data: unknown;
      try { data = JSON.parse(xhr.responseText); }
      catch { reject(new ApiError("Upload returned an unreadable response. Check the Jobs page before trying again.", xhr.status)); return; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T);
      else reject(new ApiError(apiMessage(data, "Upload failed."), xhr.status));
    };
    xhr.onerror = () => { finish(); reject(new ApiError("Upload connection failed. Check the Jobs page before retrying.")); };
    xhr.ontimeout = () => { finish(); reject(new ApiError("Upload timed out. Use a smaller file or a self-hosted web server.")); };
    xhr.onabort = () => { finish(); reject(new DOMException("Upload stopped", "AbortError")); };
    if (signal.aborted) { reject(new DOMException("Upload stopped", "AbortError")); return; }
    signal.addEventListener("abort", abort, { once: true });
    xhr.send(form);
  });
}
