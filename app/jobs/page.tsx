import { JobBoard } from "../components/JobBoard";
import { SiteNav } from "../components/SiteNav";
import { WorkerStatus } from "../components/WorkerStatus";

export default function JobsPage() {
  return <main><SiteNav page="jobs" /><header className="pageHeader"><span className="eyebrow">YOUR PROCESSING QUEUE</span><h1>Every job, under control.</h1><p>Follow progress, reopen your edits, or stop and retry work safely.</p></header><WorkerStatus /><JobBoard /></main>;
}
