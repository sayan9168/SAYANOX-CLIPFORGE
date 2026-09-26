import { forward } from "../jobs/_worker";
export const runtime = "nodejs";
export async function GET(req: Request) {
  return forward(req, "/projects", { method: "GET" });
}
export async function POST(req: Request) {
  const body = await req.text();
  return forward(req, "/projects", { method: "POST", body });
}
