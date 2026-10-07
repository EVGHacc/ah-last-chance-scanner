import { Resend } from "resend";
import crypto from "node:crypto";

const labels=[
  ["niet relevant","not_relevant"],["not relevant","not_relevant"],
  ["te junior","too_junior"],["verkeerde locatie","wrong_location"],
  ["wrong location","wrong_location"],["te technisch","too_technical"],
  ["too technical","too_technical"],["onvoldoende ervaring","insufficient_experience"],["geen management rol","no_management_role"],["goede inhoudelijke fit","good_domain_fit"],
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
function feedbackFeatures(p){
  const text=[p.title,p.summary,p.description,p.department,p.team,p.office,p.location].filter(Boolean).join(" ").toLowerCase();
  const domains=["aml","anti-money laundering","financial crime","fincrime","sanctions","compliance","regulatory","internal audit","governance","non-financial risk","risk assurance","controls","trust & safety","responsible ai"].filter(x=>text.includes(x));
  return {domains,technical:["engineer","engineering","developer","software","data scientist","machine learning","architect","technical","technology"].some(x=>text.includes(x)),junior:["intern","internship","graduate","junior","associate"].some(x=>new RegExp("\\b"+x+"\\b").test((p.title||"").toLowerCase())),management:["chief","cco","cro","mlro","head","director","senior manager","manager","lead","people manager","team lead"].some(x=>text.includes(x)),outside_location:!["amsterdam","netherlands","london","remote"].some(x=>(p.location||p.office||"").toLowerCase().includes(x))};
}
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
const BUTTON_LABELS=new Set(["relevant","not_relevant","too_junior","wrong_location","too_technical","insufficient_experience","no_management_role","good_domain_fit","good_seniority"]);
function safe(v=""){return String(v).replace(/[<>&"']/g,ch=>({"<":"&lt;",">":"&gt;","&":"&amp;","\"":"&quot;","'":"&#39;"}[ch]))}
export function signFeedbackToken(payload){
  const secret=process.env.FEEDBACK_LINK_SECRET;if(!secret)throw new Error("feedback signing not configured");
  const body=Buffer.from(JSON.stringify(payload)).toString("base64url");
  const sig=crypto.createHmac("sha256",secret).update(body).digest("base64url");
  return body+"."+sig;
}
export function feedbackLinks({source,job_id,source_url=""},baseUrl){
  const base=String(baseUrl||"").replace(/\/$/,"");
  return Object.fromEntries([...BUTTON_LABELS].map(label=>[label,base+"/api/webhook?t="+encodeURIComponent(signFeedbackToken({source:String(source),job_id:String(job_id),source_url,label}))]));
}
export function verifyFeedbackToken(token){
  const secret=process.env.FEEDBACK_LINK_SECRET;if(!secret||!token)return null;
  const [body,sig]=String(token).split(".");if(!body||!sig)return null;
  const expected=crypto.createHmac("sha256",secret).update(body).digest("base64url");
  if(sig.length!==expected.length||!crypto.timingSafeEqual(Buffer.from(sig),Buffer.from(expected)))return null;
  try{const p=JSON.parse(Buffer.from(body,"base64url").toString("utf8"));if(!p.source||!p.job_id||!p.label||!BUTTON_LABELS.has(p.label))return null;return p}catch{return null}
}
function feedbackPage(ok,message,token=""){const form=token?`<form method="post" style="margin-top:1.5rem"><input type="hidden" name="t" value="${safe(token)}"><button type="submit" style="font:inherit;padding:.7rem 1rem">Feedback bevestigen</button></form>`:"";return `<!doctype html><meta name="viewport" content="width=device-width"><title>Vacaturefeedback</title><main style="font-family:system-ui;max-width:38rem;margin:4rem auto;padding:1rem"><h1>${ok?"Vacaturefeedback":"Feedback niet verwerkt"}</h1><p>${safe(message)}</p>${form}</main>`}

