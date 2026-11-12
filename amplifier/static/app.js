"use strict";
let csrf = "", campaigns = [], assets = [];
const byId = id => document.getElementById(id);
function node(tag, content, css) {
  const n = document.createElement(tag);
  n.textContent = String(content);
  if (css) n.className = css;
  return n;
}
async function request(path, method="GET", payload) {
  const options = {method, credentials:"same-origin", headers:{}};
  if (payload !== undefined) {options.headers["Content-Type"]="application/json";options.body=JSON.stringify(payload);}
  if (method!=="GET") options.headers["X-CSRF-Token"]=csrf;
  const response = await fetch(path,options);
  const json = await response.json();
  if (!response.ok) throw Error(json.error || "Request failed");
  return json;
}
function alertUser(msg){const box=byId("message");box.textContent=msg;box.hidden=false;}
function render(){
  byId("campaignList").replaceChildren();
  byId("assetList").replaceChildren();
  byId("campaignSelect").replaceChildren();
  for (const c of campaigns) {
    const option=node("option",c.name);option.value=c.id;byId("campaignSelect").append(option);
    const row=node("div","","entry");
    row.append(node("strong",c.name),node("span",`${c.goal.toLocaleString()} ${c.target_metric} target`));
    byId("campaignList").append(row);
  }
  for (const a of assets) {
    const row=node("div","","entry"), left=node("div","","");
    left.append(node("strong",a.title),node("div",`${a.platform.toUpperCase()} · ${a.opens} outbound opens (not views)`,"muted"));
    const link=node("a","Open on platform ↗");
    link.href="/out/"+encodeURIComponent(a.id);link.target="_blank";link.rel="noopener noreferrer";
    row.append(left,link);byId("assetList").append(row);
  }
  if(!campaigns.length)byId("campaignList").append(node("p","Create a campaign to begin.","muted"));
  if(!assets.length)byId("assetList").append(node("p","Add content links from any supported platform.","muted"));
}
async function refresh(){
  const [c,a,s]=await Promise.all([request("/api/campaigns"),request("/api/assets"),request("/api/stats")]);
  campaigns=c.campaigns;assets=a.assets;
  byId("campaignCount").textContent=s.campaigns;byId("assetCount").textContent=s.assets;
  byId("openCount").textContent=s.outbound_opens;render();
}
function show(user){
  csrf=user.csrf;byId("login").hidden=true;byId("app").hidden=false;
  byId("user").textContent=user.email+" · "+user.role;
  const canEdit=["superadmin","admin","manager"].includes(user.role);
  byId("campaignForm").hidden=!canEdit;byId("assetForm").hidden=!canEdit;
  refresh().catch(e=>alertUser(e.message));
}
byId("signIn").addEventListener("submit",async e=>{
  e.preventDefault();const data=new FormData(e.currentTarget);
  try{show(await request("/api/login","POST",{email:data.get("email"),password:data.get("password")}));}
  catch(err){byId("error").textContent=err.message;}
});
byId("campaignForm").addEventListener("submit",async e=>{
  e.preventDefault();const data=new FormData(e.currentTarget);
  try{
    await request("/api/campaigns","POST",{name:data.get("name"),goal:Number(data.get("goal")),target_metric:data.get("target_metric")});
    e.currentTarget.reset();await refresh();alertUser("Campaign created.");
  }catch(err){alertUser(err.message);}
});
byId("assetForm").addEventListener("submit",async e=>{
  e.preventDefault();const data=new FormData(e.currentTarget);
  try{
    await request("/api/assets","POST",{campaign_id:data.get("campaign_id"),platform:data.get("platform"),title:data.get("title"),url:data.get("url")});
    e.currentTarget.reset();await refresh();alertUser("Asset registered.");
  }catch(err){alertUser(err.message);}
});
byId("logout").addEventListener("click",async ()=>{
  try{await request("/api/logout","POST",{});}finally{csrf="";byId("app").hidden=true;byId("login").hidden=false;}
});
request("/api/me").then(show).catch(()=>{byId("login").hidden=false;byId("app").hidden=true;});
