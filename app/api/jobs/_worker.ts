/* Shared helpers for the /api/jobs/* proxy routes -> FastAPI worker. */
export const runtime = "nodejs";

export function workerBase(): string | null {
  return (process.env.WORKER_API_URL || "").replace(/\/+$/, "") || null;
}

export function workerHeaders(req?: Request): HeadersInit {
  const h: Record<string, string> = {};
  if (process.env.WORKER_API_TOKEN) h.Authorization = `Bearer ${process.env.WORKER_API_TOKEN}`;
  if (req) {
    const ct = req.headers.get("content-type");
    if (ct && !ct.startsWith("multipart/form-data")) h["Content-Type"] = ct;
  }
  return h;
}

export function unavailable() {
  return Response.json(
    { error: "WORKER_API_URL is not configured. Set it in .env to enable the real pipeline." },
    { status: 503 },
  );
}

/** Forward a request to the worker and return its JSON response verbatim. */
export async function forward(req: Request, path: string, init?: RequestInit): Promise<Response> {
  const base = workerBase();
  if (!base) return unavailable();
  let r: Response;
  try {
    r = await fetch(base + path, { cache: "no-store", headers: workerHeaders(req), ...init });
  } catch {
    return Response.json({ error: "Worker is unreachable." }, { status: 502 });
  }
  const data = await r.json().catch(() => ({ error: "Worker returned invalid JSON." }));
  return Response.json(data, { status: r.status });
}
