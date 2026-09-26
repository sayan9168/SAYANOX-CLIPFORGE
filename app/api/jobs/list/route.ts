import { forward } from "../../jobs/_worker";
export const runtime = "nodejs";
export async function GET(req: Request) {
  return forward(req, "/jobs", { method: "GET" });
}
