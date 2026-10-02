"use client";
import Link from "next/link";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main><div className="emptyState"><h1>The studio hit a snag.</h1><p>Your worker jobs run independently. Try reopening the page or check the queue before submitting again.</p><div className="historyActions"><button type="button" className="renderBtn" onClick={reset}>Try again</button><Link href="/jobs" className="chip">View jobs</Link></div></div></main>;
}
