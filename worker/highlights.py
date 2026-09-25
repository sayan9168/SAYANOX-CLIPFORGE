from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    speech_score: float = 0.5
    emotion_score: float = 0.5
    audio_score: float = 0.5
    visual_score: float = 0.5

def score(s: Segment) -> int:
    density=min(1.0,len(s.text.strip())/140.0)
    ending=1.0 if s.text.rstrip().endswith((".", "!", "?")) else 0.45
    return round(100*(density*.30+s.speech_score*.15+s.emotion_score*.15+
                      s.audio_score*.15+s.visual_score*.10+ending*.15))

def find_highlights(segments: Iterable[Segment], min_seconds=15, max_seconds=90, limit=10):
    items=list(segments); candidates=[]
    for i,s in enumerate(items):
        if not s.text.strip(): continue
        end=s.end; text=s.text.strip(); j=i+1
        while j<len(items) and end-s.start<min_seconds:
            text+=" "+items[j].text.strip(); end=items[j].end; j+=1
        if min_seconds<=end-s.start<=max_seconds:
            merged=Segment(s.start,end,text,s.speech_score,s.emotion_score,s.audio_score,s.visual_score)
            candidates.append((score(merged),merged))
    candidates.sort(key=lambda x:x[0],reverse=True); chosen=[]
    for value,s in candidates:
        if all(s.end<=old.start or s.start>=old.end for _,old in chosen):
            chosen.append((value,s))
        if len(chosen)>=limit: break
    return [{"start":round(s.start,2),"end":round(s.end,2),"score":value,"text":s.text} for value,s in chosen]
