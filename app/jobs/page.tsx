"use client";
import { JobBoard } from "../components/JobBoard";

export default function JobsPage() {
  return (
    <main>
      <h1>Worker job list</h1>
      <p className="sub">Live sync from GET /api/jobs/list → FastAPI store.list().</p>
      <JobBoard />
    </main>
  );
}
