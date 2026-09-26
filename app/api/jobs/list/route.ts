import { forward } from "../_worker";
export const runtime = "nodejs";
export async function GET(req: Request) {
  return forward(req, "/jobs", { method: "GET" });
}
