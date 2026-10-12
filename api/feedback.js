import crypto from "node:crypto";
const CHOICES={relevant:"Relevant",too_junior:"Te junior",wrong_location:"Verkeerde locatie",too_technical:"Te technisch",not_relevant:"Niet relevant"};

function verify(token){
 const secret=process.env.FEEDBACK_LINK_SECRET;
 if(!secret||Buffer.byteLength(secret)<32)throw Error("unconfigured");
 if(typeof token!=="string"||token.length>2750||token.split(".").length!==2)throw Error("token");
 const [body,sig]=token.split(".");
 const mac=crypto.createHmac("sha256",secret).update(body).digest();
 const supplied=Buffer.from(sig,"base64url");
 if(supplied.length!==mac.length||!crypto.timingSafeEqual(mac,supplied))throw Error("signature");
 const p=JSON.parse(Buffer.from(body,"base64url").toString("utf8"));
 if(!p||p.v!==1||!["Wise","Mollie"].includes(p.source)||!CHOICES[p.action]||
 !/^[a-zA-Z0-9-]{6,80}$/.test(p.job_id)||!/^[a-f0-9]{64}$/.test(p.recipient_digest)||
 !Number.isSafeInteger(p.exp)||Date.now()>p.exp*1000||p.exp*1000-Date.now()>15*86400000)throw Error("payload");
 return p;
}
const htmlEscape=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function save(p,token){
 const repo=process.env.GITHUB_REPOSITORY,branch=process.env.GITHUB_BRANCH||"vacancy-v4-clean-sheet";
 if(!repo||!process.env.GITHUB_TOKEN)throw Error("persistence unavailable");
 const path="vacancy-v4/data/feedback/v5-button-feedback.json";
 const url="https://api.github.com/repos/"+repo+"/contents/"+path;
 const headers={Authorization:"Bearer "+process.env.GITHUB_TOKEN,Accept:"application/vnd.github+json","Content-Type":"application/json"};
 const digest=crypto.createHash("sha256").update(token).digest("hex");
 const identity=p.source+"|"+p.job_id+"|"+p.recipient_digest;
 for(let i=0;i<4;i++){
  const response=await fetch(url+"?ref="+encodeURIComponent(branch),{headers});
  let rows=[],sha;
  if(response.status===200){const v=await response.json();sha=v.sha;rows=JSON.parse(Buffer.from(v.content,"base64").toString("utf8"))}
  else if(response.status!==404)throw Error("read failed "+response.status);
  if(!Array.isArray(rows))throw Error("invalid ledger");
  if(rows.some(r=>r.identity===identity))return "already-recorded";
  rows.push({identity,source:p.source,source_job_id:p.job_id,recipient_digest:p.recipient_digest,label:p.action,token_sha256:digest,confirmed_at:new Date().toISOString(),feedback_schema:"v5-button"});
  const payload={message:"v5: persist confirmed feedback",branch,content:Buffer.from(JSON.stringify(rows,null,2)+"\n").toString("base64"),...(sha?{sha}:{})};
  const put=await fetch(url,{method:"PUT",headers,body:JSON.stringify(payload)});
  if(put.ok)return "stored";
  if(put.status!==409&&put.status!==422)throw Error("write failed "+put.status);
 }
 throw Error("ledger contention");
}
export default async function handler(req,res){
 res.setHeader("Cache-Control","no-store");
 res.setHeader("X-Content-Type-Options","nosniff");
 if(!["GET","POST"].includes(req.method))return res.status(405).send("Method not allowed");
 let p,token;
 try{token=req.method==="GET"?req.query?.token:(typeof req.body==="string"?new URLSearchParams(req.body).get("token"):req.body?.token);p=verify(token)}
 catch{return res.status(400).send("Ongeldige of verlopen feedbacklink.");}
 if(req.method==="GET"){
  res.setHeader("Content-Type","text/html; charset=utf-8");
  return res.status(200).send('<!doctype html><html lang="nl"><meta charset="utf-8"><title>Bevestig feedback</title><body style="font:16px Arial;max-width:620px;margin:50px auto"><h1>Bevestig je feedback</h1><p>'+htmlEscape(p.source)+' · vacature '+htmlEscape(p.job_id)+'</p><p>Keuze: <strong>'+htmlEscape(CHOICES[p.action])+'</strong></p><form method="post"><input type="hidden" name="token" value="'+htmlEscape(token)+'"><button type="submit">Feedback bevestigen</button></form><p>Er wordt niets opgeslagen voordat je bevestigt.</p></body></html>');
 }
 try{
  // Vercel may parse application/x-www-form-urlencoded form submissions.
  if(typeof req.body==="string"){const parsed=new URLSearchParams(req.body);if(parsed.get("token")!==token) return res.status(400).send("Invalid form");}\n  if(!token)return res.status(400).send("Invalid form");
  const status=await save(p,token);
  return res.status(200).send(status==="stored"?"Feedback opgeslagen. Bedankt.":"Feedback was al opgeslagen.");
 }catch{return res.status(503).send("Opslaan mislukt; probeer later opnieuw.");}
}
