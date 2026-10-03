import { VALID_ID } from "../../../lib/validation";
/* Server-only worker proxy. Tokens never reach the browser. */
export const runtime = "nodejs";
export const JOB_ID = VALID_ID;
const MAX_JSON_BYTES = 128 * 1024;

export class ProxyError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export function workerBase(): string | null {
  const raw = process.env.WORKER_API_URL?.trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
    return raw.replace(/\/+$/, "");
  } catch { return null; }
}

export function workerHeaders(req?: Request, multipart = false): Headers {
  const headers = new Headers();
  if (process.env.WORKER_API_TOKEN) headers.set("Authorization", `Bearer ${process.env.WORKER_API_TOKEN}`);
  const type = req?.headers.get("content-type");
  if (type && (multipart || !type.startsWith("multipart/form-data"))) headers.set("Content-Type", type);
  const workspace = req?.headers.get("x-clipforge-user");
  if (workspace) headers.set("x-clipforge-user", workspace);
  return headers;
}

export function errorMessage(data: unknown, fallback = "Worker request failed."): string {
  if (typeof data === "string") return data.slice(0, 2000);
  if (!data || typeof data !== "object") return fallback;
  const record = data as Record<string, unknown>;
  const value = record.error ?? record.detail;
  if (typeof value === "string") return value.slice(0, 2000);
  if (Array.isArray(value)) return value.map((item) => {
    const error = item as { loc?: unknown[]; msg?: string };
    return `${error.loc?.join(".") || "request"}: ${error.msg || "Invalid value"}`;
  }).join("; ").slice(0, 2000);
  return fallback;
}

export function proxyError(error: unknown): Response {
  if (error instanceof ProxyError) return Response.json({ error: error.message }, { status: error.status });
  if (error instanceof Error && error.name === "TimeoutError") {
    return Response.json({ error: "Worker timed out. Check its health and your jobs before submitting again." }, { status: 504 });
  }
  if (error instanceof Error && error.name === "AbortError") {
    return Response.json({ error: "Request was interrupted." }, { status: 499 });
  }
  return Response.json({ error: "Worker is unreachable. Check WORKER_API_URL and restart the worker." }, { status: 502 });
}

export function unavailable() {
  return proxyError(new ProxyError("Worker is not configured. Set WORKER_API_URL and start the FastAPI worker. Demo mode is disabled.", 503));
}

function timeoutMs() {
  const seconds = Number(process.env.WORKER_REQUEST_TIMEOUT_SECONDS || 30);
  return (Number.isFinite(seconds) ? Math.max(1, Math.min(300, seconds)) : 30) * 1000;
}

export async function readJson(req: Request): Promise<Record<string, unknown>> {
  if (!req.body) throw new ProxyError("A JSON object is required.", 400);
  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_JSON_BYTES) {
        await reader.cancel();
        throw new ProxyError("Request body is too large.", 413);
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  try {
    const body: unknown = JSON.parse(new TextDecoder().decode(bytes));
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error();
    return body as Record<string, unknown>;
  } catch { throw new ProxyError("Invalid request: send a JSON object.", 400); }
}

export function jobId(req: Request): string {
  const id = new URL(req.url).searchParams.get("job") || "";
  if (!JOB_ID.test(id)) throw new ProxyError("Invalid job id.", 400);
  return id;
}

async function upstream(req: Request, path: string, init: RequestInit, signal: AbortSignal) {
  const base = workerBase();
  if (!base) throw new ProxyError("Worker is not configured. Set WORKER_API_URL and start the FastAPI worker.", 503);
  const headers = new Headers(workerHeaders(req));
  new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  if (typeof init.body === "string" && !headers.has("content-type")) headers.set("content-type", "application/json");
  return fetch(base + path, { ...init, headers, signal, cache: "no-store" });
}

export async function forward(req: Request, path: string, init: RequestInit = {}, timeout = timeoutMs()): Promise<Response> {
  const signal = AbortSignal.any([req.signal, AbortSignal.timeout(timeout)]);
  try {
    const response = await upstream(req, path, init, signal);
    let data: unknown;
    try { data = await response.json(); }
    catch {
      if (signal.aborted) throw signal.reason;
      throw new ProxyError("Worker returned invalid JSON. Check the worker version and logs.", 502);
    }
    const headers = new Headers({ "Cache-Control": "private, no-store" });
    const retry = response.headers.get("retry-after");
    if (retry) headers.set("Retry-After", retry);
    return Response.json(response.ok ? data : { ...(typeof data === "object" && data ? data : {}), error: errorMessage(data) },
      { status: response.status, headers });
  } catch (error) { return proxyError(error); }
}

export async function forwardJson(req: Request, path: string) {
  try {
    const body = await readJson(req);
    return forward(req, path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  } catch (error) { return proxyError(error); }
}

export async function forwardUpload(req: Request, path = "/jobs/upload") {
  if (!workerBase()) return unavailable();
  const type = req.headers.get("content-type") || "";
  if (!type.startsWith("multipart/form-data;") || !/boundary=/i.test(type) || !req.body) {
    return Response.json({ error: "A multipart upload with a video file is required." }, { status: 400 });
  }
  const maximum = Number(process.env.CLIPFORGE_MAX_UPLOAD_MB || 2048);
  const length = Number(req.headers.get("content-length") || 0);
  if (length > (maximum + 72) * 1024 * 1024) {
    return Response.json({ error: `Upload exceeds the configured ${maximum} MB media limit.` }, { status: 413 });
  }
  // Do not buffer multi-GB files in the Next.js process. Preserve the boundary.
  const init: RequestInit & { duplex: "half" } = {
    method: "POST", body: req.body, duplex: "half", headers: workerHeaders(req, true),
  };
  return forward(req, path, init, 300_000);
}

export async function forwardFile(req: Request, path: string, filename: string, attachment = false): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("Worker timed out", "TimeoutError")), timeoutMs());
  const headers = new Headers(workerHeaders());
  for (const name of ["range", "if-range", "if-none-match", "if-modified-since"]) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const response = await upstream(req, path, { method: "GET", headers }, AbortSignal.any([req.signal, controller.signal]));
    // A download can outlive the header timeout. Keep only request cancellation.
    if (!response.ok && ![304, 416].includes(response.status)) {
      const data: unknown = await response.json().catch(() => null);
      return Response.json({ error: errorMessage(data, "File is not available.") }, { status: response.status });
    }
    clearTimeout(timer);
    const resultHeaders = new Headers({ "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" });
    for (const name of ["content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"]) {
      const value = response.headers.get(name);
      if (value) resultHeaders.set(name, value);
    }
    resultHeaders.set("Content-Disposition", `${attachment ? "attachment" : "inline"}; filename="${filename.replace(/[^A-Za-z0-9._-]/g, "_")}"`);
    return new Response(response.status === 304 ? null : response.body, { status: response.status, headers: resultHeaders });
  } catch (error) { return proxyError(error); }
  finally { clearTimeout(timer); }
}
