(() => {
  "use strict";
  const KEY = "tapas-growth-autopilot-v1";
  const $ = (q, root=document) => root.querySelector(q);
  const $$ = (q, root=document) => Array.from(root.querySelectorAll(q));
  const esc = v => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const clone = v => JSON.parse(JSON.stringify(v));
  const timeNow = () => new Date().toISOString();
  const niceDate = v => { try { return new Date(v).toLocaleString("en-IN",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}); } catch(e) { return String(v); } };
  const platforms = ["LinkedIn","YouTube","Instagram","X","Spotify","Bluesky","Mastodon","SoundCloud"];
  const seed = {
    version:1, activeView:"dashboard",
    campaigns:[
      {id:"GH-001",name:"Executive thought leadership",platform:"LinkedIn",url:"",goal:"1,000 impressions",status:"Draft — awaiting approval",createdAt:"2026-11-05T08:30:00.000Z",duration:60},
      {id:"GH-002",name:"November video discovery",platform:"YouTube",url:"",goal:"Audience discovery",status:"Planned",createdAt:"2026-11-04T09:30:00.000Z",duration:60}
    ],
    rules:[
      {id:1,keyword:"organizational transformation",platform:"LinkedIn",type:"New public posts",enabled:true},
      {id:2,keyword:"AI workforce readiness",platform:"YouTube",type:"Hashtag / topic",enabled:true},
      {id:3,keyword:"leadership development",platform:"Bluesky",type:"New public posts",enabled:false}
    ],
    schedules:[
      {id:1,title:"LinkedIn leadership insight",platform:"LinkedIn",cadence:"Weekly · Tuesday",next:"10 Nov 2026",status:"Planned",deliverable:"Original post"},
      {id:2,title:"YouTube Shorts repurpose",platform:"YouTube",cadence:"Twice weekly",next:"06 Nov 2026",status:"Planned",deliverable:"Short-form video"}
    ],
    comments:[], contacts:[], activities:[], tasks:[], monitor:null,
    metrics:{impressions:12840,views:4620,followers:386,listeners:920,conversions:24}
  };
  let state;

  const API_BASE = window.location.port === "8000" ? window.location.origin : (window.location.protocol + "//" + window.location.hostname + ":8000");
  let apiStatusData = null;
  async function apiCall(path, options) {
    options = options || {};
    const headers = Object.assign({"Content-Type":"application/json"}, options.headers || {});
    const response = await fetch(API_BASE + "/api" + path, Object.assign({}, options, {headers:headers}));
    const raw = await response.text();
    let data = {};
    try { data = raw ? JSON.parse(raw) : {}; } catch(e) { data = {detail:raw.slice(0,500)}; }
    if (!response.ok) throw new Error(data.detail || ("HTTP " + response.status));
    return data;
  }
  async function refreshBackendStatus() {
    try { apiStatusData = await apiCall("/status"); return apiStatusData; }
    catch(e) { apiStatusData = null; return null; }
  }
  const providerIds = {"LinkedIn":"linkedin","YouTube":"youtube","Instagram":"instagram","X":"x","Spotify":"spotify","Bluesky":"bluesky","Mastodon":"mastodon","SoundCloud":"soundcloud"};
  function liveProviderState(name) {
    const p = apiStatusData && apiStatusData.providers ? apiStatusData.providers[providerIds[name]] : null;
    if (!p) return {label:"Backend unavailable",kind:"warn",connected:false,configured:false,detail:"Start the FastAPI backend."};
    if (p.status === "connected") return {label:"Connected",kind:"ok",connected:true,configured:true,detail:p.account_name || "Authorized account"};
    if (p.status === "available") return {label:"Public reads available",kind:"info",connected:false,configured:true,detail:"No account login required for public discovery"};
    if (p.configured) return {label:"Ready to connect",kind:"info",connected:false,configured:true,detail:"Provider app credentials are configured"};
    return {label:"App credentials required",kind:"warn",connected:false,configured:false,detail:"Configure the provider app in backend .env"};
  }
  async function syncProvider(name) {
    const id = providerIds[name];
    toast("Requesting live " + name + " data…");
    try {
      const result = await apiCall("/analytics/sync/" + id,{method:"POST"});
      await loadLiveSnapshots();
      toast(name + " data synchronized.");
      render("analytics");
      return result;
    } catch(e) { toast(name + ": " + e.message); return null; }
  }
  let liveSnapshots = [];
  async function loadLiveSnapshots() {
    try { const d=await apiCall("/analytics/snapshots"); liveSnapshots=d.snapshots || []; return liveSnapshots; }
    catch(e) { liveSnapshots=[]; return []; }
  }
  async function refreshServerModules() {
    await Promise.all([
      refreshBackendStatus(),
      apiCall("/discovery/rules").then(d=>{state.rules=(d.rules||[]).map(r=>({id:r.id,keyword:r.keyword,platform:r.platform,type:r.rule_type,enabled:!!r.enabled}));save();}).catch(()=>{}),
      apiCall("/schedules").then(d=>{if(d.schedules){state.schedules=d.schedules.map(r=>({id:r.id,title:r.title,platform:r.platform,cadence:r.cadence,next:new Date(r.next_run_at).toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"}),deliverable:r.deliverable,status:r.status,approved:!!r.approved}));save();}}).catch(()=>{}),
      apiCall("/tasks?limit=100").then(d=>{state.tasks=d.tasks||[];save();}).catch(()=>{}),
      loadLiveSnapshots()
    ]);
  }
  function showProviderSetup(name, readiness) {
    const envNames={LinkedIn:"LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET",YouTube:"GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET",Instagram:"META_APP_ID, META_APP_SECRET",X:"X_CLIENT_ID (and optional X_CLIENT_SECRET)",Spotify:"SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET",Mastodon:"No developer key required; instance app registration is created on connection",SoundCloud:"SOUNDCLOUD_CLIENT_ID, SOUNDCLOUD_CLIENT_SECRET"};
    const slug=providerIds[name];
    const redirect=API_BASE+"/api/oauth/"+slug+"/callback";
    showModal(name+" connection requirements",'<p>'+esc(readiness&&readiness.capability||"Configure the official provider developer app.")+'</p><p><b>Backend variables:</b><br>'+esc(envNames[name]||"Provider-specific configuration")+'</p><p><b>OAuth callback URL:</b><br><code>'+esc(name==="Mastodon"?API_BASE+"/api/oauth/mastodon/callback":redirect)+'</code></p><p>Set these values in <code>growth-autopilot/.env</code>, restart the backend, then select Connect account. Never paste client secrets into this page or chat.</p>');
  }
  try { state = JSON.parse(localStorage.getItem(KEY)) || clone(seed); } catch(e) { state = clone(seed); }
  function save(){ localStorage.setItem(KEY,JSON.stringify(state)); }
  function log(title,detail){ state.activities.unshift({title:title,detail:detail,time:new Date().toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"})}); state.activities=state.activities.slice(0,12); }
  function toast(msg){ const t=$("#toast"); t.textContent=msg; t.classList.add("show"); window.setTimeout(()=>t.classList.remove("show"),2600); }
  function status(txt,kind){ return '<span class="status '+(kind||"")+'">'+esc(txt)+'</span>'; }
  function pageHead(k,t,d,a){ return '<div class="head"><div><div class="eyebrow">'+esc(k)+'</div><h1>'+esc(t)+'</h1><p>'+d+'</p></div><div class="actions">'+(a||"")+'</div></div>'; }
  function kpi(label,value,foot,orb){ return '<div class="card kpi" style="--orb:'+orb+'"><label>'+label+'</label><strong>'+value+'</strong><small>'+foot+'</small></div>'; }
  function activityList(){ if(!state.activities.length) return '<div class="empty">No workspace activity yet. Create a local plan to begin.</div>'; return state.activities.slice(0,5).map(a=>'<div class="activity"><i></i><div><b>'+esc(a.title)+'</b><small>'+esc(a.detail)+'</small></div><span class="right">'+esc(a.time)+'</span></div>').join(""); }
  function platformBars(){ const data=[["LinkedIn",76],["YouTube",61],["Instagram",53],["Spotify",42],["Bluesky",29]]; return data.map(x=>'<div class="bar-row"><label>'+x[0]+'</label><div class="track"><span style="width:'+x[1]+'%"></span></div><b>'+x[1]+'%</b></div>').join(""); }
  function dashboard(){
    const m=state.metrics, active=state.monitor && state.monitor.status==="Monitoring locally (demo)";
    const duration=active?(state.monitor.duration||60):60;
    const elapsed=active ? Math.min(duration,Math.floor((Date.now()-state.monitor.startedAt)/60000)) : 0;
    const pct=active?Math.round(elapsed/duration*100):0;
    let h=pageHead("TAPAS ADVISORY / GROWTH OS","Growth command centre","One workspace for first-hour campaigns, content intelligence and recurring growth programmes. All figures shown are illustrative demo data.",'<button class="btn ghost" data-action="export">⇩ Export data</button><button class="btn primary" data-go="golden">＋ New Golden Hour</button>');
    h+='<div class="grid kpis">'+kpi("Tracked impressions","12,840","Illustrative demo period",'#edf0ff')+kpi("Video views","4,620","Illustrative sample",'#e9fafa')+kpi("Audience growth","+386","Across demo records",'#f0ebff')+kpi("Conversions","24","Illustrative sample",'#fff4e8')+'</div>';
    h+='<div class="grid split"><section class="card"><div class="hero"><div class="hero-top"><h2>Golden Hour monitor</h2><span>'+(active?"DEMO MONITOR RUNNING":"READY TO PLAN")+'</span></div><div class="hero-number">'+(active?(duration-elapsed)+'m remaining':"60-minute window")+'</div><div class="hero-sub">'+(active?"Local timer only · no platform actions are sent":"Set a first-hour target and prepare your campaign")+'</div><div class="progress"><span style="width:'+pct+'%"></span></div><div class="hero-foot"><span>'+(active?elapsed+" minutes elapsed":"Campaign orchestration")+'</span><span>'+(active?pct+"%":"Target: 1,000 impressions")+'</span></div></div><div class="mini"><div><label>Campaigns</label><b>'+state.campaigns.length+'</b></div><div><label>Watch rules</label><b>'+state.rules.filter(x=>x.enabled).length+' active</b></div><div><label>Schedules</label><b>'+state.schedules.length+'</b></div></div></section>';
    h+='<section class="card"><div class="card-head"><div><h2>Recent workspace activity</h2><p>Local workflow history</p></div><span class="tag">LATEST</span></div><div class="card-body">'+activityList()+'</div></section></div>';
    h+='<div class="grid split"><section class="card"><div class="card-head"><div><h2>Platform momentum</h2><p>Relative activity index · illustrative demo</p></div>'+status("Sample data","warn")+'</div><div class="card-body">'+platformBars()+'<p class="metric-note">Indices are illustrative and are not connected to social platform analytics.</p></div></section>';
    h+='<section class="card"><div class="card-head"><div><h2>Quick launch</h2><p>Start with a focused growth workflow</p></div></div><div class="card-body">'+activityButton("Prepare a Golden Hour","60-minute campaign plan","golden")+activityButton("Draft thoughtful comments","Context-aware writing assistant","comments")+activityButton("Create a recurring programme","Weekly and monthly cadence","drip")+'</div></section></div>';
    h+='<h2 class="section-title">Growth Autopilot modules</h2><div class="grid quick">'+quick("◷","Golden Hour","Plan a 60-minute distribution and measurement window.","golden")+quick("✳","Smart Comments","Prepare thoughtful, relevant comment and reply drafts.","comments")+quick("◎","Community Intelligence","Organize relevant communities and opted-in advocates.","community")+quick("⌕","Auto-Discovery","Define watchlists and review matching content sources.","discovery")+quick("↻","Drip Growth","Plan repeatable content and distribution programmes.","drip")+quick("▥","Growth Analytics","Review tracked outcomes and export campaign records.","analytics")+'</div>';
    return h;
  }
  function activityButton(title,sub,view){return '<div class="activity"><i></i><div><b>'+title+'</b><small>'+sub+'</small></div><button class="btn soft" data-go="'+view+'">Open</button></div>';}
  function quick(icon,title,desc,view){return '<button data-go="'+view+'"><i>'+icon+'</i><b>'+title+'</b><small>'+desc+'</small></button>';}
  function golden(){
    const active=state.monitor && state.monitor.status==="Monitoring locally (demo)";
    const duration=active?(state.monitor.duration||60):60;
    const elapsed=active?Math.min(duration,Math.floor((Date.now()-state.monitor.startedAt)/60000)):0;
    let rows=state.campaigns.map(c=>'<tr><td><b>'+esc(c.name)+'</b><br><span class="metric-note">'+esc(c.id)+'</span></td><td>'+esc(c.platform)+'</td><td>'+esc(c.goal)+'</td><td>'+status(c.status,c.status.indexOf("Draft")>=0?"warn":c.status.indexOf("Monitoring")>=0?"info":"")+'</td><td>'+niceDate(c.createdAt)+'</td><td>'+(c.status==="Draft — awaiting approval"?'<button class="btn soft" data-action="start-monitor" data-id="'+esc(c.id)+'">Start demo timer</button>':'—')+'</td></tr>').join("");
    let h=pageHead("CAMPAIGN ORCHESTRATION","Golden Hour","Plan the first 60 minutes around a clear objective. The local demo timer does not publish, boost, message or create engagement on any platform.",'<button class="btn ghost" data-go="analytics">View analytics</button>');
    h+='<div class="grid split"><section class="card"><div class="card-head"><div><h2>Build a 60-minute campaign</h2><p>Choose the content, target and monitoring window</p></div>'+status("Approval workflow","info")+'</div><div class="card-body"><form id="goldenForm"><div class="form-grid"><div class="field"><label>Campaign name</label><input id="gName" required maxlength="90" placeholder="e.g. Leadership insight launch"></div><div class="field"><label>Platform</label><select id="gPlatform">'+options(platforms)+'</select></div><div class="field full"><label>Post / content URL (optional for planning)</label><input id="gUrl" type="url" placeholder="https://..."><span class="hint">A public URL is a reference only. No account access is performed.</span></div><div class="field"><label>Primary outcome</label><select id="gGoal">'+options(["1,000 impressions","1,000 video views","Qualified profile visits","Listener discovery","Community conversations","Lead conversions"])+'</select></div><div class="field"><label>Monitoring window</label><select id="gDuration">'+options(["60","30","90"])+'</select></div></div><div class="note"><b>What this MVP does</b><br>It saves a campaign plan and runs a local timer. Live distribution and analytics require an authorized platform connector and verified account permissions.</div><div class="form-actions"><span class="hint">Status on save: Draft — awaiting approval</span><button class="btn primary">Save campaign plan →</button></div></form></div></section>';
    h+='<section class="card"><div class="card-head"><div><h2>Campaign monitor</h2><p>Current local session</p></div>'+status(active?"Monitoring locally":"Idle",active?"info":"")+'</div><div class="card-body">';
    if(active){h+='<div class="hero"><div class="hero-top"><h2>'+esc(state.monitor.name)+'</h2><span>DEMO TIMER</span></div><div class="hero-number" id="remaining">'+Math.max(0,duration-elapsed)+'m</div><div class="hero-sub">'+esc(state.monitor.platform)+' · '+esc(state.monitor.goal)+'</div><div class="progress"><span style="width:'+Math.round(elapsed/duration*100)+'%"></span></div><div class="hero-foot"><span>'+elapsed+' minutes elapsed</span><span>'+duration+'-minute plan</span></div></div><p class="metric-note">This timer measures elapsed time only. No impression or view count is generated.</p><button class="btn danger" data-action="stop-monitor">Stop local timer</button>';}
    else{h+='<div class="empty"><div style="font-size:27px">◷</div><b>No active monitoring session</b><p>Create a campaign plan to begin.</p></div>';}
    h+='</div></section></div><section class="card" style="margin-top:14px"><div class="card-head"><div><h2>Campaign register</h2><p>Saved plans and workflow status</p></div><span class="tag">'+state.campaigns.length+' RECORDS</span></div><div class="table-wrap"><table><thead><tr><th>Campaign</th><th>Platform</th><th>Goal</th><th>Status</th><th>Created</th><th>Action</th></tr></thead><tbody>'+(rows||'<tr><td colspan="6" class="empty">No campaigns yet.</td></tr>')+'</tbody></table></div></section>';
    return h;
  }
  function options(arr){return arr.map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join("");}
  function comments(){
    let cards=state.comments.map((c,i)=>'<article class="comment"><div class="comment-top"><b>Draft '+(i+1)+' · '+esc(c.tone)+'</b>'+status(c.status,c.status==="Approved for manual use"?"ok":"warn")+'</div><p>'+esc(c.text)+'</p><div class="row-buttons"><button class="btn ghost" data-action="copy-comment" data-id="'+c.id+'">Copy text</button>'+(c.status==="Approved for manual use"?'<button class="btn soft" disabled>Approved for manual use</button>':'<button class="btn soft" data-action="approve-comment" data-id="'+c.id+'">Approve draft</button>')+'</div></article>').join("");
    let h=pageHead("CONTENT ASSISTANCE","Smart Comments","Generate context-aware comment and reply drafts for review. Draft approval means approval to copy and use manually—not permission to auto-post.",'<button class="btn ghost" data-action="clear-comments">Clear drafts</button>');
    h+='<div class="grid split"><section class="card"><div class="card-head"><div><h2>Comment drafting studio</h2><p>Give the assistant the actual conversation context</p></div>'+status("Draft only","warn")+'</div><div class="card-body"><form id="commentForm"><div class="field"><label>Post text or conversation context</label><textarea id="sourcePost" required placeholder="Paste the post text or the comment you want to respond to..."></textarea></div><div class="form-grid" style="margin-top:12px"><div class="field"><label>Tone</label><select id="cTone">'+options(["Insightful and professional","Constructive and curious","Supportive and concise","Evidence-led and analytical"])+'</select></div><div class="field"><label>Drafts to generate</label><select id="cCount">'+options(["3","5"])+'</select></div></div><div class="field" style="margin-top:12px"><label>Your point of view (optional)</label><input id="cPoint" placeholder="Add a perspective, example or question"></div><div class="note"><b>Gemini drafting</b><br>Comment generation calls the private backend Gemini API when GEMINI_API_KEY is configured. Drafts are saved for human review; this module does not publish comments.</div><div class="form-actions"><span class="hint">Approved items publish automatically — nothing publishes without approval.</span><button class="btn primary">Generate comment drafts →</button></div></form></div></section>';
    h+='<section class="card"><div class="card-head"><div><h2>Writing principles</h2><p>Quality controls for TAPAS voice</p></div></div><div class="card-body">'+activityItem("Add a relevant insight","Contribute a useful idea, not generic praise.")+activityItem("Stay context-specific","Reflect the actual subject and point raised.")+activityItem("Keep the human voice","Avoid repetitive or promotional replies.")+activityItem("Verify factual claims","Do not invent studies, statistics or experience.")+'</div></section></div>';
    h+='<section class="card" style="margin-top:14px"><div class="card-head"><div><h2>Draft library</h2><p>Approved drafts remain manual-use assets</p></div><span class="tag">'+state.comments.length+' DRAFTS</span></div><div class="card-body">'+(cards||'<div class="empty">No drafts yet. Paste post context to generate the first set.</div>')+'</div></section>';
    return h;
  }
  function activityItem(title,desc){return '<div class="activity"><i></i><div><b>'+title+'</b><small>'+desc+'</small></div></div>';}
  function community(){
    let contacts=state.contacts.map(c=>'<tr><td><b>'+esc(c.name)+'</b><br><span class="metric-note">'+esc(c.url||"No public URL supplied")+'</span></td><td>'+esc(c.platform)+'</td><td>'+esc(c.topic)+'</td><td>'+status(c.permission,c.permission==="Opted in"?"ok":"warn")+'</td></tr>').join("");
    let h=pageHead("AUDIENCE DEVELOPMENT","Community Intelligence","Organize relevant communities, advocates and creator relationships from public information and voluntary submissions. No profile scraping or automatic invitations.",'<button class="btn primary" data-action="add-contact">＋ Add contact</button>');
    h+='<div class="grid community-grid">'+communityCard("◎","People & Organization Leaders","HR, OD, talent, culture and organizational effectiveness practitioners.","LinkedIn · professional community")+communityCard("↗","Change & Transformation","Change leaders, transformation executives and enterprise adoption voices.","Cross-platform discovery")+communityCard("✳","AI & Future of Work","Responsible AI, workforce strategy and digital transformation discussions.","Bluesky · Mastodon · LinkedIn")+'</div>';
    h+='<div class="grid split" style="margin-top:14px"><section class="card"><div class="card-head"><div><h2>Relationship register</h2><p>People added by the workspace owner</p></div><span class="tag">'+state.contacts.length+' CONTACTS</span></div><div class="table-wrap"><table><thead><tr><th>Contact</th><th>Platform</th><th>Topic</th><th>Permission</th></tr></thead><tbody>'+(contacts||'<tr><td colspan="4" class="empty">No contacts recorded. Add a public creator or an opted-in advocate.</td></tr>')+'</tbody></table></div></section>';
    h+='<section class="card"><div class="card-head"><div><h2>Community principles</h2><p>Trust-led audience development</p></div></div><div class="card-body">'+activityItem("Relevance before volume","Prioritize subject-matter fit and audience overlap.")+activityItem("Permission is recorded","Track opt-in before adding advocates to owned programmes.")+activityItem("No engagement exchange","Contacts choose independently whether to participate.")+'</div></section></div>';
    return h;
  }
  function communityCard(g,n,d,meta){return '<article class="card community"><div class="glyph">'+g+'</div><h3>'+n+'</h3><p>'+d+'</p><span class="metric-note">'+meta+'</span></article>';}
  function discovery(){
    let rules=state.rules.map(r=>'<div class="watch"><div><b>'+esc(r.keyword)+'</b><small>'+esc(r.platform)+' · '+(r.enabled?"Enabled in background worker":"Paused")+'</small></div><button class="switch '+(r.enabled?"on":"")+'" data-action="toggle-rule" data-id="'+r.id+'" aria-label="Toggle rule"></button><button class="btn ghost" data-action="delete-rule" data-id="'+r.id+'">Remove</button></div>').join("");
    let h=pageHead("CONTENT LISTENING","Auto-Discovery","Define topics and platforms to monitor. The local backend scans supported public/authenticated sources every 15 minutes while it is running; platform reach varies by API permission and tier.",'<button class="btn ghost" data-action="sample-scan">Run live scan now</button>');
    h+='<div class="grid split"><section class="card"><div class="card-head"><div><h2>Create a watch rule</h2><p>Monitor topics relevant to TAPAS positioning</p></div></div><div class="card-body"><form id="watchForm"><div class="form-grid"><div class="field full"><label>Keyword or topic</label><input id="watchKeyword" required placeholder="e.g. AI workforce transformation"></div><div class="field"><label>Platform</label><select id="watchPlatform">'+options(platforms)+'</select></div><div class="field"><label>Watch type</label><select id="watchType">'+options(["New public posts","Hashtag / topic","Creator publication","Competitor / brand mention"])+'</select></div></div><div class="form-actions"><span class="hint">No account access required to save a rule.</span><button class="btn primary">Save watch rule →</button></div></form></div></section>';
    h+='<section class="card"><div class="card-head"><div><h2>Watchlist status</h2><p>Backend rules and scheduled scan</p></div>'+status("Server-backed","info")+'</div><div class="card-body"><div style="font:800 29px Manrope">'+state.rules.filter(x=>x.enabled).length+' / '+state.rules.length+'</div><p class="metric-note">Active rules / total rules. Scan interval is controlled by DISCOVERY_INTERVAL_MINUTES in backend .env.</p><div class="note"><b>Connector required for live discovery</b><br>Use only authorized search or streaming endpoints after account access and permissions are verified.</div></div></section></div>';
    h+='<section class="card" style="margin-top:14px"><div class="card-head"><div><h2>Configured watch rules</h2><p>Enable, pause or remove topics</p></div></div><div class="card-body">'+(rules||'<div class="empty">No watch rules configured.</div>')+'</div></section>';
    h+='<section class="card" style="margin-top:14px"><div class="card-head"><div><h2>Live discovery feed</h2><p>Items returned by authorized provider APIs</p></div>'+status("Demo examples","warn")+'</div><div class="card-body" id="sampleFeed"><div class="empty">Run a live scan to retrieve posts from connected sources. Bluesky public discovery does not require sign-in.</div></div></section>';
    return h;
  }
  function drip(){
    let rows=state.schedules.map(s=>'<div class="schedule"><time>'+esc(s.next)+'</time><div><b>'+esc(s.title)+'</b><small>'+esc(s.platform)+' · '+esc(s.cadence)+' · '+esc(s.deliverable||"Content")+'</small></div><div>'+status(s.status,s.status==="Active"?"ok":s.status==="Pending approval"?"warn":"")+' <button class="btn ghost" data-action="toggle-schedule" data-id="'+s.id+'">'+(s.status==="Active"?"Pause":s.status==="Paused"?"Activate":"Approve & activate")+'</button></div></div>').join("");
    const taskRows=(state.tasks||[]).filter(t=>t.task_type==="scheduled_campaign").map(t=>{
      let info={};try{info=JSON.parse(t.detail||"{}");}catch(e){}
      return '<div class="activity"><i></i><div><b>'+esc(info.title||"Scheduled content task")+'</b><small>'+esc(t.platform||"")+' · '+esc(info.deliverable||"")+' · '+esc(info.note||"Ready for review")+'</small></div><span class="right">'+esc(t.status)+" · "+esc(t.created_at)+'</span></div>';
    }).join("");
    let h=pageHead("RECURRING PROGRAMMES","Drip Growth","Build recurring content programmes. The backend checks due schedules every minute and creates durable review tasks; publishing requires a separate authorized route and approval.",'<button class="btn ghost" data-action="refresh-tasks">↻ Refresh tasks</button>');
    h+='<div class="grid split"><section class="card"><div class="card-head"><div><h2>Create a recurring programme</h2><p>Define the deliverable and cadence</p></div></div><div class="card-body"><form id="dripForm"><div class="form-grid"><div class="field full"><label>Programme name</label><input id="dTitle" required placeholder="e.g. Weekly executive insight"></div><div class="field"><label>Platform</label><select id="dPlatform">'+options(platforms)+'</select></div><div class="field"><label>Cadence</label><select id="dCadence">'+options(["Daily","Twice weekly","Weekly","Fortnightly","Monthly"])+'</select></div><div class="field"><label>Next planned date</label><input id="dDate" type="date" required value="2026-11-06"></div><div class="field"><label>Deliverable</label><select id="dDeliverable">'+options(["Original post","Short-form video","Repurposed content","Community conversation plan","SEO / AEO content update"])+'</select></div></div><div class="form-actions"><span class="hint">New items begin as Pending approval.</span><button class="btn primary">Save programme →</button></div></form></div></section>';
    h+='<section class="card"><div class="card-head"><div><h2>Operating cadence</h2><p>Background worker status</p></div>'+status("Minute-level scheduler","info")+'</div><div class="card-body">'+activityItem("Plan","Set topics and objectives for the month.")+activityItem("Prepare","Draft and approve content before the slot.")+activityItem("Review","Due programmes generate a review task.")+activityItem("Distribute","A separate authorized publishing action is required.")+'</div></section></div>';
    h+='<section class="card" style="margin-top:14px"><div class="card-head"><div><h2>Programme calendar</h2><p>Server-backed recurring schedule register</p></div><span class="tag">'+state.schedules.length+' PROGRAMMES</span></div><div class="card-body">'+(rows||'<div class="empty">No recurring programmes yet.</div>')+'</div></section>';
    h+='<section class="card" style="margin-top:14px"><div class="card-head"><div><h2>Due-task review queue</h2><p>Tasks created when scheduled runs become due. Approved items publish automatically — nothing publishes without approval.</p></div><span class="tag">'+(state.tasks||[]).length+' TASKS</span></div><div class="card-body">'+(taskRows||'<div class="empty">No scheduled tasks are due. The worker checks each minute while the backend is running.</div>')+'</div></section>';
    return h;
  }
  function chartSvg(){return '<svg class="chart" viewBox="0 0 700 170" preserveAspectRatio="none" aria-label="Illustrative seven-day impressions trend"><defs><linearGradient id="fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#5a72f5" stop-opacity=".22"/><stop offset="1" stop-color="#5a72f5" stop-opacity="0"/></linearGradient></defs>'+[25,65,105,145].map(y=>'<line x1="30" y1="'+y+'" x2="685" y2="'+y+'" stroke="#eef1f7"/>').join("")+'<path d="M30 125 L135 112 L240 118 L345 81 L450 91 L555 49 L685 30 L685 150 L30 150 Z" fill="url(#fill)"/><path d="M30 125 L135 112 L240 118 L345 81 L450 91 L555 49 L685 30" fill="none" stroke="#526dff" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'+[[30,125],[135,112],[240,118],[345,81],[450,91],[555,49],[685,30]].map(p=>'<circle cx="'+p[0]+'" cy="'+p[1]+'" r="4" fill="#fff" stroke="#526dff" stroke-width="2"/>').join("")+["30 Oct","31 Oct","01 Nov","02 Nov","03 Nov","04 Nov","05 Nov"].map((x,i)=>'<text x="'+(30+i*109)+'" y="166" text-anchor="middle" font-size="9" fill="#98a2b5">'+x+'</text>').join("")+'</svg>';}
  function analytics(){
    let m=state.metrics;
    let h=pageHead("MEASUREMENT & INSIGHT","Growth Analytics","Unify outcome definitions and campaign history. The sample values are not connected to YouTube, Spotify, LinkedIn or other platform accounts.",'<button class="btn ghost" data-action="export-csv">⇩ Export CSV</button>');
    h+='<div class="grid kpis">'+kpi("Impressions",m.impressions.toLocaleString("en-IN"),"Illustrative sample","#edf0ff")+kpi("Video views",m.views.toLocaleString("en-IN"),"Illustrative sample","#e9fafa")+kpi("Audience growth","+"+m.followers,"Illustrative sample","#f0ebff")+kpi("Conversions",m.conversions,"Illustrative sample","#fff4e8")+'</div>';
    h+='<div class="grid split"><section class="card"><div class="card-head"><div><h2>Impression trend</h2><p>Last seven days · demo series</p></div>'+status("Illustrative","warn")+'</div><div class="card-body">'+chartSvg()+'</div></section><section class="card"><div class="card-head"><div><h2>Audience outcome mix</h2><p>Source-defined metrics</p></div></div><div class="card-body">'+metricBar("Video views",m.views,80)+metricBar("Spotify listeners",m.listeners,56)+metricBar("Conversions",m.conversions,28)+'<p class="metric-note">Bars are normalized illustrative values, not cross-platform comparators.</p></div></section></div>';
    h+='<section class="card" style="margin-top:14px"><div class="card-head"><div><h2>Metric dictionary</h2><p>Keep source definitions visible when comparing platforms</p></div></div><div class="table-wrap"><table><thead><tr><th>Metric</th><th>Sample value</th><th>Definition / source treatment</th></tr></thead><tbody><tr><td>Impressions</td><td>'+m.impressions.toLocaleString("en-IN")+'</td><td>Display count</td></tr><tr><td>Video views</td><td>'+m.views.toLocaleString("en-IN")+'</td><td>Plays; source-defined metric</td></tr><tr><td>Audience growth</td><td>'+m.followers.toLocaleString("en-IN")+'</td><td>Follower / subscriber adds</td></tr><tr><td>Spotify listeners</td><td>'+m.listeners.toLocaleString("en-IN")+'</td><td>Monthly listener snapshot</td></tr><tr><td>Conversions</td><td>'+m.conversions+'</td><td>Demo conversion events</td></tr></tbody></table></div></section>';
    h+='<section class="card" style="margin-top:14px"><div class="card-head"><div><h2>Live provider snapshots</h2><p>Latest records returned by authorized APIs</p></div><button class="btn ghost" data-action="refresh-snapshots">↻ Refresh</button></div><div class="card-body">'+(liveSnapshots.length?liveSnapshots.slice(0,20).map(x=>'<div class="activity"><i></i><div><b>'+esc(x.provider.toUpperCase())+'</b><small>'+esc(x.provenance)+' · '+esc(JSON.stringify(x.metrics).slice(0,300))+'</small></div><span class="right">'+esc(x.collected_at)+'</span></div>').join(""):'<div class="empty">No live analytics snapshots yet. Connect a platform and select Sync data.</div>')+'</div></section>';
    h+='<div class="note"><b>Data provenance</b><br>Only records returned by connected APIs appear in Live provider snapshots. Headline sample figures remain illustrative. Spotify for Artists metrics are not implied by Spotify listener-account data.</div>';
    return h;
  }
  function metricBar(n,v,w){return '<div class="bar-row" style="grid-template-columns:105px 1fr 48px"><label>'+n+'</label><div class="track"><span style="width:'+w+'%"></span></div><b>'+Number(v).toLocaleString("en-IN")+'</b></div>';}
  const integrations=[
    ["LinkedIn","in","Official API / authorized provider","OAuth and applicable product permissions required."],
    ["YouTube","▶","YouTube Data & Analytics APIs","Google account authorization; API quota and scopes apply."],
    ["Instagram","◎","Meta Graph API","Eligible professional account and Meta app permissions required."],
    ["X","𝕏","X API / permitted export","API access and rate limits depend on the selected tier."],
    ["Spotify","♫","Spotify for Artists / Web API","Artist analytics access is distinct from public Spotify metadata."],
    ["Bluesky","✳","AT Protocol","Public discovery and authorized account sessions."],
    ["Mastodon","m","Mastodon API","Instance-specific API access and rate limits."],
    ["SoundCloud","☁","Authorized account / API route","Confirm current app registration and granted scopes."]
  ];
  function connections(){
    let cards=integrations.map(x=>{
      const st=liveProviderState(x[0]);
      const actions=st.connected
        ? '<button class="btn soft" data-action="sync-provider" data-name="'+x[0]+'">Sync data</button><button class="btn ghost" data-action="disconnect-provider" data-name="'+x[0]+'">Disconnect</button>'
        : '<button class="btn primary" data-action="connect-provider" data-name="'+x[0]+'">'+(x[0]==="Bluesky"?"Open discovery":st.configured?"Connect account":"Setup requirements")+'</button>';
      return '<article class="card integration"><div class="integration-head"><span class="integration-icon">'+x[1]+'</span><div><b>'+x[0]+'</b><br>'+status(st.label,st.kind)+'</div></div><p>'+esc(st.detail)+'. '+x[3]+'</p><div class="integration-foot"><span class="metric-note">'+x[2]+'</span><div class="row-buttons">'+actions+'</div></div></article>';
    }).join("");
    const gem=apiStatusData && apiStatusData.gemini;
    const gemText=gem ? (gem.configured?"Gemini API ready · "+gem.model:"Gemini API key required") : "Backend not reachable";
    return pageHead("INTEGRATION CONTROL","Platform connections","Connect accounts through each provider's official consent screen. Credentials and tokens stay on the backend; the browser never receives provider secrets.",'<button class="btn ghost" data-action="refresh-connections">↻ Refresh status</button>')+
      '<section class="card" style="padding:13px 16px;margin-bottom:14px"><b>Gemini drafting service</b><p class="metric-note">'+esc(gemText)+' · Configure GEMINI_API_KEY in the backend .env. A Google AI Pro login is not an API key.</p></section>'+
      '<div class="grid integration-grid">'+cards+'</div><div class="note"><b>Connection status is live</b><br>OAuth callback URLs must be registered in each provider developer console. Bluesky public discovery does not require account authentication. Spotify for Artists and LinkedIn restricted analytics require separate account/product eligibility.</div>';
  }
  function settings(){
    let h=pageHead("WORKSPACE CONFIGURATION","Workspace settings","Private local prototype controls. Campaign plans and drafts are stored in this browser local storage.",'<button class="btn ghost" data-action="export">⇩ Backup data</button>');
    h+='<div class="grid split"><section class="card"><div class="card-head"><div><h2>Workspace information</h2><p>Current runtime configuration</p></div></div><div class="card-body">'+activityItem("Workspace","TAPAS Advisory · Private")+activityItem("Environment","Browser-local prototype · Demo mode")+activityItem("Storage","Browser localStorage · Local only")+activityItem("AI provider","No live model configured")+activityItem("Social connectors","No platform authorized")+'</div></section><section class="card"><div class="card-head"><div><h2>Data controls</h2><p>Backup, restore or reset local prototype</p></div></div><div class="card-body"><div class="activity"><div><b>Export workspace JSON</b><small>Download campaigns, watchlists and drafts</small></div><button class="btn ghost" data-action="export">Export</button></div><div class="activity"><div><b>Import workspace JSON</b><small>Restore a prior local backup</small></div><label class="btn ghost" for="importFile">Choose file</label><input id="importFile" type="file" accept="application/json" hidden></div><div class="activity"><div><b>Reset to sample data</b><small>Replace local records with demo examples</small></div><button class="btn danger" data-action="reset">Reset</button></div></div></section></div>';
    h+='<section class="card" style="margin-top:14px"><div class="card-head"><div><h2>Production readiness gaps</h2><p>Required before real platform operations</p></div></div><div class="card-body">'+activityItem("Add private workspace authentication and a protected backend.","")+activityItem("Implement official OAuth / approved provider connections.","")+activityItem("Connect genuine analytics and metric provenance.","")+activityItem("Add a Gemini model adapter for AI drafting.","")+activityItem("Add authorized discovery and a durable scheduling queue.","")+activityItem("Add audit events, retries, approvals and end-to-end tests.","")+'</div></section>';
    return h;
  }
  const renderers={dashboard:dashboard,golden:golden,comments:comments,community:community,discovery:discovery,drip:drip,analytics:analytics,connections:connections,settings:settings};
  const titles={dashboard:"Command centre",golden:"Golden Hour",comments:"Smart Comments",community:"Community Intelligence",discovery:"Auto-Discovery",drip:"Drip Growth",analytics:"Growth Analytics",connections:"Platform connections",settings:"Workspace settings"};
  function render(view){
    state.activeView=view||"dashboard";save();
    $$(".nav-item").forEach(b=>b.classList.toggle("active",b.dataset.view===state.activeView));
    $("#crumb").textContent=titles[state.activeView]||"Workspace";
    $("#content").innerHTML=(renderers[state.activeView]||dashboard)();
    window.scrollTo(0,0);
  }
  function exportData(){const blob=new Blob([JSON.stringify(state,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="tapas-growth-autopilot-backup.json";a.click();URL.revokeObjectURL(url);toast("Workspace backup exported.");}
  function exportCsv(){const rows=[["Campaign ID","Name","Platform","Goal","Status","Created"]].concat(state.campaigns.map(c=>[c.id,c.name,c.platform,c.goal,c.status,c.createdAt]));const csv=rows.map(r=>r.map(x=>'"'+String(x||"").replace(/"/g,'""')+'"').join(",")).join("\n");const blob=new Blob([csv],{type:"text/csv"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="tapas-campaign-register.csv";a.click();URL.revokeObjectURL(url);toast("Campaign register exported.");}
  function showModal(title,body){$("#modalBody").innerHTML="<h2>"+title+"</h2>"+body;$("#modal").classList.remove("hidden");}
  function closeModal(){$("#modal").classList.add("hidden");}
  function generateDrafts(source,tone,point,count){
    const clean=source.trim().replace(/\s+/g," ");const topic=clean.split(/[.!?]/)[0].slice(0,120);const pool=[
      'The point about "'+topic+'" raises an important operational question. How are you seeing this translate into day-to-day decisions and measurable outcomes?',
      'A useful perspective. One additional consideration is the capability and operating conditions required to make this sustainable—not just the initial intent.',
      'This connects strategy with execution. I would be interested in the evidence being used to understand whether the change is becoming embedded in routine practice.',
      'There is an important distinction here between activity and impact. What signals are proving that the intended outcome is actually taking hold?',
      'The implementation context matters as much as the idea itself. How are leaders making space for feedback and course correction as this develops?'
    ];
    if(point.trim())pool[1]+=' My additional lens: '+point.trim()+'.';
    return pool.slice(0,Number(count)).map((t,i)=>({id:"CM-"+Date.now()+"-"+i,text:t,tone:tone,status:"Draft for review",createdAt:timeNow()}));
  }

  document.addEventListener("click",function(e){
    const nav=e.target.closest("[data-view]");if(nav){render(nav.dataset.view);return;}
    const go=e.target.closest("[data-go]");if(go){render(go.dataset.go);return;}
    const b=e.target.closest("[data-action]");if(!b)return;
    const action=b.dataset.action,id=b.dataset.id;
    if(action==="export"){exportData();return;}
    if(action==="export-csv"){exportCsv();return;}
    if(action==="stop-monitor"){state.monitor=null;log("Golden Hour timer stopped","Local demo session");save();render("golden");toast("Local timer stopped.");return;}
    if(action==="start-monitor"){
      const c=state.campaigns.find(x=>x.id===id);if(!c)return;
      if(state.monitor && state.monitor.status==="Monitoring locally (demo)"){toast("A local timer is already running.");return;}
      state.monitor={name:c.name,platform:c.platform,goal:c.goal,duration:c.duration||60,startedAt:Date.now(),status:"Monitoring locally (demo)"};
      c.status="Monitoring locally (demo)";log("Golden Hour timer started",c.platform+" · "+c.name);save();render("golden");toast("Local timer started. No platform action sent.");return;
    }
    if(action==="approve-comment"){const c=state.comments.find(x=>x.id===id);if(c)c.status="Approved for manual use";save();render("comments");toast("Draft approved for manual use.");return;}
    if(action==="copy-comment"){const c=state.comments.find(x=>x.id===id);if(c&&navigator.clipboard){navigator.clipboard.writeText(c.text).then(()=>toast("Draft copied."),()=>toast("Clipboard permission unavailable."));}else if(c){toast("Clipboard unavailable in this browser.");}return;}
    if(action==="clear-comments"){state.comments=[];save();render("comments");toast("Draft library cleared.");return;}
    if(action==="add-contact"){
      showModal("Add a community contact",'<form id="contactForm"><div class="field"><label>Name / public profile name</label><input id="contactName" required></div><div class="field" style="margin-top:9px"><label>Public profile URL (optional)</label><input id="contactUrl" type="url" placeholder="https://..."></div><div class="field" style="margin-top:9px"><label>Platform</label><select id="contactPlatform">'+options(platforms)+'</select></div><div class="field" style="margin-top:9px"><label>Topic</label><input id="contactTopic" required placeholder="e.g. Change management"></div><div class="field" style="margin-top:9px"><label>Permission / relationship</label><select id="contactPermission">'+options(["Public profile only","Opted in","Pending permission"])+'</select></div><button class="btn primary" style="margin-top:14px">Save contact</button></form>');return;
    }
    if(action==="toggle-rule"){
      const r=state.rules.find(x=>String(x.id)===id);if(!r)return;
      const enabled=!r.enabled;
      apiCall("/discovery/rules/"+id,{method:"PATCH",body:JSON.stringify({enabled:enabled})}).then(()=>{r.enabled=enabled;save();render("discovery");toast("Watch rule updated.");}).catch(err=>toast("Could not update live rule: "+err.message));
      return;
    }
    if(action==="delete-rule"){
      apiCall("/discovery/rules/"+id,{method:"DELETE"}).then(()=>{state.rules=state.rules.filter(x=>String(x.id)!==id);save();render("discovery");toast("Watch rule removed.");}).catch(err=>toast("Could not remove live rule: "+err.message));
      return;
    }
    if(action==="sample-scan"){
      const feed=$("#sampleFeed");if(feed)feed.innerHTML='<div class="empty">Scanning configured live sources…</div>';
      (async()=>{
        try{
          const scan=await apiCall("/discovery/scan",{method:"POST"});
          const items=await apiCall("/discovery/items?limit=50");
          const list=items.items||[];
          if(feed)feed.innerHTML=(list.length?list.map(x=>'<div class="activity"><i></i><div><b>'+esc((x.provider||"").toUpperCase())+' · '+esc(x.author||"Post")+'</b><small>'+esc(x.text||"")+'</small>'+(x.url?'<a target="_blank" rel="noopener" href="'+esc(x.url)+'">Open post ↗</a>':"")+'</div><span class="right">'+esc(x.created_at||"")+'</span></div>').join(""):'<div class="empty">No new matches returned. Check provider access, scopes and watch rules.</div>');
          const failures=(scan.rules||[]).filter(x=>x.status!=="success");
          toast(scan.new_items+" new items found. "+failures.length+" rule(s) need attention.");
        }catch(err){if(feed)feed.innerHTML='<div class="empty">'+esc(err.message)+'</div>';toast("Live discovery failed: "+err.message);}
      })();return;
    }
    if(action==="toggle-schedule"){
      const item=state.schedules.find(x=>String(x.id)===id);if(!item)return;
      const enable=item.status!=="Active";
      apiCall("/schedules/"+id,{method:"PATCH",body:JSON.stringify(enable?{approved:true,enabled:true,status:"Active"}:{enabled:false,status:"Paused"})}).then(()=>{
        item.status=enable?"Active":"Paused";item.approved=enable;log("Recurring programme updated",item.title);save();render("drip");toast(enable?"Recurring task execution activated.":"Programme paused.");
      }).catch(err=>toast("Schedule update failed: "+err.message));
      return;
    }
    if(action==="connect-provider"){
      const name=b.dataset.name;
      const id=providerIds[name];
      if(name==="Bluesky"){render("discovery");toast("Bluesky public discovery is available without account sign-in. Add a Bluesky watch rule to begin.");return;}
      const readiness=apiStatusData&&apiStatusData.providers?apiStatusData.providers[id]:null;
      if(name==="Mastodon"){
        showModal("Connect a Mastodon instance",'<form id="mastodonConnectForm"><div class="field"><label>Instance URL</label><input id="mastodonInstance" type="url" required placeholder="https://mastodon.social"></div><p class="metric-note">TAPAS will register a read-only application on this instance and request account, status and search scopes.</p><button class="btn primary" style="margin-top:12px">Continue to Mastodon →</button></form>');
        return;
      }
      if(!readiness||!readiness.configured){showProviderSetup(name,readiness);return;}
      window.location.href=API_BASE+"/api/connect/"+id+"/start";return;
    }
    if(action==="refresh-connections"){refreshServerModules().then(()=>render("connections"));return;}
    if(action==="refresh-tasks"){refreshServerModules().then(()=>render("drip"));return;}
    if(action==="sync-provider"){syncProvider(b.dataset.name);return;}
    if(action==="disconnect-provider"){
      const name=b.dataset.name;const id=providerIds[name];
      apiCall("/connect/"+id,{method:"DELETE"}).then(()=>refreshServerModules()).then(()=>{render("connections");toast(name+" disconnected.");}).catch(err=>toast("Disconnect failed: "+err.message));
      return;
    }
    if(action==="refresh-snapshots"){loadLiveSnapshots().then(()=>render("analytics"));return;}
    if(action==="integration-info"){
      const name=b.dataset.name;const d=integrations.find(x=>x[0]===name);
      showModal(name+" connection setup",'<p><b>Connection state:</b> Not connected.</p><p>'+esc(d?d[3]:"")+'</p><ul><li>Confirm the platform account and required access.</li><li>Use the platform official OAuth or permitted integration route.</li><li>Store tokens on a protected server, never in browser storage.</li><li>Validate analytics scopes before enabling live reporting.</li></ul><p>This prototype does not request or store credentials.</p>');return;
    }
    if(action==="reset"){showModal("Reset local demo data",'<p>This replaces campaigns, schedules, comments and contacts stored in this browser with the original sample data.</p><button class="btn danger" data-action="confirm-reset">Reset workspace data</button>');return;}
    if(action==="confirm-reset"){state=clone(seed);save();closeModal();render("dashboard");toast("Demo data restored.");return;}
  });
  document.addEventListener("submit",async function(e){
    const f=e.target;if(!f.id)return;e.preventDefault();
    if(f.id==="goldenForm"){
      const c={id:"GH-"+String(Date.now()).slice(-6),name:$("#gName").value.trim(),platform:$("#gPlatform").value,goal:$("#gGoal").value,url:$("#gUrl").value.trim(),status:"Draft — awaiting approval",createdAt:timeNow(),duration:Number($("#gDuration").value)};
      state.campaigns.unshift(c);log("Campaign plan created",c.platform+" · "+c.name);save();render("golden");toast("Campaign plan saved. No external action taken.");return;
    }
    if(f.id==="commentForm"){
      const source=$("#sourcePost").value;
      const tone=$("#cTone").value;
      const point=$("#cPoint").value;
      const count=Number($("#cCount").value);
      try {
        const response=await apiCall("/ai/comments",{method:"POST",body:JSON.stringify({post_text:source,audience:"TAPAS Advisory target audience",objective:"Add a useful, evidence-led contribution",tone:tone,count:count,point_of_view:point})});
        const ds=(response.comments||[]).map((c,i)=>({id:"AI-"+Date.now()+"-"+i,text:c.text||"",tone:c.type||tone,status:"Draft for review",createdAt:response.created_at||timeNow(),purpose:c.purpose||""}));
        if(!ds.length) throw new Error("Gemini returned no comment drafts.");
        state.comments=ds.concat(state.comments).slice(0,30);
        log("Gemini comment drafts generated",response.model+" · review required");
        save();render("comments");toast(ds.length+" Gemini drafts created. Review before use.");
      } catch(err) {
        toast("Live Gemini unavailable: "+err.message+". Configure the backend API key; no demo substitute was shown.");
      }
      return;
    }
    if(f.id==="watchForm"){
      const rule={keyword:$("#watchKeyword").value.trim(),platform:$("#watchPlatform").value,rule_type:$("#watchType").value,enabled:true};
      try {
        const saved=await apiCall("/discovery/rules",{method:"POST",body:JSON.stringify(rule)});
        state.rules.unshift({id:saved.id,keyword:saved.keyword,platform:saved.platform,type:saved.rule_type,enabled:!!saved.enabled});
        log("Live discovery rule created",rule.platform+" · "+rule.keyword);
        save();render("discovery");toast("Discovery rule saved to backend scheduler.");
      } catch(err) {
        toast("Could not save live watch rule: "+err.message);
      }
      return;
    }
    if(f.id==="dripForm"){
      const raw=$("#dDate").value;
      const scheduledAt=raw?new Date(raw+"T10:00:00").toISOString():new Date().toISOString();
      const payload={title:$("#dTitle").value.trim(),platform:$("#dPlatform").value,cadence:$("#dCadence").value,next_run_at:scheduledAt,deliverable:$("#dDeliverable").value,content:"",approved:false};
      try {
        const saved=await apiCall("/schedules",{method:"POST",body:JSON.stringify(payload)});
        const s={id:saved.id,title:saved.title,platform:saved.platform,cadence:saved.cadence,next:new Date(saved.next_run_at).toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"}),deliverable:saved.deliverable,status:saved.status};
        state.schedules.unshift(s);log("Recurring programme saved to backend",s.title);save();render("drip");toast("Recurring programme saved. It will create review tasks when due.");
      } catch(err) { toast("Could not save background schedule: "+err.message); }
      return;
    }
    if(f.id==="mastodonConnectForm"){
      const instance=$("#mastodonInstance").value.trim().replace(/\/$/,"");
      if(!instance.startsWith("https://")){toast("Use an HTTPS Mastodon instance URL.");return;}
      window.location.href=API_BASE+"/api/connect/mastodon/start?instance="+encodeURIComponent(instance);
      return;
    }
    if(f.id==="contactForm"){
      state.contacts.unshift({id:Date.now(),name:$("#contactName").value.trim(),url:$("#contactUrl").value.trim(),platform:$("#contactPlatform").value,topic:$("#contactTopic").value.trim(),permission:$("#contactPermission").value});log("Community contact added",$("#contactName").value.trim());save();closeModal();render("community");toast("Contact saved to local register.");return;
    }
  });
  document.addEventListener("change",function(e){
    if(e.target && e.target.id==="importFile"){
      const file=e.target.files && e.target.files[0];if(!file)return;
      const reader=new FileReader();reader.onload=function(){try{const x=JSON.parse(reader.result);if(!x||x.version!==1||!Array.isArray(x.campaigns)||!Array.isArray(x.rules)||!Array.isArray(x.schedules))throw new Error("format");state=Object.assign(clone(seed),x);save();render("settings");toast("Workspace backup imported.");}catch(err){toast("Import failed: invalid TAPAS backup.");}};reader.readAsText(file);
    }
  });
  $("#export").addEventListener("click",exportData);
  $("#closeModal").addEventListener("click",closeModal);
  $("#modal").addEventListener("click",function(e){if(e.target===$("#modal"))closeModal();});
  window.setInterval(function(){
    if(state.monitor && state.monitor.status==="Monitoring locally (demo)"){
      const duration=state.monitor.duration||60;
      const elapsed=Math.floor((Date.now()-state.monitor.startedAt)/60000);
      const n=$("#remaining");if(n)n.textContent=Math.max(0,duration-elapsed)+"m";
      if(elapsed>=duration){const name=state.monitor.name;state.monitor.status="Timer completed (demo)";state.campaigns.forEach(c=>{if(c.name===name&&c.status==="Monitoring locally (demo)")c.status="Timer completed (demo)";});log("Golden Hour timer completed",duration+" minutes elapsed; no live platform metric or action");save();render(state.activeView);}
    }
  },15000);
  const requestedView=new URLSearchParams(window.location.search).get("view");
  if(requestedView&&renderers[requestedView])state.activeView=requestedView;
  render(state.activeView||"dashboard");
  refreshServerModules().then(()=>{
    if(["connections","analytics","discovery","drip"].includes(state.activeView))render(state.activeView);
    const connected=new URLSearchParams(window.location.search).get("connected");
    if(connected)toast(connected+" account authorization completed.");
  });
})();