const map=L.map("liveMap",{zoomControl:true,preferCanvas:true}).setView([44.15,-73.65],8);
map.createPane("radarMosaicPane");
map.getPane("radarMosaicPane").style.zIndex=250;
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:12,attribution:"© OpenStreetMap contributors"}).addTo(map);
const layers={KCXX:L.layerGroup().addTo(map),KTYX:L.layerGroup().addTo(map)};
const radarLocations={KCXX:[44.511,-73.166],KTYX:[43.756,-75.680]};
const LIVE_BASE="https://raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-live-data/viewer/data/live/";
const SHADOW_BASE="https://raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-shadow-data/viewer/data/shadow/";
let datasets={},selected=null,refreshTimer=null,hasInitialExtent=false,radarMosaicLayer=L.layerGroup().addTo(map),radarMosaic=null,radarMode="clean",qcdRadarLayer=null;

const num=(v,d=1)=>v==null||Number.isNaN(Number(v))?"—":Number(v).toFixed(d); const shadowScoreFor=(p)=>{const r=shadowRecord(p.radar_site,p.track_id)?.research_probabilities||{};const v=r["15"]??r["15min"];return Number.isFinite(Number(v))?Number(v):null;};
const fmt=t=>t?new Date(t).toLocaleString(undefined,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit",second:"2-digit"}):"—";
const ageMinutes=t=>t?Math.max(0,(Date.now()-new Date(t).getTime())/60000):Infinity;
const esc=s=>String(s??"—").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
const ktFromMs=v=>v==null||Number.isNaN(Number(v))?null:Number(v)*1.943844492;
const cFromK=v=>v==null||Number.isNaN(Number(v))?null:Number(v)-273.15;
const url=name=>LIVE_BASE+name+"?cb="+Date.now();
const shadowUrl=name=>SHADOW_BASE+name+"?cb="+Date.now();
const mosaicMetaUrl=()=>LIVE_BASE+"radar_mosaic.json?cb="+Date.now();
const mosaicImageUrl=(mode="clean")=>{
  const product=radarMosaic?.display_products||{};
  const name=mode==="raw"?(product.raw_image||"radar_mosaic_raw.png"):(product.clean_image||"radar_mosaic_clean.png");
  return LIVE_BASE+name+"?cb="+Date.now();
};

function markerIcon(site){
  return L.divIcon({className:"radar-station",iconSize:[12,12],iconAnchor:[6,6],html:""});
}

function addRadarMarkers(){
  Object.entries(radarLocations).forEach(([site,loc])=>{
    L.marker(loc,{icon:markerIcon(site),interactive:false,title:site}).addTo(map);
  });
}

const OBJECT_FEED_SUFFIX="_objects.geojson";
function feedUrl(site,kind){
  return kind==="objects"
    ? url(site+OBJECT_FEED_SUFFIX)
    : url(site+"_"+kind+".json");
}

async function fetchOptionalJson(target,fallback){
  try{
    const response=await fetch(target);
    if(!response.ok)return fallback;
    return await response.json();
  }catch(_){
    return fallback;
  }
}

async function getFeed(site){
  const [geo,state,history,health,shadow,shadowHistory]=await Promise.all([
    fetch(feedUrl(site,"objects")).then(r=>r.ok?r.json():Promise.reject(new Error(site+" objects HTTP "+r.status))),
    fetch(feedUrl(site,"state")).then(r=>r.ok?r.json():Promise.reject(new Error(site+" state HTTP "+r.status))),
    fetchOptionalJson(feedUrl(site,"history"),[]),
    fetchOptionalJson(feedUrl(site,"health"),null),
    fetchOptionalJson(shadowUrl(site+"_shadow.json"),null),
    fetchOptionalJson(shadowUrl(site+"_shadow_history.json"),[])
  ]);
  return {geo,state,history,health,shadow,shadowHistory};
}
async function getRadarMosaic(){
  try{
    const response=await fetch(mosaicMetaUrl());
    if(!response.ok)return null;
    return await response.json();
  }catch(_){return null;}
}
function renderRadarMosaic(meta){
  radarMosaicLayer.clearLayers();
  if(mrmsFallbackLayer){try{map.removeLayer(mrmsFallbackLayer)}catch(_){} mrmsFallbackLayer=null;}
  if(qcdRadarLayer){try{map.removeLayer(qcdRadarLayer)}catch(_){} qcdRadarLayer=null;}
  radarMosaic=meta;
  const status=document.getElementById("mosaicStatus");
  const sources=document.getElementById("mosaicSources");
  const time=document.getElementById("mosaicTime");
  const modeLabel=document.getElementById("hudMode");
  if(!meta||meta.status!=="ready"||!meta.bounds){
    if(status)status.textContent="Local mosaic unavailable";
    if(sources)sources.textContent="NOAA QC fallback";
    if(time)time.textContent="Live NOAA feed";
    if(modeLabel)modeLabel.textContent="NOAA QC FALLBACK";
    addMrmsFallback();
    return;
  }

  const src=(meta.sources||[]).map(x=>x.radar).filter(Boolean);
  if(status)status.textContent=src.length===2?"READY • KCXX + KTYX":("READY • "+src.join(" + "));
  if(sources)sources.textContent=src.join(" + ")||"—";
  const times=(meta.sources||[]).map(x=>x.scan_time_utc).filter(Boolean).sort();
  if(time)time.textContent=times.length?fmt(times[times.length-1]):fmt(meta.updated_utc);
  if(modeLabel)modeLabel.textContent=radarMode==="raw"?"RAW DISPLAY":(radarMode==="qcd"?"NOAA QC DISPLAY":"CLEAN DISPLAY");

  if(radarMode==="qcd"){
    addMrmsFallback();
  }else{
    const overlay=L.imageOverlay(mosaicImageUrl(radarMode),meta.bounds,{
      pane:"radarMosaicPane",
      opacity:radarMode==="raw"?.66:.84,
      interactive:false,
      crossOrigin:true
    });
    overlay.once("error",()=>{
      radarMosaicLayer.clearLayers();
      if(status)status.textContent="Local image failed • NOAA QC fallback";
      addMrmsFallback();
    });
    overlay.addTo(radarMosaicLayer);
  }

  if(!hasInitialExtent){map.fitBounds(meta.bounds,{padding:[25,25],maxZoom:8});hasInitialExtent=true;}
}
function setRadarMode(mode){
  radarMode=mode;
  document.querySelectorAll(".display-btn").forEach(btn=>btn.classList.toggle("active",btn.dataset.radarMode===mode));
  if(radarMosaic)renderRadarMosaic(radarMosaic);
  const subtitle=document.getElementById("hudMode");
  if(subtitle)subtitle.textContent=mode==="raw"?"RAW DISPLAY":(mode==="qcd"?"NOAA QC DISPLAY":"CLEAN DISPLAY");
}

let mrmsFallbackLayer=null;
function addMrmsFallback(){
  if(mrmsFallbackLayer)return;
  try{
    const url="https://mapservices.weather.noaa.gov/eventdriven/rest/services/radar/radar_base_reflectivity/MapServer/export";
    const imageUrl=url+"?bbox=-76.9075,41.861,-70.3925,46.3983&bboxSR=4326&imageSR=4326&size=1400,900&format=png32&transparent=true&f=image";
    mrmsFallbackLayer=L.imageOverlay(imageUrl,[[41.861,-76.908],[46.398,-70.392]],{
      pane:"radarMosaicPane",opacity:.62,interactive:false,crossOrigin:true
    }).addTo(radarMosaicLayer);
  }catch(_){}
}

function summarize(site,item){
  const {geo,state,history,health,shadow,shadowHistory}=item;
  const features=geo.features||[];
  const last=state.last_scan_time_utc||geo.metadata?.scan_time_utc||geo.metadata?.last_scan_utc;
  const age=ageMinutes(last);
  const good=age<=30;
  return {site,features,state,geo,history,health,shadow,shadowHistory,last,age,good};
}

function renderRadarCards(summary){
  document.getElementById("radarCards").innerHTML=summary.map(x=>{
    if(x.error){
      return "<div class='live-card'><h3>"+esc(x.site)+" <span class='chip'>ERROR</span></h3>"+
        "<div class='live-stat'><span>Feed</span><b>Unavailable</b></div>"+
        "<div class='live-stat'><span>Reason</span><b>"+esc(x.error)+"</b></div>"+
        "<div class='live-stat'><span>Live shadow</span><b>"+(x.shadow?.scored_object_count??0)+" scored</b></div></div>";
    }
    const quality=x.good?"LIVE":"STALE";
    return "<div class='live-card'><h3>"+x.site+" <span class='chip'>"+quality+"</span></h3>"+
      "<div class='live-stat'><span>Last scan</span><b>"+esc(fmt(x.last))+"</b></div>"+
      "<div class='live-stat'><span>Age</span><b>"+(Number.isFinite(x.age)?num(x.age,1)+" min":"—")+"</b></div>"+
      "<div class='live-stat'><span>Objects</span><b>"+x.features.length+"</b></div>"+
      "<div class='live-stat'><span>History</span><b>"+x.history.length.toLocaleString()+" records</b></div>"+
      "<div class='live-stat'><span>Publish state</span><b>"+esc(x.health?.status||"unknown")+"</b></div>"+
      "<div class='live-stat'><span>Live shadow</span><b>"+(x.shadow?.scored_object_count??0)+" scored</b></div></div>";
  }).join("");
}

function objectColor(p){
  const z=Number(p.max_reflectivity_dbz);
  if(z>=45)return "#ff6b6b";
  if(z>=35)return "#ffd166";
  return "#57bbff";
}

function renderMap(summary){
  Object.values(layers).forEach(l=>l.clearLayers());
  const bounds=[];
  summary.filter(x=>!x.error).forEach(x=>{
    (x.features||[]).forEach(f=>{
      const p=f.properties||{};
      const id=String(p.track_id??"—");
      const isSelected=selected&&String(selected.track_id)===id&&selected.radar_site===x.site;
      const fill=objectColor(p);
      const layer=L.geoJSON(f,{style:{color:isSelected?"#ffffff":fill,fillColor:fill,fillOpacity:isSelected?.50:.18,weight:isSelected?3:1.5}}).addTo(layers[x.site]);
      layer.bindTooltip("<b>"+esc(x.site)+" • Object "+esc(id)+"</b><br>"+num(p.max_reflectivity_dbz)+" dBZ • "+num(p.area_km2)+" km² • "+num(p.motion_speed_kt)+" kt",{sticky:true,direction:"top"});
      layer.on("click",()=>selectObject({...p,radar_site:x.site}));
      if(isSelected&&p.centroid_lat!=null&&p.centroid_lon!=null){
        L.marker([Number(p.centroid_lat),Number(p.centroid_lon)],{icon:L.divIcon({className:"live-object-label-wrap",iconSize:null,iconAnchor:[0,0],html:"<div class='live-object-label selected'>"+esc(x.site)+"-"+esc(id)+"</div>"}),interactive:false}).addTo(layers[x.site]).bringToFront();
      }
      const b=layer.getBounds?.();
      if(b&&b.isValid())bounds.push(b);
    });
  });
  if(bounds.length&&!hasInitialExtent){
    let b=bounds[0];
    for(let i=1;i<bounds.length;i++)b=b.extend(bounds[i]);
    map.fitBounds(b,{padding:[30,30],maxZoom:9});
    hasInitialExtent=true;
  }
}
function renderObjectList(summary){
  let all=[];
  summary.filter(x=>!x.error).forEach(x=>(x.features||[]).forEach(f=>all.push({...f.properties,radar_site:x.site,source_kind:"current"})));
  all.sort((a,b)=>{const as=shadowScoreFor(a),bs=shadowScoreFor(b);if(as!=null||bs!=null)return (bs??-1)-(as??-1);return Number(b.candidate_rank_score??-1)-Number(a.candidate_rank_score??-1)||Number(b.max_reflectivity_dbz||0)-Number(a.max_reflectivity_dbz||0);});

  let usingHistory=false;
  if(!all.length){
    usingHistory=true;
    summary.filter(x=>!x.error).forEach(x=>{
      const latestByTrack=new Map();
      (x.history||[]).forEach(r=>{
        if(r.track_id==null)return;
        const id=String(r.track_id);
        const prior=latestByTrack.get(id);
        if(!prior || String(r.timestamp)>String(prior.timestamp)) latestByTrack.set(id,r);
      });
      latestByTrack.forEach(r=>all.push({...r,radar_site:x.site,source_kind:"recent"}));
    });
    all.sort((a,b)=>String(b.timestamp||"").localeCompare(String(a.timestamp||"")));
  }

  // Current objects are the operational map inventory. Retained history is
  // shown only when there are no current objects, and is explicitly marked.
  document.getElementById("objectCount").textContent=String(all.length)+(usingHistory?" recent":" active");
  if(!all.length){
    document.getElementById("objectList").innerHTML="<div class='live-card'>No current or recent tracked objects are available.</div>";
    return;
  }

  document.getElementById("objectList").innerHTML=all.slice(0,20).map(p=>{
    const shadow=shadowRecord(p.radar_site,p.track_id);
    const rp=shadow?.research_probabilities||{};
    const score=rp["15"];
    const state=lifecycleState(p);
    return "<div class='live-object "+(selected&&selected.track_id===p.track_id&&selected.radar_site===p.radar_site?"selected":"")+"' data-id='"+esc(p.radar_site+"|"+p.track_id)+"'>"+
    "<div class='title'>"+esc(p.radar_site)+" • Track "+esc(p.track_id)+" <span class='chip'>"+esc(state)+"</span><span class='chip'>"+(p.source_kind==="recent"?"RECENT":"ACTIVE")+"</span></div>"+
    "<div class='sub'>"+esc(fmt(p.timestamp))+(p.source_kind==="recent"?" • latest retained track sample":"")+"</div>"+
    "<div class='chips'><span class='chip'>"+num(p.max_reflectivity_dbz)+" dBZ</span><span class='chip'>"+num(p.motion_speed_kt)+" kt</span><span class='chip'>"+num(p.area_km2)+" km²</span>"+(p.candidate_rank_score==null?"":"<span class='chip'>Rank "+Number(p.candidate_rank_score).toFixed(0)+"</span>")+(score==null?"":"<span class='chip research-chip'>15m "+(Number(score)*100).toFixed(0)+"% RESEARCH</span>")+"<span class='chip'>"+esc(p.data_quality||"—")+"</span></div></div>";
  }).join("");

  document.querySelectorAll(".live-object").forEach(el=>el.onclick=()=>{
    const [site,id]=el.dataset.id.split("|");
    const item=all.find(p=>p.radar_site===site&&String(p.track_id)===String(id));
    if(item)selectObject(item);
  });
}

function shadowRecord(site,trackId){
  const records=datasets[site]?.shadow?.records||[];
  return records.find(r=>String(r.track_id)===String(trackId))||null;
}
function shadowGrid(record){
  const probs=record?.research_probabilities||{};
  const coverage=record?.feature_coverage||{};
  const errors=record?.score_errors||{};
  if(!Object.keys(probs).length){
    const detail=Object.keys(errors).length
      ? " "+Object.entries(errors).map(([h,e])=>h+" min: "+e).join(" • ")
      : "";
    return "<div class='shadow-note'>No live research score is available yet."+esc(detail)+"</div>";
  }
  return "<div class='shadow-grid'>" + [15,30,45,60].map(h=>{
    const p=probs[String(h)];
    const fraction=coverage[String(h)]?.fraction;
    const err=errors[String(h)];
    const sub=err?"error":(fraction==null?"coverage —":(Number(fraction)*100<80?"warming up • coverage "+(Number(fraction)*100).toFixed(0)+"%":"coverage "+(Number(fraction)*100).toFixed(0)+"%"));
    return "<div class='shadow-cell'><span>"+h+" min</span><b>"+(p==null?(err?"ERROR":"—"):""+(Number(p)*100).toFixed(1)+"%")+"</b><span>"+esc(sub)+"</span></div>";
  }).join("")+"</div>";
}

function renderShadowCard(summary){
  const box=document.getElementById("shadowCardBody");
  if(!box)return;
  const rows=summary.filter(x=>x.shadow).map(x=>({
    site:x.site,
    updated:x.shadow.updated_utc,
    scored:Number(x.shadow.scored_object_count||0),
    total:Number(x.shadow.current_object_count||0),
    status:x.shadow.operational_release_status||"unknown"
  }));
  if(!rows.length){
    box.innerHTML="<div class='shadow-note'>No published shadow feed is available yet.</div>";
    return;
  }
  box.innerHTML=rows.map(row=>
    "<div class='live-stat'><span>"+esc(row.site)+"</span><b>"+row.scored+" / "+row.total+" scored</b></div>"+
    "<div class='live-stat'><span>Updated</span><b>"+esc(fmt(row.updated))+"</b></div>"+
    "<div class='live-stat'><span>Status</span><b>"+esc(row.status)+"</b></div>"
  ).join("")+
    "<div class='shadow-note'>The operational object feed remains probability-free. Scores shown here come from the isolated research shadow branch.</div>";
}
function renderEnvironment(fields){
  const env=fields||{};
  const rows=[
    ["SBCAPE","cape_jkg",v=>num(v,0)+" J/kg"],
    ["SBCIN","cin_jkg",v=>num(v,0)+" J/kg"],
    ["MLCAPE","mlcape_jkg",v=>num(v,0)+" J/kg"],
    ["MLCIN","mlcin_jkg",v=>num(v,0)+" J/kg"],
    ["MUCAPE","mucape_jkg",v=>num(v,0)+" J/kg"],
    ["PWAT","pwat_mm",v=>num(v,1)+" mm"],
    ["0–1 km SRH","srh01_m2s2",v=>num(v,0)+" m²/s²"],
    ["0–6 km shear","shear_0_6km_ms",v=>num(ktFromMs(v),1)+" kt"],
    ["2 m temp","temperature_2m_k",v=>num(cFromK(v),1)+" °C"],
    ["2 m dewpoint","dewpoint_2m_k",v=>num(cFromK(v),1)+" °C"],
    ["Surface gust","gust_ms",v=>num(ktFromMs(v),1)+" kt"],
    ["SNSQ","snsq",v=>num(v,2)],
    ["SNSQ 0–2 km RH","mean_rh_0_2km_pct",v=>num(v,0)+"%"],
    ["SNSQ Δθe 0–2 km","thetae_delta_0_2km_k",v=>num(v,1)+" K"],
    ["SNSQ 0–2 km wind","mean_wind_0_2km_ms",v=>num(ktFromMs(v),1)+" kt"],
    ["2 m wet-bulb","wetbulb_2m_c",v=>num(v,1)+" °C"],
  ];
  return "<div class='live-env-grid'>"+rows.map(([label,key,format])=>{
    const value=env[key];
    return "<div class='env-item'><span>"+label+"</span><b>"+(value==null?"—":format(value))+"</b></div>";
  }).join("")+"</div>";
}

function lifecycleState(p){const age=Number(p?.age_scans||0),trend=Number(p?.reflectivity_trend_dbz_per_hr);if(age<=2)return "NEW";if(Number.isFinite(trend)&&trend>=3)return "INTENSIFYING";if(Number.isFinite(trend)&&trend<=-3)return "WEAKENING";return "STEADY";}
function liveSpark(rows,key,label,unit){const vals=rows.map(r=>Number(r[key])).filter(Number.isFinite);if(!vals.length)return "<div class='live-spark-row'><span>"+label+"</span><div class='trend-empty'>No data</div></div>";const W=300,H=58,P=7,min=Math.min(...vals),max=Math.max(...vals),range=Math.max(max-min,.1),pts=rows.map((r,i)=>{const v=Number(r[key]);return Number.isFinite(v)?{i,v}:null}).filter(Boolean),x=i=>P+(rows.length===1?0:i*(W-2*P)/Math.max(1,rows.length-1)),y=v=>(H-P)-(v-min)/range*(H-2*P),path=pts.map((pt,i)=>(i?"L":"M")+x(pt.i).toFixed(1)+" "+y(pt.v).toFixed(1)).join(" "),last=pts[pts.length-1],digits=label==="Max Z"?0:1;return "<div class='live-spark-row'><div class='live-spark-label'><span>"+label+"</span><b>"+num(last.v,digits)+" "+unit+"</b></div><svg class='live-spark' viewBox='0 0 "+W+" "+H+"'><line x1='"+P+"' y1='"+(H-P)+"' x2='"+(W-P)+"' y2='"+(H-P)+"' class='trend-axis'/><path d='"+path+"' class='trend-path'/><circle cx='"+x(last.i).toFixed(1)+"' cy='"+y(last.v).toFixed(1)+"' r='3.5' class='trend-current'/></svg></div>";}
function renderLiveTrend(p){const box=document.getElementById("liveTrend");if(!box)return;if(!p){box.innerHTML="<div class='history-empty'>Select a live object to see its evolution.</div>";return;}const rows=(datasets[p.radar_site]?.history||[]).filter(r=>String(r.track_id)===String(p.track_id)).sort((a,b)=>String(a.timestamp).localeCompare(String(b.timestamp)));if(!rows.length){box.innerHTML="<div class='history-empty'>No retained history for this object.</div>";return;}box.innerHTML="<div class='live-trend-head'><span>Track "+esc(p.track_id)+"</span><b>"+lifecycleState(p)+"</b><small>"+rows.length+" retained scans</small></div>"+liveSpark(rows,"max_reflectivity_dbz","Max Z","dBZ")+liveSpark(rows,"area_km2","Area","km²")+liveSpark(rows,"motion_speed_kt","Motion","kt");const scored=(datasets[p.radar_site]?.shadowHistory||[]).filter(r=>String(r.track_id)===String(p.track_id)).sort((a,b)=>String(a.timestamp).localeCompare(String(b.timestamp))),latest=scored.at(-1),any=scored.some(r=>Object.values(r.research_probabilities||{}).some(v=>v!=null));if(any){box.innerHTML+="<div class='live-prob-trend'><div class='live-trend-head'><span>Research probability evolution</span><b>RESEARCH ONLY</b></div><div class='live-prob-grid'>"+[["15 min",latest?.research_probabilities?.["15"]],["30 min",latest?.research_probabilities?.["30"]],["45 min",latest?.research_probabilities?.["45"]],["60 min",latest?.research_probabilities?.["60"]]].map(x=>"<div><span>"+x[0]+"</span><b>"+(x[1]==null?"—":(Number(x[1])*100).toFixed(1)+"%")+"</b></div>").join("")+"</div><div class='mosaic-note'>Latest available shadow score. Early scans may be unscored while temporal predictors warm up.</div></div>";}}
function renderSelectedHistory(p){
  const box=document.getElementById("liveHistory");
  const count=document.getElementById("liveTrackCount");
  if(!p){
    count.textContent="—";
    box.innerHTML="<div class='history-empty'>Select a current object to see its scan-to-scan history.</div>";
    return;
  }
  const summary=datasets[p.radar_site];
  const rows=(summary?.history||[])
    .filter(r=>String(r.track_id)===String(p.track_id))
    .sort((a,b)=>String(a.timestamp).localeCompare(String(b.timestamp)));
  count.textContent=rows.length+" scans";
  if(!rows.length){
    box.innerHTML="<div class='history-empty'>No persisted history is available for this track yet.</div>";
    return;
  }
  const currentTimestamp=p.timestamp;
  box.innerHTML="<div class='history-scroll'><table class='history-table'><thead><tr>"+
    "<th>Time</th><th>Max Z</th><th>Area</th><th>L × W</th><th>Motion</th><th>Z trend</th><th>Env</th>"+
    "</tr></thead><tbody>"+
    rows.map(r=>{
      const current=String(r.timestamp)===String(currentTimestamp)?" class='current'":"";
      return "<tr"+current+" data-ts='"+esc(r.timestamp)+"'>"+
        "<td>"+esc(fmt(r.timestamp))+"</td>"+
        "<td>"+num(r.max_reflectivity_dbz)+" dBZ</td>"+
        "<td>"+num(r.area_km2)+" km²</td>"+
        "<td>"+num(r.length_km)+" × "+num(r.width_km)+" km</td>"+
        "<td>"+num(r.motion_speed_kt)+" kt</td>"+
        "<td>"+num(r.reflectivity_trend_dbz_per_hr)+" dBZ/hr</td>"+
        "<td>"+esc(r.environment_status||"—")+"</td>"+
      "</tr>";
    }).join("")+
    "</tbody></table></div>";
}

function selectObject(p){
  selected=p;
  document.getElementById("selectionState").textContent="Selected: "+p.radar_site+" track "+p.track_id;

  const env=p.environment||{};
  const nested=env.fields||{};
  const envFields={
    ...nested,
    cape_jkg: nested.cape_jkg?.value ?? p.cape_jkg,
    cin_jkg: nested.cin_jkg?.value ?? p.cin_jkg,
    mlcape_jkg: nested.mlcape_jkg?.value ?? p.mlcape_jkg,
    mlcin_jkg: nested.mlcin_jkg?.value ?? p.mlcin_jkg,
    mucape_jkg: nested.mucape_jkg?.value ?? p.mucape_jkg,
    pwat_mm: nested.pwat_mm?.value ?? p.pwat_mm,
    srh01_m2s2: nested.srh01_m2s2?.value ?? p.srh01_m2s2,
    shear_0_6km_ms: nested.shear_0_6km_ms?.value ?? p.shear_0_6km_ms,
    temperature_2m_k: nested.temperature_2m_k?.value ?? p.temperature_2m_k,
    dewpoint_2m_k: nested.dewpoint_2m_k?.value ?? p.dewpoint_2m_k,
    gust_ms: nested.gust_ms?.value ?? p.gust_ms,
    visibility_m: nested.visibility_m?.value ?? p.visibility_m
  };
  const envSource=env.source||p.environment_source||"—";
  const envStatus=p.environment_status||env.status||"—";
  const motionDir=p.motion_direction_deg ?? p.motion_dir_deg;
  document.getElementById("selectedSummary").innerHTML=
    "<div class='live-stat'><span>Radar</span><b>"+esc(p.radar_site)+"</b></div>"+
    "<div class='live-stat'><span>Track</span><b>"+esc(p.track_id)+"</b></div>"+
    "<div class='live-stat'><span>Time</span><b>"+esc(fmt(p.timestamp))+"</b></div>"+
    "<div class='live-stat'><span>Max Z</span><b>"+num(p.max_reflectivity_dbz)+" dBZ</b></div>"+
    "<div class='live-stat'><span>Mean Z</span><b>"+num(p.mean_reflectivity_dbz)+" dBZ</b></div>"+
    "<div class='live-stat'><span>Area</span><b>"+num(p.area_km2)+" km²</b></div>"+
    "<div class='live-stat'><span>Shape</span><b>"+num(p.length_km)+" × "+num(p.width_km)+" km</b></div>"+
    "<div class='live-stat'><span>Motion</span><b>"+num(p.motion_speed_kt)+" kt @ "+num(motionDir,0)+"°</b></div>"+
    "<div class='live-stat'><span>Age</span><b>"+(p.age_scans==null?"—":esc(p.age_scans+" scans"))+"</b></div>"+
    "<div class='live-stat'><span>Z trend</span><b>"+num(p.reflectivity_trend_dbz_per_hr)+" dBZ/hr</b></div>"+
    "<div class='live-stat'><span>Environment</span><b>"+esc(envSource)+" • "+esc(envStatus)+"</b></div>"+
    renderEnvironment(envFields)+
    "<div class='live-card'><h3>Live research shadow</h3>"+shadowGrid(shadowRecord(p.radar_site,p.track_id))+
    "<div class='shadow-note'>Candidate model scored this live object separately from the operational feed. Research only.</div></div>"+
    "<div class='live-stat'><span>Data quality</span><b>"+esc(p.data_quality||"—")+"</b></div>"+
    "<div class='live-stat'><span>Detection evidence</span><b>"+esc(Array.isArray(p.detection_evidence)?p.detection_evidence.join(" • "):(p.detection_evidence||"—"))+"</b></div>"+
    (p.candidate_rank_score==null?"":"<div class='live-stat'><span>Candidate rank</span><b>"+Number(p.candidate_rank_score).toFixed(0)+"/100 • "+esc(p.candidate_rank_tier||"—")+"</b></div>");
  renderSelectedHistory(p);
  renderLiveTrend(p);
}

async function refresh(){
  document.getElementById("overallTitle").textContent="Refreshing live feeds…";
  document.getElementById("overallText").textContent="Fetching latest persisted KCXX/KTYX objects and histories.";
  try{
    const sites=["KCXX","KTYX"];
    const mosaicPromise=getRadarMosaic();
    const results=await Promise.all(sites.map(async site=>{
      try{
        return summarize(site,await getFeed(site));
      }catch(err){
        return {site,error:String(err.message||err),features:[],history:[],state:{},geo:{},good:false};
      }
    }));
    const summary=results;
    datasets=Object.fromEntries(summary.map(x=>[x.site,x]));
    renderRadarMosaic(await mosaicPromise);
    renderRadarCards(summary);
    renderShadowCard(summary);
    renderMap(summary);
    renderObjectList(summary);

    if(selected){
      const latest=summary
        .flatMap(x=>(x.features||[]).map(f=>({...f.properties,radar_site:x.site})))
        .find(p=>p.radar_site===selected.radar_site&&String(p.track_id)===String(selected.track_id));
      if(latest)selectObject(latest);
      else renderSelectedHistory(selected);
    }

    const degraded=summary.filter(x=>x.error||!x.good);
    const allObjects=summary.reduce((n,x)=>n+x.features.length,0);
    const hudScan=document.getElementById("hudScan");
    const hudSources=document.getElementById("hudSources");
    const hudObjects=document.getElementById("hudObjects");
    const feedBadge=document.getElementById("feedBadge");
    const empty=document.getElementById("mapEmptyState");
    if(hudScan)hudScan.textContent=fmt(summary.map(x=>x.last).filter(Boolean).sort().at(-1));
    if(hudSources)hudSources.textContent=summary.filter(x=>!x.error).map(x=>x.site).join(" + ")||"NO DATA";
    if(hudObjects)hudObjects.textContent=allObjects+" objects";
    if(feedBadge)feedBadge.textContent=degraded.length?"DEGRADED":"HEALTHY";
    if(empty){
      empty.classList.toggle("visible",allObjects===0);
      empty.querySelector("strong").textContent=degraded.length?"Radar data unavailable":"No significant echoes";
      empty.querySelector("span").textContent=degraded.length?"Waiting for a valid radar product.":"Radar feed is healthy. Weak returns below the display threshold are intentionally muted.";
    }
    document.getElementById("overallTitle").textContent=degraded.length?"Live feed degraded":"Live feeds healthy";
    document.getElementById("overallText").textContent=degraded.length?
      degraded.map(x=>x.site+" "+(x.error?"unavailable":"stale")).join(", ")+" • "+allObjects+" current objects":
      "KCXX/KTYX current object feeds • "+allObjects+" candidate objects • live research shadow "+summary.reduce((n,x)=>n+(x.shadow?.scored_object_count||0),0)+" scored";
    document.getElementById("overallStatus").classList.toggle("degraded",degraded.length>0);
    const latestRadarTime=summary.map(x=>x.last).filter(Boolean).sort().at(-1);
    const latestRadarAge=latestRadarTime?ageMinutes(latestRadarTime):Infinity;
    document.getElementById("subtitle").textContent=latestRadarTime
      ?"Radar: "+fmt(latestRadarTime)+" • "+(Number.isFinite(latestRadarAge)?num(latestRadarAge,1)+" min old":"age unknown")
      :"Radar time unavailable";
    const footerTime=document.getElementById("footerRefreshTime");
    if(footerTime)footerTime.textContent="Page "+fmt(new Date().toISOString());
    const footerBtn=document.getElementById("footerRefreshBtn");
    if(footerBtn)footerBtn.disabled=false;
  }catch(err){
    document.getElementById("overallTitle").textContent="Live feed unavailable";
    document.getElementById("overallText").textContent=String(err);
    document.getElementById("overallStatus").classList.add("degraded");
  }
}

addRadarMarkers();
const liveTrackToggle=document.getElementById("showAllLiveTracks");
if(liveTrackToggle)liveTrackToggle.onchange=e=>{showAllLiveTracks=e.target.checked;renderMap(Object.values(datasets))};
document.getElementById("refreshBtn").onclick=refresh;
const footerRefreshBtn=document.getElementById("footerRefreshBtn");
if(footerRefreshBtn)footerRefreshBtn.onclick=refresh;
document.querySelectorAll(".display-btn").forEach(btn=>btn.onclick=()=>setRadarMode(btn.dataset.radarMode));
refresh();
refreshTimer=setInterval(refresh,60000);
