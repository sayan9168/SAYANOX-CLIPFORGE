"use client";
import { useMemo, useState } from "react";
import { Copy, Check } from "lucide-react";

export type SocialPack = {
  caption?: string;
  hashtags?: string[];
  hashtag_line?: string;
  post?: string;
};

type PlatformKey = "youtube" | "instagram" | "tiktok";

const STOP = new Set([
  "the","a","an","and","or","but","so","to","of","in","on","for",
  "is","are","was","were","be","it","this","that","with","you","your",
  "we","our","i","me","my","at","as","from","by","if","not","do","have",
]);

const EXTRAS: Record<PlatformKey, string[]> = {
  youtube: ["#shorts", "#youtube", "#youtubeshorts", "#subscribe"],
  instagram: ["#reels", "#instagram", "#explore", "#instareels"],
  tiktok: ["#fyp", "#foryou", "#viral", "#tiktok"],
};

const CTA: Record<PlatformKey, string> = {
  youtube: "If this helped, like and subscribe for more Shorts.",
  instagram: "Save this Reel and share it with a friend.",
  tiktok: "Watch till the end — then stitch this.",
};

function keywords(title?: string, text?: string): string[] {
  const words = `${title || ""} ${text || ""}`.match(/[A-Za-z][A-Za-z0-9']+/g) || [];
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
  return tags;
}

export function fallbackPost(title?: string, text?: string, platform: PlatformKey = "youtube"): string {
  const hook = (title || text || "Watch this clip.").trim();
  const tags = [...keywords(title, text)];
  const seen = new Set(tags.map((t) => t.toLowerCase()));
  for (const e of EXTRAS[platform]) {
    if (!seen.has(e.toLowerCase())) tags.push(e);
  }
  return `${hook}\n\n${CTA[platform]}\n\n${tags.join(" ")}`.trim();
}

function pickPost(
  key: PlatformKey,
  packs?: Partial<Record<PlatformKey, SocialPack>> | null,
  pack?: SocialPack | null,
  title?: string,
  text?: string,
): string {
  return packs?.[key]?.post || (pack?.post && key === "youtube" ? pack.post : "") || fallbackPost(title, text, key);
}

export function SocialCaption({
  pack,
  packs,
  title,
  text,
  platform,
}: {
  pack?: SocialPack | null;
  packs?: Partial<Record<PlatformKey, SocialPack>> | null;
  title?: string;
  text?: string;
  platform?: string;
}) {
  const initial: PlatformKey =
    platform === "tiktok" ? "tiktok" :
    platform === "reels" || platform === "instagram" ? "instagram" :
    "youtube";
  const [tab, setTab] = useState<PlatformKey>(initial);
  const [copied, setCopied] = useState<PlatformKey | "">("");
  const post = useMemo(
    () => pickPost(tab, packs, pack, title, text),
    [tab, packs, pack, title, text],
  );

  async function copy(key: PlatformKey) {
    const value = pickPost(key, packs, pack, title, text);
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      setTimeout(() => setCopied(""), 1500);
    } catch {}
  }

  return (
    <div className="socialCap">
      <div className="socialHead">
        <span>Caption + hashtags</span>
        <button type="button" className="chip" onClick={() => copy(tab)}>
          {copied === tab ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy {tab}</>}
        </button>
      </div>
      <div className="socialTabs">
        {(["youtube", "instagram", "tiktok"] as PlatformKey[]).map((key) => (
          <button
            key={key}
            type="button"
            className={tab === key ? "chip on" : "chip"}
            onClick={() => setTab(key)}
          >
            {key === "youtube" ? "YouTube" : key === "instagram" ? "Instagram" : "TikTok"}
          </button>
        ))}
      </div>
      <pre>{post}</pre>
    </div>
  );
}
