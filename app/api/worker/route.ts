import {NextResponse} from "next/server";
export const runtime="nodejs";
export async function POST(req:Request){
 const worker=process.env.WORKER_API_URL;
 if(!worker)return NextResponse.json({error:"WORKER_API_URL is not configured."},{status:503});
 const form=await req.formData(); const video=form.get("video");
 if(!(video instanceof File))return NextResponse.json({error:"video file is required."},{status:400});
 const body=new FormData(); body.append("video",video,video.name||"video.mp4");
 body.append("start",String(form.get("start")??0)); body.append("end",String(form.get("end")??30));
 const headers:HeadersInit={}; if(process.env.WORKER_API_TOKEN)headers.Authorization=`Bearer ${process.env.WORKER_API_TOKEN}`;
 const r=await fetch(worker+"/clip",{method:"POST",body,headers});
 const data=await r.json().catch(()=>({error:"Worker returned invalid JSON."}));
 return NextResponse.json(data,{status:r.status});
}