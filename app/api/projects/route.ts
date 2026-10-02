import { forward, forwardJson, JOB_ID, proxyError, ProxyError } from "../jobs/_worker";
export const runtime = "nodejs";

function projectPath(req: Request, required = false) {
  const id = new URL(req.url).searchParams.get("id");
  if (id !== null && !JOB_ID.test(id)) throw new ProxyError("Invalid project id.", 400);
  if (required && !id) throw new ProxyError("Project id is required.", 400);
  return id ? `/projects/${id}` : "/projects";
}

export async function GET(req: Request) {
  try { return forward(req, projectPath(req), { method: "GET" }); }
  catch (error) { return proxyError(error); }
}
export async function POST(req: Request) { return forwardJson(req, "/projects"); }
export async function DELETE(req: Request) {
  try { return forward(req, projectPath(req, true), { method: "DELETE" }); }
  catch (error) { return proxyError(error); }
}
