import { forward, workerBase } from "../jobs/_worker";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const configured = Boolean(workerBase());
  let worker: Record<string, unknown> = { configured, reachable: false };
  if (configured) {
    const response = await forward(req, "/health", { method: "GET" }, 5000);
    const data = await response.json();
    if (response.ok && data.auth_required) {
      const authenticated = await forward(req, "/auth-check", { method: "GET" }, 3000);
      if (!authenticated.ok) {
        return Response.json({ ok: true, service: "sayanox-clipforge", timestamp: new Date().toISOString(), worker: {
          ...data, configured, reachable: true, ready: false,
          error: "Worker authentication failed. Set the same WORKER_API_TOKEN on the web server and worker.",
        } }, { headers: { "Cache-Control": "no-store" } });
      }
    }
    worker = response.ok ? { ...data, configured, reachable: true }
      : { configured, reachable: false, error: data.error || "Worker health check failed." };
  }
  return Response.json({ ok: true, service: "sayanox-clipforge", timestamp: new Date().toISOString(), worker },
    { headers: { "Cache-Control": "no-store" } });
}
