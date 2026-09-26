import { forward } from "../_worker";
export const runtime = "nodejs";

/* POST /api/jobs/retry?job=<id> */
export async function POST(req: Request) {
  const job = new URL(req.url).searchParams.get("job") || "";
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(job)) {
    return Response.json({ error: "Invalid job id." }, { status: 400 });
  }
  return forward(req, `/jobs/${job}/retry`, { method: "POST" });
}
