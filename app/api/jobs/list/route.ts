import { forward } from "../_worker";
export const runtime = "nodejs";

export async function GET(req: Request) {
  const query = new URL(req.url).searchParams;
  const params = new URLSearchParams();
  for (const key of ["limit", "status"]) if (query.has(key)) params.set(key, query.get(key) || "");
  return forward(req, `/jobs?${params}`, { method: "GET" });
}
