import { forwardUpload } from "../jobs/_worker";
export const runtime = "nodejs";

export async function POST(req: Request) { return forwardUpload(req, "/clip"); }
