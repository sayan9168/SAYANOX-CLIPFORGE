import { forwardJson } from "../jobs/_worker";
export const runtime = "nodejs";

export async function POST(req: Request) { return forwardJson(req, "/translate"); }
