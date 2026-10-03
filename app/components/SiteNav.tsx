import Link from "next/link";
import { FolderOpen, History, ListVideo, Scissors } from "lucide-react";

export function SiteNav({ page = "studio", onHistory }: { page?: "studio" | "jobs" | "projects"; onHistory?: () => void }) {
  return <nav className="siteNav" aria-label="Main navigation">
    <Link href="/" className="brand"><Scissors size={18} /> SAYANOX <span>CLIPFORGE</span></Link>
    <div className="navLinks">
      <Link href="/jobs" className={`tab${page === "jobs" ? " on" : ""}`}><ListVideo size={14} /> Jobs</Link>
      <Link href="/projects" className={`tab${page === "projects" ? " on" : ""}`}><FolderOpen size={14} /> Projects</Link>
      {onHistory && <button type="button" className="tab" onClick={onHistory}><History size={14} /> History</button>}
    </div>
  </nav>;
}
