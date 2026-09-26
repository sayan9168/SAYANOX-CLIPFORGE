import { forward } from "../jobs/_worker";
export const runtime = "nodejs";
export async function POST(req: Request) {
  const body = await req.text();
  return forward(req, "/translate", { method: "POST", body });
}