function categoryPage(source,job_id,source_url){return `<!doctype html><meta name="viewport" content="width=device-width"><title>Nieuwe feedbackcategorie</title><main style="font-family:system-ui;max-width:38rem;margin:4rem auto;padding:1rem"><h1>Nieuwe categorie toevoegen</h1><p>Beschrijf kort waarom deze vacature niet goed past. Dit wordt opgeslagen als voorstel en verandert de matchscore pas nadat de categorie expliciet in het model is opgenomen.</p><form method="post"><input type="hidden" name="action" value="custom_category"><input type="hidden" name="source" value="${safe(source)}"><input type="hidden" name="job_id" value="${safe(job_id)}"><input type="hidden" name="source_url" value="${safe(source_url)}"><input name="custom_label" maxlength="160" required style="font:inherit;padding:.7rem;width:100%;box-sizing:border-box"><button type="submit" style="font:inherit;padding:.7rem 1rem;margin-top:1rem">Categorie opslaan</button></form></main>`}
async function rawBody(req){const chunks=[];for await(const chunk of req)chunks.push(Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk));return Buffer.concat(chunks).toString("utf8")}
export default async function handler(req,res){
  if(req.method==="GET"){
    const u=new URL(req.url,"https://feedback.invalid");
    if(u.searchParams.get("mode")==="links"){
      const source=u.searchParams.get("source"),job_id=u.searchParams.get("job_id"),source_url=u.searchParams.get("source_url")||"";
      if(!source||!job_id||!/^[A-Za-z0-9_-]{3,128}$/.test(job_id))return res.status(400).json({error:"invalid identity"});
      const host=req.headers["x-forwarded-host"]||req.headers.host,proto=req.headers["x-forwarded-proto"]||"https";
      return res.status(200).json(feedbackLinks({source,job_id,source_url},proto+"://"+host));
    }
    if(u.searchParams.get("source")&&u.searchParams.get("job_id")&&u.searchParams.get("action")==="add_category"){
      const source=u.searchParams.get("source"),job_id=u.searchParams.get("job_id"),source_url=u.searchParams.get("source_url")||"";
      if(!/^[A-Za-z0-9_-]{3,128}$/.test(job_id))return res.status(400).send(feedbackPage(false,"Ongeldige vacature-identiteit."));
      return res.status(200).send(categoryPage(source,job_id,source_url));
    }
    if(u.searchParams.get("source")&&u.searchParams.get("job_id")&&u.searchParams.get("label")){
      const source=u.searchParams.get("source"),job_id=u.searchParams.get("job_id"),label=u.searchParams.get("label"),source_url=u.searchParams.get("source_url")||"";
      if(!BUTTON_LABELS.has(label)||!/^[A-Za-z0-9_-]{3,128}$/.test(job_id))return res.status(400).send(feedbackPage(false,"Ongeldige feedbackkeuze."));
      const token=signFeedbackToken({source,job_id,source_url,label});
      return res.status(200).send(feedbackPage(true,"Keuze: "+label+". Bevestig om deze voorkeur op te slaan.",token));
    }
  }
  if(req.method==="POST" && req.headers["x-feedback-link-request"]==="1"){
    try{
      const raw=await rawBody(req), body=JSON.parse(raw||"{}");
      if(!body.source||!body.job_id)return res.status(400).json({error:"source and job_id required"});
      const host=req.headers["x-forwarded-host"]||req.headers.host;
      const proto=req.headers["x-forwarded-proto"]||"https";
      return res.status(200).json(feedbackLinks(body,proto+"://"+host));
    }catch{return res.status(400).json({error:"invalid request"})}
  }
  if(req.method==="GET"){
    try{
      const u=new URL(req.url,"https://feedback.invalid"),p=verifyFeedbackToken(u.searchParams.get("t"));
      if(!p)return res.status(400).send(feedbackPage(false,"De feedbacklink is ongeldig of beschadigd."));
      return res.status(200).send(feedbackPage(true,"Keuze: "+p.label+". Bevestig om deze voorkeur op te slaan.",u.searchParams.get("t")));
    }catch{return res.status(500).send(feedbackPage(false,"Opslaan is mislukt."))}
  }
  if(req.method!=="POST")return res.status(405).send("method not allowed");
  try{
    const raw=await rawBody(req);
    const ct=String(req.headers["content-type"]||"");
    if(ct.includes("application/x-www-form-urlencoded")){
      const form=new URLSearchParams(raw);
      if(form.get("action")==="custom_category"){
        const source=form.get("source"),job_id=form.get("job_id"),source_url=form.get("source_url")||"",custom_label=(form.get("custom_label")||"").trim();
        if(!source||!/^[A-Za-z0-9_-]{3,128}$/.test(job_id)||custom_label.length<2||custom_label.length>160)return res.status(400).send(feedbackPage(false,"Ongeldige nieuwe categorie."));
        const identity=source+"|"+job_id+"|"+custom_label.toLowerCase();
        const record={source,job_id:String(job_id),label:"custom_category",custom_label,received_at:new Date().toISOString(),message_id:"custom:"+crypto.createHash("sha256").update(identity).digest("hex"),source_url};
        const status=await persist(record);
        return res.status(200).send(feedbackPage(true,status==="duplicate"?"Deze categorie was al voorgesteld.":"Dank. De nieuwe categorie is opgeslagen als voorstel."));
      }
      const token=form.get("t"),p=verifyFeedbackToken(token);
      if(!p)return res.status(400).send(feedbackPage(false,"De feedbacklink is ongeldig of beschadigd."));
      const record={source:p.source,job_id:String(p.job_id),label:p.label,received_at:new Date().toISOString(),message_id:"link:"+crypto.createHash("sha256").update(token).digest("hex"),source_url:p.source_url||"",features:p.features||{}};
      const status=await persist(record);
      return res.status(200).send(feedbackPage(true,status==="duplicate"?"Deze feedback was al opgeslagen.":"Dank. Deze feedback wordt begrensd meegenomen in toekomstige matchscores."));
    }
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
