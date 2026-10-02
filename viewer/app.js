const BOOT_VERSION = "2026-10-01-02";
function showBootError(message){
  const subtitle=document.getElementById("subtitle");
  if(subtitle)subtitle.textContent=message;
  const panel=document.getElementById("panel");
  if(panel){
    let box=document.getElementById("bootStatus");
    if(!box){box=document.createElement("div");box.id="bootStatus";box.className="boot-error";panel.prepend(box);}
    box.textContent=message;
  }
}
window.addEventListener("error",e=>showBootError("Viewer runtime error: "+(e.message||"unknown JavaScript error")));
window.addEventListener("unhandledrejection",e=>showBootError("Viewer data error: "+(e.reason?.message||e.reason||"unknown promise error")));
if(!window.L){showBootError("Viewer initialization failed: Leaflet did not load.");throw new Error("Leaflet did not load");}
async function fetchJson(url){
  const response=await fetch(url,{cache:"no-store"});
  if(!response.ok)throw new Error(url+" returned HTTP "+response.status);
  return response.json();
}
const RESEARCH_RELEASE_STATUS = "candidate_only_not_operational";
const map=L.map("map",{zoomControl:true,preferCanvas:true}).setView([44.2,-73.1],8);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:12,attribution:"© OpenStreetMap contributors"}).addTo(map);
const radarLayer=L.layerGroup().addTo(map),objectsLayer=L.layerGroup().addTo(map);
let catalog=null,current=null,features=[],times=[],currentIndex=0,playing=false,timer=null,selectedKey=null,showAllTracks=false;
const isTrainingPage=document.body.dataset.mode==="training";
const radarLocations={KCXX:[44.511,-73.166],KTYX:[43.756,-75.680],KBTV:[44.472,-73.154]};
const num=(v,d=1)=>v==null||Number.isNaN(Number(v))?"—":Number(v).toFixed(d);
const fmtTime=t=>t?new Date(t).toLocaleString(undefined,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}):"—";
const fmtUtc=t=>t?new Date(t).toISOString().replace("T"," ").replace(".000Z","Z"):"—";
const setText=(id,v)=>{const el=document.getElementById(id);if(el)el.textContent=v??"—";};
const esc=v=>String(v??"—").replace(/[&<>"\']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));
const envValue=(e,key)=>e&&e[key]?e[key].value:null;
const formatEnv=(e,key)=>{const v=envValue(e,key);if(v==null)return"—";const u=e[key].units||"";return num(v,1)+(u?" "+u:"")};
function renderCaseInfo(){const c=current;setText("caseTitle",c?c.case_id+" • "+c.radar_site:"No case");setText("caseMeta",c?(c.source_study||"Historical study")+" • "+c.first_scan_utc?.slice(0,16)+" to "+c.last_scan_utc?.slice(0,16):"—");document.getElementById("caseGrid").innerHTML=[["Event onset",fmtUtc(c?.event_start_utc)],["Station",c?.observing_station||"—"],["Peak wind",c?.peak_wind_kt==null?"—":num(c.peak_wind_kt)+" kt"],["Min visibility",c?.min_visibility_km==null?"—":num(c.min_visibility_km)+" km"],["Tracks",c?.track_count??"—"],["Scans",c?.scan_count??"—"],["Radar frames",c?.radar_frames?.length??0]].map(x=>"<div><span>"+x[0]+"</span><b>"+x[1]+"</b></div>").join("");setText("subtitle",c?c.case_id+" • "+c.radar_site+" • "+c.status:"Loading historical pilot data…")}
function renderModelSummary(){
  const box=document.getElementById("modelSummary");
  const badge=document.getElementById("modelStatusBadge");
  const summary=catalog?.model_summary;
  if(!summary?.horizons?.length){
    badge.textContent="NOT AVAILABLE";
    box.textContent="No trained candidate metrics are embedded in this viewer build yet.";
    return;
  }
  badge.textContent="RESEARCH ONLY";
  const rows=summary.horizons;
  box.innerHTML="<div class='model-summary-grid'>"+rows.map(r=>{
    const auc=r.roc_auc==null?"—":Number(r.roc_auc).toFixed(2);
    const pr=r.pr_auc==null?"—":Number(r.pr_auc).toFixed(2);
    const brier=r.brier_score==null?"—":Number(r.brier_score).toFixed(3);
    const groups=r.positive_case_group_count==null?"—":r.positive_case_group_count;
    return "<div class='model-summary-cell'><span>"+r.horizon_minutes+" min</span><b>ROC "+auc+" • PR "+pr+"</b><b>Brier "+brier+" • "+groups+" positive groups</b></div>";
  }).join("")+"</div>"+
  "<div class='model-note'>These are exploratory case-held-out diagnostics from the research candidate. They are not an operational probability, threshold, warning recommendation, or release decision.</div>";
}

function populateCases(){const sel=document.getElementById("caseSelect");sel.innerHTML=catalog.cases.map((c,i)=>"<option value="+i+">"+c.case_id+" • "+c.radar_site+"</option>").join("");sel.onchange=()=>loadCase(Number(sel.value)).catch(err=>showBootError("Historical case failed to load: "+err.message))}
async function loadCase(index){current=catalog.cases[index];selectedKey=null;const analogButton=document.getElementById("analogsBtn");analogButton.disabled=true;analogButton.onclick=null;const geo=await fetchJson("data/"+current.file);features=geo.features||[];times=[...new Set(features.map(f=>f.properties.timestamp))].sort();currentIndex=0;document.getElementById("slider").max=Math.max(0,times.length-1);document.getElementById("slider").value=0;renderCaseInfo();addRadarMarker();fitToData();render()}
function addRadarMarker(){map.eachLayer(layer=>{if(layer.options?.className==="radar-station")map.removeLayer(layer)});const loc=radarLocations[current?.radar_site];if(loc)L.marker(loc,{icon:L.divIcon({className:"radar-station",iconSize:[12,12],iconAnchor:[6,6],html:""}),interactive:false,title:current.radar_site}).addTo(map)}
function fitToData(){const pts=features.map(f=>[Number(f.properties.centroid_lat),Number(f.properties.centroid_lon)]).filter(x=>x.every(Number.isFinite));if(!pts.length)return;map.fitBounds(L.latLngBounds(pts),{padding:[35,35],maxZoom:9})}
function featuresAt(ts){return features.filter(f=>f.properties.timestamp===ts)}
function render(){if(!times.length)return;const ts=times[currentIndex];setText("timelineTime",fmtTime(ts)+" • "+fmtUtc(ts));document.getElementById("slider").value=currentIndex;renderRadar(ts);renderTracks(ts);renderObjects(ts);updateSelection()}
function renderRadar(ts){radarLayer.clearLayers();const frames=current?.radar_frames||[],bounds=current?.radar_bounds;if(!frames.length||!bounds){setText("radarStatus","No reconstructed radar frame loaded");return}const exact=frames.find(f=>f.timestamp===ts);const frame=exact||[...frames].reverse().find(f=>f.timestamp<ts);if(!frame){setText("radarStatus","No frame at or before current time");return}const opacity=Number(document.getElementById("radarOpacity")?.value||78)/100;L.imageOverlay("data/"+frame.file,bounds,{opacity,interactive:false,attribution:"Historical Level-II reflectivity reconstruction"}).addTo(radarLayer);setText("radarStatus","Frame: "+fmtUtc(frame.timestamp)+(exact?"":" • prior available scan"))}
function historicalProbability(p){
  const vals=[p.probability_30min,p.probability_15min].map(Number).filter(Number.isFinite);
  return vals.length?vals[0]:null;
}
function historicalColor(prob){
  if(prob==null)return "#8b98a4";
  if(prob<.20)return "#55b7ff";
  if(prob<.40)return "#4fd1c5";
  if(prob<.60)return "#f5d66b";
  if(prob<.80)return "#f39b2f";
  return "#ef625f";
}
function historicalEvolution(p){
  const probs=[15,30,45,60].map(h=>Number(p["probability_"+h+"min"])).filter(Number.isFinite);
  if(probs.length>=2){
    const d=probs[probs.length-1]-probs[0];
    if(d>=.05)return "RISING";
    if(d<=-.05)return "FALLING";
  }
  const z=Number(p.reflectivity_trend_dbz_per_hr),g=Number(p.area_growth_fraction);
  if((Number.isFinite(z)&&z>=3)||(Number.isFinite(g)&&g>=.08))return "RISING";
  if((Number.isFinite(z)&&z<=-3)||(Number.isFinite(g)&&g<=-.08))return "FALLING";
  return "STEADY";
}
function renderTracks(ts){}

function renderObjects(ts){
  objectsLayer.clearLayers();
  featuresAt(ts).forEach(f=>{
    const p=f.properties,selected=selectedKey===p.track_key;
    const prob=historicalProbability(p),color=historicalColor(prob),evolution=historicalEvolution(p);
    const layer=L.geoJSON(f,{style:{
      color:selected?"#ffffff":color,fillColor:color,fillOpacity:selected?.30:.12,weight:selected?3:1.5
    }}).addTo(objectsLayer);
    layer.bindTooltip(
      "Track "+esc(p.object_id)+" • "+(prob==null?"SS —":"SS "+(prob*100).toFixed(0)+"%")+" • "+evolution+"<br>"+
      num(p.motion_speed_kt)+" kt @ "+num(p.motion_direction_deg,0)+"°",
      {sticky:true}
    );
    layer.bindPopup("<b>"+p.case_id+" • "+p.radar_site+"</b><br>Track "+esc(p.object_id)+"<br>"+fmtUtc(p.timestamp));
    layer.on("click",()=>selectObject(f));
    if(p.centroid_lat!=null&&p.centroid_lon!=null){
      const radius=Math.max(2500,Math.min(10000,(Math.max(Number(p.length_km)||0,Number(p.width_km)||0)||5)*500));
      L.circle([Number(p.centroid_lat),Number(p.centroid_lon)],{
        radius,color:selected?"#ffffff":color,weight:selected?3:2,fillColor:color,fillOpacity:.035,interactive:false
      }).addTo(objectsLayer);
    }
  });
  renderObjectList(ts);
}

function renderObjectList(ts){const box=document.getElementById("objectList"),count=document.getElementById("currentObjectCount");if(!box||!count)return;const rows=featuresAt(ts).slice().sort((a,b)=>Number(b.properties.max_reflectivity_dbz||0)-Number(a.properties.max_reflectivity_dbz||0));count.textContent=String(rows.length);if(!rows.length){box.innerHTML="<div class='history-empty'>No tracked objects at this scan.</div>";return}box.innerHTML=rows.map(f=>{const p=f.properties,selected=selectedKey===p.track_key;return "<button type='button' class='object-row"+(selected?" selected":"")+"' data-track='"+esc(p.track_key)+"'><span class='object-row-main'><b>Track "+esc(p.object_id)+"</b><span>"+num(p.max_reflectivity_dbz)+" dBZ • "+num(p.area_km2)+" km²</span></span><span class='object-row-sub'>"+num(p.motion_speed_kt)+" kt • "+esc(p.environment_status||"environment —")+"</span></button>"}).join("");box.querySelectorAll("[data-track]").forEach(btn=>{btn.onclick=()=>{const f=featuresAt(ts).find(x=>x.properties.track_key===btn.dataset.track);if(f)selectObject(f)}})}
function selectObject(f){selectedKey=f.properties.track_key;const b=document.getElementById("analogsBtn");b.disabled=false;b.onclick=()=>window.open("analogs.html?case="+catalog.cases.indexOf(current)+"&track="+encodeURIComponent(f.properties.track_key),"_blank");render()}
function trendSvg(rows,key,label,unit,activeIndex){
  const raw=rows.map(r=>Number(r.properties[key]));
  const vals=raw.filter(Number.isFinite);
  if(!vals.length)return "<div class='trend-row'><span>"+label+"</span><div class='trend-empty'>No data</div></div>";
  const W=250,H=54,P=8,min=Math.min(...vals),max=Math.max(...vals),range=Math.max(max-min,0.1);
  const points=rows.map((r,i)=>{const v=raw[i];return Number.isFinite(v)?{i,v}:null}).filter(Boolean);
  const x=i=>P+(rows.length===1?0:i*(W-2*P)/(rows.length-1));
  const y=v=>(H-P)-(v-min)/range*(H-2*P);
  const path=points.map((pt,i)=>(i?"L":"M")+x(pt.i).toFixed(1)+" "+y(pt.v).toFixed(1)).join(" ");
  const chosen=points.find(pt=>pt.i===activeIndex)||points.filter(pt=>pt.i<=activeIndex).pop()||points[0];
  const digits=label==="Max Z"?0:1;
  return "<div class='trend-row'><div class='trend-label'><span>"+label+"</span><b>"+num(chosen.v,digits)+" "+unit+"</b></div><svg class='trend-spark' viewBox='0 0 "+W+" "+H+"' aria-label='"+label+" trend'><line x1='"+P+"' y1='"+(H-P)+"' x2='"+(W-P)+"' y2='"+(H-P)+"' class='trend-axis'/><path d='"+path+"' class='trend-path'/><line x1='"+x(chosen.i).toFixed(1)+"' y1='"+P+"' x2='"+x(chosen.i).toFixed(1)+"' y2='"+(H-P)+"' class='trend-cursor'/><circle cx='"+x(chosen.i).toFixed(1)+"' cy='"+y(chosen.v).toFixed(1)+"' r='3.5' class='trend-current'/><text x='"+(P-2)+"' y='10' text-anchor='end' class='trend-scale'>"+num(max,digits)+"</text><text x='"+(P-2)+"' y='"+(H-P+3)+"' text-anchor='end' class='trend-scale'>"+num(min,digits)+"</text></svg></div>";
}
function renderTrackTrend(){
  const box=document.getElementById("trackTrend");
  if(!box)return;
  if(!selectedKey){box.innerHTML="<div class='history-empty'>Select a storm object to see intensity, size, and motion trends.</div>";return;}
  const rows=features.filter(x=>x.properties.track_key===selectedKey).sort((a,b)=>a.properties.timestamp.localeCompare(b.properties.timestamp));
  if(!rows.length){box.innerHTML="<div class='history-empty'>No trend history is available for this track.</div>";return;}
  const activeTs=times[currentIndex];
  let activeIndex=rows.findIndex(r=>r.properties.timestamp===activeTs);
  if(activeIndex<0)activeIndex=rows.map(r=>r.properties.timestamp).reduce((best,ts,i)=>ts<=activeTs?i:best,-1);
  if(activeIndex<0)activeIndex=0;
  box.innerHTML="<div class='trend-note'>Track "+esc(rows[0].properties.object_id)+" • "+rows.length+" scans • cursor marks the current replay time</div>"+
    trendSvg(rows,"max_reflectivity_dbz","Max Z","dBZ",activeIndex)+
    trendSvg(rows,"area_km2","Area","km²",activeIndex)+
    trendSvg(rows,"motion_speed_kt","Motion","kt",activeIndex);
}
function renderTrackHistory(){
  const box=document.getElementById("trackHistory");
  const count=document.getElementById("trackCount");
  if(!selectedKey){
    setText("trackCount","—");
    box.innerHTML="<div class='history-empty'>Select a storm object to see its scan-to-scan evolution.</div>";
    return;
  }
  const same=features
    .filter(x=>x.properties.track_key===selectedKey)
    .sort((a,b)=>a.properties.timestamp.localeCompare(b.properties.timestamp));
  setText("trackCount",same.length+" scans");
  if(!same.length){
    box.innerHTML="<div class='history-empty'>No object evolution history is available for this object.</div>";
    return;
  }
  const activeTs=times[currentIndex];
  const active=same.find(x=>x.properties.timestamp===activeTs) ||
    [...same].filter(x=>x.properties.timestamp<=activeTs).pop() ||
    same[0];
  const activeTimestamp=active.properties.timestamp;
  box.innerHTML="<div class='history-scroll'><table class='history-table'><thead><tr>"+
    "<th>Time</th><th>Max Z</th><th>Area</th><th>L × W</th><th>Motion</th><th>Z trend</th><th>Env</th>"+
    "</tr></thead><tbody>"+
    same.map(f=>{
      const p=f.properties;
      const currentRow=p.timestamp===activeTimestamp?" class='current'":"";
      const env=p.environment_status||"—";
      return "<tr"+currentRow+" data-ts='"+p.timestamp+"'>"+
        "<td>"+fmtTime(p.timestamp)+"</td>"+
        "<td>"+num(p.max_reflectivity_dbz)+"</td>"+
        "<td>"+num(p.area_km2)+" km²</td>"+
        "<td>"+num(p.length_km)+" × "+num(p.width_km)+" km</td>"+
        "<td>"+num(p.motion_speed_kt)+" kt</td>"+
        "<td>"+num(p.reflectivity_trend_dbz_per_hr)+"</td>"+
        "<td>"+env+"</td>"+
      "</tr>";
    }).join("")+
    "</tbody></table></div>";
  box.querySelectorAll("tr[data-ts]").forEach(row=>{
    row.onclick=()=>{
      const idx=times.indexOf(row.dataset.ts);
      if(idx>=0){
        currentIndex=idx;
        render();
      }
    };
  });
}
function renderProbabilityEvolution(){
  const box=document.getElementById("probabilityEvolutionBody");
  if(!box) return;
  if(!selectedKey){
    box.innerHTML="<div class='history-empty'>Select a storm object to plot its score through time.</div>";
    return;
  }
  const rows=features
    .filter(x=>x.properties.track_key===selectedKey)
    .sort((a,b)=>a.properties.timestamp.localeCompare(b.properties.timestamp));
  const points=rows.map(x=>{
    const p=x.properties, v=p.research_probabilities||{};
    return {ts:p.timestamp, values:["15min","30min","45min","60min"].map(h=>v[h]).map(v=>v==null?null:Number(v))};
  });
  const has=points.some(x=>x.values.some(v=>Number.isFinite(v)));
  if(!has){
    box.innerHTML="<div class='history-empty'>This track has no attached research score history.</div>";
    return;
  }

  const activeTs=times[currentIndex];
  let activePointIndex=points.findIndex(pt=>pt.ts===activeTs);
  if(activePointIndex<0){
    for(let i=0;i<points.length;i++){
      if(points[i].ts<=activeTs) activePointIndex=i;
    }
    if(activePointIndex<0) activePointIndex=0;
  }
  const active=points[activePointIndex]?.values||[];
  const prior=points[activePointIndex-1]?.values||[];
  const W=330,H=150,P=24;
  const observed=points.flatMap(pt=>pt.values).filter(v=>Number.isFinite(v)&&v>=0);
  const maxY=Math.min(1,Math.max(0.01,(Math.max(...observed)||0.01)*1.15));
  const xs=points.map((_,i)=>P+(points.length===1?0:i*(W-2*P)/(points.length-1)));
  const yFor=v=>(H-P)-Math.min(maxY,Math.max(0,v))/maxY*(H-2*P);
  const pathFor=idx=>{
    const valid=points.map((pt,i)=>({v:pt.values[idx],i})).filter(x=>Number.isFinite(x.v));
    if(!valid.length)return "";
    return valid.map((x,n)=>{
      const yy=yFor(x.v);
      return (n?"L":"M")+xs[x.i].toFixed(1)+" "+yy.toFixed(1);
    }).join(" ");
  };
  const labels=["15","30","45","60"], glyphs=["#58b9ff","#63d1a3","#d9aa64","#c9a3ff"];
  const currentX=xs[activePointIndex];
  const svg="<svg class='prob-chart' viewBox='0 0 "+W+" "+H+"' role='img' aria-label='Research probability evolution'>"+
    "<line x1='"+P+"' y1='"+(H-P)+"' x2='"+(W-P)+"' y2='"+(H-P)+"' class='chart-axis'/>"+
    "<line x1='"+P+"' y1='"+P+"' x2='"+P+"' y2='"+(H-P)+"' class='chart-axis'/>"+
    "<line x1='"+currentX.toFixed(1)+"' y1='"+P+"' x2='"+currentX.toFixed(1)+"' y2='"+(H-P)+"' class='chart-current'/>"+
    "<text x='"+(P-4)+"' y='"+(P+3)+"' text-anchor='end' class='chart-label'>"+(maxY*100).toFixed(1)+"%</text>"+
    "<text x='"+(P-4)+"' y='"+((H/2)+3)+"' text-anchor='end' class='chart-label'>"+(maxY*50).toFixed(1)+"%</text>"+
    "<text x='"+(P-4)+"' y='"+(H-P+3)+"' text-anchor='end' class='chart-label'>0%</text>"+
    [0,1,2,3].map(i=>{
      const path=pathFor(i);
      return path?"<path d='"+path+"' fill='none' stroke='"+glyphs[i]+"' stroke-width='2' stroke-linecap='round'/>":"";
    }).join("")+
    (points.map((pt,i)=>{
      return pt.values.map((v,j)=>{
        if(!Number.isFinite(v))return "";
        const yy=yFor(v);
        const current=i===activePointIndex;
        return "<circle cx='"+xs[i].toFixed(1)+"' cy='"+yy.toFixed(1)+"' r='"+(current?"3.5":"2.5")+"' fill='"+glyphs[j]+"'"+(current?" stroke='#ffffff' stroke-width='1.5'":"")+"/>"; 
      }).join("");
    }).join(""))+
    "</svg>"+
    "<div class='chart-legend'>"+labels.map((l,i)=>{
      const v=active[i], pv=prior[i];
      const delta=Number.isFinite(v)&&Number.isFinite(pv)?v-pv:null;
      const deltaText=delta==null?"":" • Δ "+(delta>=0?"+":"")+(delta*100).toFixed(1)+" pp";
      return "<span><i style='background:"+glyphs[i]+"'></i>"+l+"m "+(v==null?"—":(v*100).toFixed(1)+"%")+deltaText+"</span>";
    }).join("")+"</div>"+
    "<div class='research-prob-note'>Current scan: "+fmtUtc(points[activePointIndex]?.ts||activeTs)+". The trace follows only scores available at each historical scan; later scans are never used to construct an earlier point.</div>";
  box.innerHTML=svg;
}

function renderResearchProbabilities(p){
  const box=document.getElementById("researchProbabilityBody");
  if(!box)return;
  const values=p?.research_probabilities||{};
  const horizons=["15min","30min","45min","60min"];
  const available=horizons.filter(h=>values[h]!=null);
  if(!available.length){
    box.innerHTML="<div class='history-empty'>No out-of-fold research probability is attached to this scan.</div>";
    return;
  }
  box.innerHTML="<div class='research-prob-grid'>"+horizons.map(h=>{
    const v=values[h];
    return "<div class='research-prob-cell'><span>"+h.replace("min"," min")+"</span><b>"+(v==null?"—":(Number(v)*100).toFixed(1)+"%")+"</b></div>";
  }).join("")+"</div><div class='research-prob-note'>This is an out-of-fold research result for historical replay only. It is not an operational probability or warning recommendation.</div>";
}

function renderTrackerQc(p){
  const box=document.getElementById("trackerQc");
  if(!box)return;
  const score=p.track_quality_score==null?"—":num(p.track_quality_score,0);
  const tier=p.track_quality_tier||p.track_quality_gate||"—";
  const conf=p.track_association_confidence==null?"—":num(p.track_association_confidence,2);
  const margin=p.track_association_margin==null?"—":num(p.track_association_margin,2);
  const amb=p.track_association_ambiguous===true||p.track_association_ambiguous==="True"?"YES":"NO";
  const vel=p.track_velocity_mismatch_kt==null?"—":num(p.track_velocity_mismatch_kt,1)+" kt";
  const radar=p.track_radar_motion_mismatch_kt==null?"—":num(p.track_radar_motion_mismatch_kt,1)+" kt";
  const gap=p.track_gap_recovered===true||p.track_gap_recovered==="True"?"YES":"NO";
  const cls=tier==="pass"?"pass":(tier==="review"?"review":"reject");
  box.querySelector(".tracker-qc-grid").innerHTML=[
    ["Quality",score+(tier==="—"?"":" • "+tier),cls],
    ["Assoc. confidence",conf,""],
    ["Ambiguous match",amb,amb==="YES"?"warn":""],
    ["Assoc. margin",margin,""],
    ["Velocity mismatch",vel,Number(p.track_velocity_mismatch_kt||0)>45?"warn":""],
    ["Radar-motion mismatch",radar,Number(p.track_radar_motion_mismatch_kt||0)>50?"warn":""],
    ["Gap recovered",gap,gap==="YES"?"warn":""],
    ["QC flags",p.track_quality_flags||"none",""]
  ].map(x=>"<div class='tracker-qc-cell "+x[2]+"'><span>"+x[0]+"</span><b>"+esc(x[1])+"</b></div>").join("");
}
function updateSelection(){const same=features.filter(x=>x.properties.track_key===selectedKey);const exact=same.find(x=>x.properties.timestamp===times[currentIndex]);const prior=[...same].filter(x=>x.properties.timestamp<=times[currentIndex]).sort((a,b)=>a.properties.timestamp.localeCompare(b.properties.timestamp)).pop();const f=exact||prior||same[0],p=f?.properties;if(!p){setText("objectTitle","Select a storm object");setText("objectTime","—");setText("selectionState","No object selected");document.getElementById("metrics").innerHTML="";document.getElementById("environment").innerHTML="";setText("envSource","—");setText("outcome","Select an object to inspect its historical context.");renderTrackHistory();renderResearchProbabilities(null);renderProbabilityEvolution();return;}setText("selectionState","Selected");setText("objectTitle","Track "+p.object_id+" • "+p.radar_site);renderTrackerQc(p);renderResearchProbabilities(p);renderProbabilityEvolution();setText("objectTime",fmtTime(p.timestamp)+" • "+fmtUtc(p.timestamp));document.getElementById("metrics").innerHTML=[["Max Z",num(p.max_reflectivity_dbz)+" dBZ"],["Mean Z",num(p.mean_reflectivity_dbz)+" dBZ"],["Area",num(p.area_km2)+" km²"],["Length",num(p.length_km)+" km"],["Width",num(p.width_km)+" km"],["Aspect",num(p.aspect_ratio)],["Motion",num(p.motion_speed_kt)+" kt"],["Direction",num(p.motion_direction_deg,0)+"°"],["Z trend",num(p.reflectivity_trend_dbz_per_hr)+" dBZ/hr"],["Age",p.age_scans==null?"—":p.age_scans+" scans"],["Core fraction",p.core_fraction==null?"—":num(p.core_fraction*100)+"%"]].map(x=>"<div class='metric'><span>"+x[0]+"</span><b>"+x[1]+"</b></div>").join("");const e=p.environment||{};document.getElementById("environment").innerHTML=[["SBCAPE","sbcape_jkg"],["SBCIN","sbcin_jkg"],["MLCAPE","mlcape_jkg"],["MLCIN","mlcin_jkg"],["MUCAPE","mucape_jkg"],["DCAPE","dcape_jkg"],["PWAT","pwat_mm"],["LCL","lcl_m"],["RH 0–2 km","rh_0_2km_pct"],["0–1 km wind","wind_0_1km_kt"],["0–3 km wind","wind_0_3km_kt"],["0–1 km shear","shear_0_1km_kt"],["0–3 km shear","shear_0_3km_kt"],["0–6 km shear","shear_0_6km_kt"],["0–3 km lapse","lapse_rate_0_3km_c_km"],["0–7.5 km lapse","lapse_rate_0_7_5km_c_km"],["WB 0–3 km","wet_bulb_0_3km_c"],["0–1 km SRH","srh01_m2s2"],["SNSQ","snsq"]].map(x=>"<div class='env-item'><span>"+x[0]+"</span><b>"+formatEnv(e,x[1])+"</b></div>").join("");setText("envSource",p.environment_source?p.environment_source+" • "+num(p.environment_age_minutes,0)+" min old":"Unavailable");const associated=p.track_event_associated===true||p.track_event_associated==="True",relation=p.case_time_relation||"unclassified",out=document.getElementById("outcome");out.className="outcome "+(associated?"positive":"");out.innerHTML=associated?"<b>Associated with documented case context.</b><br>"+relation+". Published onset: "+fmtUtc(current.event_start_utc)+".<br><span class='truth-subnote'>Association is research context, not verified object-level truth.</span>":"<b>Case-context object.</b><br>Not treated as final object-level truth. Relation: "+relation+".";renderTrackHistory();renderTrackTrend()}
function advance(step){if(!times.length)return;currentIndex=(currentIndex+step+times.length)%times.length;render()}
function tick(){if(!playing)return;advance(1);timer=setTimeout(tick,700)}
function togglePlay(){playing=!playing;setText("playBtn",playing?"❚❚ Pause":"▶ Play");if(playing)tick();else clearTimeout(timer)}
document.getElementById("slider").addEventListener("input",e=>{currentIndex=Number(e.target.value);render()});
document.getElementById("allTracksToggle").addEventListener("change",e=>{showAllTracks=e.target.checked;renderTracks(times[currentIndex])});
document.getElementById("radarOpacity").addEventListener("input",e=>{setText("radarOpacityValue",e.target.value+"%");renderRadar(times[currentIndex])});
document.getElementById("prevBtn").onclick=()=>advance(-1);document.getElementById("nextBtn").onclick=()=>advance(1);document.getElementById("playBtn").onclick=togglePlay;
document.getElementById("detailsBtn").onclick=()=>{setText("statusText",catalog?.truth_note||"—");document.getElementById("statusList").innerHTML=[["Package",catalog?.version],["Data status",catalog?.data_status],["QC posture",catalog?.source_dataset_status],["Case/radar datasets",catalog?.cases?.length],["Source object rows",catalog?.source_object_rows],["Probability",catalog?.probability_status],["Build commit",catalog?.build_commit?catalog.build_commit.slice(0,12):"—"],["Build time",catalog?.build_time_utc?fmtUtc(catalog.build_time_utc):"—"],["Policy",catalog?.future_information_policy]].map(x=>"<div class='status-row'><span>"+x[0]+"</span><b>"+(x[1]??"—")+"</b></div>").join("");document.getElementById("modal").classList.remove("hidden")};
document.getElementById("closeModal").onclick=()=>document.getElementById("modal").classList.add("hidden");
Promise.all([fetch("data/catalog.json").then(r=>r.ok?r.json():Promise.reject(new Error("catalog HTTP "+r.status)))]).then(([c])=>{
  catalog=c;
  renderModelSummary();
  populateCases();
  const preferred=isTrainingPage?catalog.cases.findIndex(x=>x.case_id==="BTV20181121"):0;
  const initial=Math.max(0,preferred);
  const selector=document.getElementById("caseSelect");
  selector.value=String(initial);
  loadCase(initial).catch(err=>showBootError("Historical case failed to load: "+err.message));
}).catch(err=>showBootError("Viewer catalog failed to load: "+err.message));