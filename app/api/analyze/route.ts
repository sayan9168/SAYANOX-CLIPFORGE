import {NextResponse} from "next/server";
export const runtime="nodejs";
const yt=/^https?:\/\/(www\.)?(youtube\.com|youtu\.be)\//i;

/* POST /api/analyze {url,...} -> REAL pipeline: forwards to the worker job
   queue (POST /jobs/youtube) and returns {job_id,status}. The browser then
   polls GET /api/jobs/status?job=<id> until the analyze job completes.
   When WORKER_API_URL is not configured we fall back to explicit demo data
   (mode:"demo") so local development keeps working. */
export async function POST(req:Request){
 let body:any={};
 try{body=await req.json();}catch{return NextResponse.json({error:"Invalid request."},{status:400})}
 const url=String(body?.url||"").trim();
 if(!yt.test(url))return NextResponse.json({error:"Enter a valid YouTube URL."},{status:400});
 const base=(process.env.WORKER_API_URL||"").replace(/\/+$/,"");
 if(base){
  const payload:Record<string,unknown>={url};
  for(const k of["min_seconds","max_seconds","limit"]){
   if(body?.[k]!==undefined&&body?.[k]!==null&&body?.[k]!=="")payload[k]=Number(body[k]);
  }
  const headers:Record<string,string>={"content-type":"application/json"};
  if(process.env.WORKER_API_TOKEN)headers.Authorization=`Bearer ${process.env.WORKER_API_TOKEN}`;
  try{
   const r=await fetch(base+"/jobs/youtube",{method:"POST",headers,body:JSON.stringify(payload),cache:"no-store"});
   const data=await r.json().catch(()=>({error:"Worker returned invalid JSON."}));
   if(!r.ok)return NextResponse.json({error:data.detail||data.error||"Worker rejected the job."},{status:r.status});
   return NextResponse.json({mode:"worker",job_id:data.job_id,status:data.status,note:data.note||null});
  }catch{
   return NextResponse.json({error:"Worker is unreachable. Is it running?"},{status:502});
  }
 }
 // No worker configured -> clearly-labelled demo mode (never presented as real results).
 return NextResponse.json({status:"queued",mode:"demo",message:"WORKER_API_URL is not configured — showing demo results.",clips:[{id:1,start:873,end:907,score:92,title:"The strongest moment",reason:"Demo highlight: hook + complete thought."},{id:2,start:1142,end:1175,score:88,title:"Key insight",reason:"Demo highlight: self-contained statement."},{id:3,start:1540,end:1571,score:84,title:"Best reaction",reason:"Demo highlight: audio/emotion peak."}]});
}
