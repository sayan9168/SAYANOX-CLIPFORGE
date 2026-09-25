import os,subprocess,uuid
from pathlib import Path
from fastapi import FastAPI,File,UploadFile,HTTPException
from fastapi.responses import FileResponse
from .highlights import Segment,find_highlights

app=FastAPI(title="SAYANOX CLIPFORGE Worker",version="0.3.0")
ROOT=Path(os.getenv("CLIPFORGE_DATA","/tmp/clipforge")); ROOT.mkdir(parents=True,exist_ok=True)

def ffmpeg(*args:str):
    p=subprocess.run(["ffmpeg","-hide_banner","-loglevel","error",*args],capture_output=True,text=True)
    if p.returncode: raise RuntimeError(p.stderr[-2000:])

@app.get("/health")
def health(): return {"ok":True,"service":"clipforge-worker","version":"0.3.0"}

@app.post("/highlights")
async def highlights(video:UploadFile=File(...),segments:str="",min_seconds:float=15,max_seconds:float=60,limit:int=5):
    if max_seconds<min_seconds: raise HTTPException(400,"max_seconds must be >= min_seconds")
    if not video.filename: raise HTTPException(400,"Missing filename.")
    job=uuid.uuid4().hex; work=ROOT/job; work.mkdir(); src=work/"source"
    with src.open("wb") as f:
        while chunk:=await video.read(1024*1024): f.write(chunk)
    # Transcript/vision adapters belong here. Never fabricate transcript data.
    return {"job_id":job,"status":"uploaded","clips":[],"message":"Media accepted. Supply timestamped transcript segments to the scoring adapter."}

@app.post("/score")
async def score_segments(payload:dict):
    raw=payload.get("segments",[])
    try:
        segs=[Segment(float(x["start"]),float(x["end"]),str(x.get("text","")),
                      float(x.get("speech_score",.5)),float(x.get("emotion_score",.5)),
                      float(x.get("audio_score",.5)),float(x.get("visual_score",.5))) for x in raw]
        return {"clips":find_highlights(segs,float(payload.get("min_seconds",15)),float(payload.get("max_seconds",60)),int(payload.get("limit",5)))}
    except (KeyError,TypeError,ValueError) as e: raise HTTPException(400,f"Invalid segment data: {e}")

@app.post("/clip")
async def create_clip(video:UploadFile=File(...),start:float=0,end:float=30):
    if end<=start or end-start>300: raise HTTPException(400,"Clip must be 0-300 seconds.")
    if not video.filename: raise HTTPException(400,"Missing filename.")
    job=uuid.uuid4().hex; work=ROOT/job; work.mkdir(); src=work/"source"; out=work/"clip.mp4"
    with src.open("wb") as f:
        while chunk:=await video.read(1024*1024): f.write(chunk)
    try: ffmpeg("-ss",str(start),"-i",str(src),"-t",str(end-start),"-map","0:v:0","-map","0:a:0?","-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-movflags","+faststart",str(out))
    except RuntimeError as e: raise HTTPException(500,f"FFmpeg failed: {e}")
    return {"job_id":job,"duration":round(end-start,3),"download":f"/clip/{job}"}

@app.get("/clip/{job_id}")
def download_clip(job_id:str):
    path=ROOT/job_id/"clip.mp4"
    if not path.is_file(): raise HTTPException(404,"Clip not found.")
    return FileResponse(path,media_type="video/mp4",filename=f"clipforge-{job_id}.mp4")
