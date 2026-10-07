import { Resend } from "resend";
import crypto from "node:crypto";

const labels=[
  ["niet relevant","not_relevant"],["not relevant","not_relevant"],
  ["te junior","too_junior"],["verkeerde locatie","wrong_location"],
  ["wrong location","wrong_location"],["te technisch","too_technical"],
  ["too technical","too_technical"],["goede inhoudelijke fit","good_domain_fit"],
  ["good fit","good_domain_fit"],["goede senioriteit","good_seniority"],
  ["relevant","relevant"],
];
export function normalize(text=""){
  const s=text.toLowerCase().replace(/\s+/g," ").trim();
  for(const [p,l] of labels) if(s.includes(p)) return l;
  return null;
}
export function identity(text=""){
  const url=(text.match(/https?:\/\/[^\s<>"']+/)||[])[0];
  if(!url) return null;
  let u; try{u=new URL(url)}catch{return null}
  const parts=u.pathname.split("/").filter(Boolean);
  const jobId=(parts.findLast?.(p=>/\d{6,}/.test(p))||parts.at(-1)||"").match(/[A-Za-z0-9_-]{6,}/)?.[0];
  if(!jobId) return null;
  return {source:u.hostname.toLowerCase(),job_id:jobId,source_url:url};
}
function senderAddress(v=""){ const m=v.match(/<([^>]+)>/); return (m?m[1]:v).trim().toLowerCase(); }
async function persist(record){
  const repo=process.env.GITHUB_REPOSITORY, branch=process.env.GITHUB_BRANCH||"vacancy-v4-clean-sheet";
  if(!repo||!process.env.GITHUB_TOKEN) throw new Error("github persistence not configured");
  const path="vacancy-v4/data/feedback/feedback.json", base="https://api.github.com/repos/"+repo+"/contents/"+path;
  for(let n=0;n<3;n++){
    const get=await fetch(base+"?ref="+encodeURIComponent(branch),{headers:{Authorization:"Bearer "+process.env.GITHUB_TOKEN,Accept:"application/vnd.github+json"}});
    let rows=[],sha;
    if(get.status===200){const j=await get.json();sha=j.sha;rows=JSON.parse(Buffer.from(j.content,"base64").toString("utf8"))}
    else if(get.status!==404) throw new Error("feedback ledger read failed "+get.status);
    if(rows.some(x=>x.message_id===record.message_id)) return "duplicate";
    rows.push(record);
    const body={message:"v4: persist vacancy feedback "+record.message_id,content:Buffer.from(JSON.stringify(rows,null,2)+"\n").toString("base64"),branch,...(sha?{sha}:{})};
    const put=await fetch(base,{method:"PUT",headers:{Authorization:"Bearer "+process.env.GITHUB_TOKEN,Accept:"application/vnd.github+json","Content-Type":"application/json"},body:JSON.stringify(body)});
    if(put.ok)return "stored"; if(put.status!==409&&put.status!==422)throw new Error("feedback ledger write failed "+put.status);
  }
  throw new Error("feedback ledger contention");
}
export const config={api:{bodyParser:false}};
const BUTTON_LABELS=new Set(["relevant","not_relevant","too_junior","wrong_location","too_technical","good_domain_fit","good_seniority"]);
function safe(v=""){return String(v).replace(/[<>&"']/g,ch=>({"<":"&lt;",">":"&gt;","&":"&amp;","\"":"&quot;","'":"&#39;"}[ch]))}
export function verifyFeedbackToken(token){
  const secret=process.env.FEEDBACK_LINK_SECRET;if(!secret||!token)return null;
  const [body,sig]=String(token).split(".");if(!body||!sig)return null;
  const expected=crypto.createHmac("sha256",secret).update(body).digest("base64url");
  if(sig.length!==expected.length||!crypto.timingSafeEqual(Buffer.from(sig),Buffer.from(expected)))return null;
  try{const p=JSON.parse(Buffer.from(body,"base64url").toString("utf8"));if(!p.source||!p.job_id||!p.label||!BUTTON_LABELS.has(p.label))return null;return p}catch{return null}
}
function feedbackPage(ok,message){return `<!doctype html><meta name="viewport" content="width=device-width"><title>Vacaturefeedback</title><main style="font-family:system-ui;max-width:38rem;margin:4rem auto;padding:1rem"><h1>${ok?"Feedback opgeslagen":"Feedback niet verwerkt"}</h1><p>${safe(message)}</p></main>`}

async function rawBody(req){const chunks=[];for await(const chunk of req)chunks.push(Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk));return Buffer.concat(chunks).toString("utf8")}
export default async function handler(req,res){
  if(req.method==="GET"){
    try{
      const u=new URL(req.url,"https://feedback.invalid"),p=verifyFeedbackToken(u.searchParams.get("t"));
      if(!p)return res.status(400).send(feedbackPage(false,"De feedbacklink is ongeldig of beschadigd."));
      const record={source:p.source,job_id:String(p.job_id),label:p.label,received_at:new Date().toISOString(),message_id:"link:"+crypto.createHash("sha256").update(u.searchParams.get("t")).digest("hex"),source_url:p.source_url||""};
      const status=await persist(record);
      return res.status(200).send(feedbackPage(true,status==="duplicate"?"Deze feedback was al opgeslagen.":"Dank. Deze feedback wordt begrensd meegenomen in toekomstige matchscores."));
    }catch{return res.status(500).send(feedbackPage(false,"Opslaan is mislukt."))}
  }
  if(req.method!=="POST")return res.status(405).send("method not allowed");
  try{
    const raw=await rawBody(req);
    const resend=new Resend(process.env.RESEND_API_KEY);
    const event=resend.webhooks.verify({payload:raw,headers:{"svix-id":req.headers["svix-id"],"svix-timestamp":req.headers["svix-timestamp"],"svix-signature":req.headers["svix-signature"]},secret:process.env.RESEND_WEBHOOK_SECRET});
    if(event.type!=="email.received")return res.status(200).send("ignored");
    if(senderAddress(event.data.from)!==(process.env.ALLOWED_SENDER||"").toLowerCase())return res.status(200).send("rejected");
    const {data:mail,error}=await resend.emails.receiving.get(event.data.email_id); if(error)throw error;
    const text=mail.text||"";
    const label=normalize(text), id=identity(text);
    if(!label||!id)return res.status(200).send("review");
    const record={source:id.source,job_id:id.job_id,label,received_at:new Date().toISOString(),message_id:event.data.email_id,source_url:id.source_url};
    const status=await persist(record);
    return res.status(200).json({status});
  }catch(e){return res.status(400).send("invalid webhook")}
}
