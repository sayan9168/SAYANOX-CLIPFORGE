import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SAYANOX CLIPFORGE — AI Video Highlight Engine",
  description:
    "Turn long videos into share-ready short clips. Whisper transcription, smart scoring, vertical crop, burned captions — local-first.",
  keywords: ["video clips", "AI highlights", "shorts", "Whisper", "FFmpeg", "Sayanox"],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
