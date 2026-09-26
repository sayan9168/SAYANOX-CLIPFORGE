import { unavailable, workerBase, workerHeaders } from "../_worker";
export const runtime = "nodejs";

const ALLOWED = [
  /^clips\/[A-Za-z0-9._-]+\.(mp4|webm|jpg|jpeg|png)$/i,
  /^source\.(mp4|mov|mkv|webm|m4v)$/i,
  /^energy\.json$/i,
  /^render\.json$/i,
];

function allowed(path: string) {
  return ALLOWED.some((re) => re.test(path));
}

export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  const job = q.get("job") || "";
  const path = q.get("path") || "";
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(job)) {
    return Response.json({ error: "Invalid job id." }, { status: 400 });
  }
  if (!allowed(path)) {
    return Response.json({ error: "Invalid file path." }, { status: 400 });
  }
  const base = workerBase();
  if (!base) return unavailable();
  const encoded = path.split("/").map(encodeURIComponent).join("/");
  let r: Response;
  try {
    r = await fetch(`${base}/jobs/${job}/files/${encoded}`, {
      headers: workerHeaders(),
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: "Worker is unreachable." }, { status: 502 });
  }
  if (!r.ok || !r.body) {
    const data = await r.json().catch(() => ({ error: "File not found." }));
    return Response.json(data, { status: r.status || 502 });
  }
  const fallbackType =
    path.endsWith(".json") ? "application/json" :
    path.endsWith(".jpg") || path.endsWith(".jpeg") ? "image/jpeg" :
    path.endsWith(".png") ? "image/png" :
    path.endsWith(".webm") ? "video/webm" :
    "video/mp4";
  return new Response(r.body, {
    status: 200,
    headers: {
      "Content-Type": r.headers.get("Content-Type") || fallbackType,
      "Content-Length": r.headers.get("Content-Length") || "",
      "Content-Disposition": `inline; filename="${path.split("/").pop()}"`,
      "Cache-Control": path.endsWith(".json") ? "no-store" : "public, max-age=3600",
      "Accept-Ranges": "bytes",
    },
  });
}
