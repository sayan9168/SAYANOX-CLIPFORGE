"use client";
import { useState } from "react";
import { Copy, Check } from "lucide-react";

export type SocialPack = {
  caption?: string;
  hashtags?: string[];
  hashtag_line?: string;
  post?: string;
};

const STOP = new Set([
  "the","a","an","and","or","but","so","to","of","in","on","for",
  "is","are","was","were","be","it","this","that","with","you","your",
  "we","our","i","me","my","at","as","from","by","if","not","do","have",
]);

export function fallbackPost(title?: string, text?: string, platform?: string): string {
  const hook = (title || text || "Watch this clip.").trim();
  const words = `${title || ""} ${text || ""}`
    .match(/[A-Za-z][A-Za-z0-9']+/g) || [];
  const tags: string[] = [];
  const seen = new Set<string>();
  for (const w of words) {
    const clean = w.replace(/[^A-Za-z0-9]/g, "");
    if (clean.length < 3 || STOP.has(clean.toLowerCase())) continue;
    const tag = "#" + clean;
    if (seen.has(tag.toLowerCase())) continue;
    seen.add(tag.toLowerCase());
    tags.push(tag);
    if (tags.length >= 5) break;
  }
  const extras =
    platform === "tiktok" ? ["#fyp", "#viral"] :
    platform === "reels" ? ["#reels", "#instagram"] :
    ["#shorts", "#reels", "#fyp"];
  for (const e of extras) {
    if (!seen.has(e.toLowerCase())) tags.push(e);
  }
  return `${hook}\n\n${tags.join(" ")}`.trim();
}

export function SocialCaption({
  pack,
  title,
  text,
  platform,
}: {
  pack?: SocialPack | null;
  title?: string;
  text?: string;
  platform?: string;
}) {
  const [copied, setCopied] = useState(false);
  const post = pack?.post || fallbackPost(title, text, platform);
  async function copy() {
    try {
      await navigator.clipboard.writeText(post);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  }
  return (
    <div className="socialCap">
      <div className="socialHead">
        <span>English caption + hashtags</span>
        <button type="button" className="chip" onClick={copy}>
          {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
        </button>
      </div>
      <pre>{post}</pre>
    </div>
  );
}
