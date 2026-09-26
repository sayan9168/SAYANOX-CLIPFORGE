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
type LangKey = "en" | "bn" | "hi";

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

const CTA: Record<LangKey, Record<PlatformKey, string>> = {
  en: {
    youtube: "If this helped, like and subscribe for more Shorts.",
    instagram: "Save this Reel and share it with a friend.",
    tiktok: "Watch till the end — then stitch this.",
  },
  bn: {
    youtube: "সাহায্য হলে লাইক ও সাবসক্রাইব করুন।",
    instagram: "রিলটা সেভ করুন এবং বন্ধুদের শেয়ার করুন।",
    tiktok: "শেষ পর্যন্ত দেখুন — তারপর স্টিচ করুন।",
  },
  hi: {
    youtube: "अच्छा लगा तो लाइक और सबस्क्राइब करें।",
    instagram: "रील सेव करें और दोस्त के साथ शेयर करें।",
    tiktok: "अंत तक देखें — फिर स्टिच करें।",
  },
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

export function fallbackPost(title?: string, text?: string, platform: PlatformKey = "youtube", lang: LangKey = "en"): string {
  const hook = (title || text || "Watch this clip.").trim();
  const tags = [...keywords(title, text)];
  const seen = new Set(tags.map((t) => t.toLowerCase()));
  if (lang === "bn") tags.push("#bangla", "#bengali");
  if (lang === "hi") tags.push("#hindi", "#india");
  for (const e of EXTRAS[platform]) {
    if (!seen.has(e.toLowerCase())) tags.push(e);
  }
  return `${hook}\n\n${CTA[lang][platform]}\n\n${tags.join(" ")}`.trim();
}

export function SocialCaption({
  pack,
  packs,
  languages,
  title,
  text,
  platform,
}: {
  pack?: SocialPack | null;
  packs?: Partial<Record<PlatformKey, SocialPack>> | null;
  languages?: Partial<Record<LangKey, Partial<Record<PlatformKey, SocialPack>>>> | null;
  title?: string;
  text?: string;
  platform?: string;
}) {
  const initialP: PlatformKey =
    platform === "tiktok" ? "tiktok" :
    platform === "reels" || platform === "instagram" ? "instagram" :
    "youtube";
  const [tab, setTab] = useState<PlatformKey>(initialP);
  const [lang, setLang] = useState<LangKey>("en");
  const [copied, setCopied] = useState("");

  const post = useMemo(() => {
    return languages?.[lang]?.[tab]?.post
      || (lang === "en" ? packs?.[tab]?.post : undefined)
      || pack?.post
      || fallbackPost(title, text, tab, lang);
  }, [languages, lang, tab, packs, pack, title, text]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(post);
      setCopied(`${lang}-${tab}`);
      setTimeout(() => setCopied(""), 1500);
    } catch {}
  }

  return (
    <div className="socialCap">
      <div className="socialHead">
        <span>Caption + hashtags</span>
        <button type="button" className="chip" onClick={copy}>
          {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
        </button>
      </div>
      <div className="socialTabs">
        {(["en", "bn", "hi"] as LangKey[]).map((k) => (
          <button key={k} type="button" className={lang === k ? "chip on" : "chip"} onClick={() => setLang(k)}>
            {k === "en" ? "EN" : k === "bn" ? "বাংলা" : "हिंदी"}
          </button>
        ))}
        <span className="optLabel">·</span>
        {(["youtube", "instagram", "tiktok"] as PlatformKey[]).map((key) => (
          <button key={key} type="button" className={tab === key ? "chip on" : "chip"} onClick={() => setTab(key)}>
            {key === "youtube" ? "YouTube" : key === "instagram" ? "Instagram" : "TikTok"}
          </button>
        ))}
      </div>
      <pre>{post}</pre>
    </div>
  );
}
