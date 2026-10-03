import { forward } from "../_worker";
export const runtime = "nodejs";

export async function POST(req: Request) { return forward(req, "/jobs/cleanup", { method: "POST" }); }
