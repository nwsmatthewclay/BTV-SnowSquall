const map=L.map("liveMap",{zoomControl:true,preferCanvas:true}).setView([44.15,-73.65],8);
map.createPane("radarMosaicPane");
map.getPane("radarMosaicPane").style.zIndex=250;
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:12,attribution:"© OpenStreetMap contributors"}).addTo(map);
const layers={KCXX:L.layerGroup().addTo(map),KTYX:L.layerGroup().addTo(map)};
const radarLocations={KCXX:[44.511,-73.166],KTYX:[43.756,-75.680]};
const LIVE_BASE="https://raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-live-data/viewer/data/live/";
const SHADOW_BASE="https://raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-shadow-data/viewer/data/shadow/";
let datasets={},selected=null,refreshTimer=null,hasInitialExtent=false,radarMosaicLayer=L.layerGroup().addTo(map),radarMosaic=null,radarMode="clean",qcdRadarLayer=null;

const num=(v,d=1)=>v==null||Number.isNaN(Number(v))?"—":Number(v).toFixed(d);
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

function shadowProbability(p){
  const shadow=shadowRecord(p.radar_site,p.track_id);
  const rp=shadow?.research_probabilities||{};
  const v30=rp["30"]??p.probability_30min;
  const v15=rp["15"]??p.probability_15min;
  return Number.isFinite(Number(v30))?Number(v30):(Number.isFinite(Number(v15))?Number(v15):null);
}
function shadowProbabilities(p){
  const shadow=shadowRecord(p.radar_site,p.track_id);
  const rp=shadow?.research_probabilities||{};
  const out={};
  [15,30,45,60].forEach(h=>{
    const v=rp[String(h)]??p["probability_"+h+"min"];
    out[h]=Number.isFinite(Number(v))?Number(v):null;
  });
  return out;
}
function snowSquallColor(prob){
  if(prob==null)return "#8b98a4";
  if(prob<.20)return "#55b7ff";
  if(prob<.40)return "#4fd1c5";
  if(prob<.60)return "#f5d66b";
  if(prob<.80)return "#f39b2f";
  return "#ef625f";
}
function probabilityLabel(prob){
  return prob==null?"—":(Number(prob)*100).toFixed(0)+"%";
}
const MAX_OBJECT_MOTION_KT=75.0;
function validMotionSpeed(p){
  const speed=Number(p.motion_speed_kt);
  const age=Number(p.age_scans);
  if(Number.isFinite(speed)&&speed>=0&&speed<=MAX_OBJECT_MOTION_KT&&(!Number.isFinite(age)||age>1)) return speed;
  const radar=Number(p.radar_motion_speed_kt);
  if(Number.isFinite(radar)&&radar>=0&&radar<=MAX_OBJECT_MOTION_KT) return radar;
  return null;
}
function motionReadout(p){
  const speed=validMotionSpeed(p);
  if(speed==null)return "—";
  const rawAge=Number(p.age_scans);
  const objectSpeed=Number(p.motion_speed_kt);
  const usedRadar=!Number.isFinite(objectSpeed)||objectSpeed<0||objectSpeed>MAX_OBJECT_MOTION_KT||(Number.isFinite(rawAge)&&rawAge<=1);
  const dir=usedRadar?Number(p.radar_motion_direction_deg):Number(p.motion_direction_deg??p.motion_dir_deg);
  return Number.isFinite(dir)?num(speed)+" kt @ "+num(dir,0)+"°"+(usedRadar?" • radar motion":"") : num(speed)+" kt";
}
function evolutionSignal(p){
  const vals=[15,30,45,60].map(h=>shadowProbabilities(p)[h]).filter(Number.isFinite);
  if(vals.length>=2){
    const delta=vals[vals.length-1]-vals[0];
    if(delta>=.05)return {label:"Increasing probability",short:"RISING"};
    if(delta<=-.05)return {label:"Decreasing probability",short:"FALLING"};
    return {label:"Little probability change",short:"STEADY"};
  }
  const z=Number(p.reflectivity_trend_dbz_per_hr),g=Number(p.area_growth_fraction);
  if((Number.isFinite(z)&&z>=3)||(Number.isFinite(g)&&g>=.08))return {label:"Radar echo strengthening",short:"RISING"};
  if((Number.isFinite(z)&&z<=-3)||(Number.isFinite(g)&&g<=-.08))return {label:"Radar echo weakening",short:"FALLING"};
  if(Number.isFinite(z)||Number.isFinite(g))return {label:"Radar echo relatively steady",short:"STEADY"};
  return {label:"Evolution not yet established",short:"UNKNOWN"};
}
function renderMap(summary){
  Object.values(layers).forEach(l=>l.clearLayers());
  const bounds=[];
  summary.filter(x=>!x.error).forEach(x=>{
    (x.features||[]).forEach(f=>{
      const p=f.properties||{},id=String(p.track_id??"—");
      const isSelected=selected&&String(selected.track_id)===id&&selected.radar_site===x.site;
      const probe={...p,radar_site:x.site},prob=shadowProbability(probe),color=snowSquallColor(prob);
      const shape=L.geoJSON(f,{style:{
        color:isSelected?"#ffffff":color,
        fillColor:color,
        fillOpacity:isSelected?.35:.18,
        weight:isSelected?3:1.5
      }}).addTo(layers[x.site]);
      shape.bindTooltip(
        "<b>"+esc(x.site)+" • Object "+esc(id)+"</b><br>"+
        "Snow Squall probability: "+esc(probabilityLabel(prob))+"<br>"+
        "Evolution: "+esc(evolutionSignal(probe).short),
        {sticky:true,direction:"top"}
      );
      shape.on("click",()=>selectObject({...p,radar_site:x.site}));
      if(isSelected&&p.centroid_lat!=null&&p.centroid_lon!=null){
        L.marker([Number(p.centroid_lat),Number(p.centroid_lon)],{
          icon:L.divIcon({
            className:"live-object-label-wrap",
            iconSize:null,
            iconAnchor:[0,0],
            html:"<div class='live-object-label selected'>"+esc(x.site)+" • "+esc(id)+"</div>"
          }),
          interactive:false
        }).addTo(layers[x.site]);
      }
      const b=shape.getBounds?.();
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
  all.sort((a,b)=>Number(shadowProbability(b)||0)-Number(shadowProbability(a)||0));
  let usingHistory=false;
  if(!all.length){
    usingHistory=true;
    summary.filter(x=>!x.error).forEach(x=>{
      const latestByTrack=new Map();
      (x.history||[]).forEach(r=>{
        if(r.track_id==null)return;
        const id=String(r.track_id),prior=latestByTrack.get(id);
        if(!prior||String(r.timestamp)>String(prior.timestamp))latestByTrack.set(id,r);
      });
      latestByTrack.forEach(r=>all.push({...r,radar_site:x.site,source_kind:"recent"}));
    });
    all.sort((a,b)=>String(b.timestamp||"").localeCompare(String(a.timestamp||"")));
  }
  document.getElementById("objectCount").textContent=String(all.length)+(usingHistory?" recent":" active");
  if(!all.length){
    document.getElementById("objectList").innerHTML="<div class='live-card'>No current or recent tracked objects are available.</div>";
    return;
  }
  document.getElementById("objectList").innerHTML=all.slice(0,20).map(p=>{
    const score=shadowProbability(p),state=lifecycleState(p),signal=evolutionSignal(p),color=snowSquallColor(score);
    return "<div class='live-object "+(selected&&selected.track_id===p.track_id&&selected.radar_site===p.radar_site?"selected":"")+"' data-id='"+esc(p.radar_site+"|"+p.track_id)+"'>"+
      "<div class='title'>"+esc(p.radar_site)+" • Track "+esc(p.track_id)+" <span class='chip'>"+esc(state)+"</span><span class='chip'>"+(p.source_kind==="recent"?"RECENT":"ACTIVE")+"</span></div>"+
      "<div class='sub'>"+esc(fmt(p.timestamp))+(p.source_kind==="recent"?" • latest retained track sample":"")+"</div>"+
      "<div class='chips'><span class='chip' style='border:1px solid "+color+"'>"+esc(snowSquallProbabilityLabel(score))+"</span><span class='chip'>"+num(p.motion_speed_kt)+" kt @ "+num(p.motion_direction_deg??p.motion_dir_deg,0)+"°</span><span class='chip'>"+esc(signal.short)+"</span><span class='chip'>"+num(p.max_reflectivity_dbz)+" dBZ</span></div></div>";
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
    const sub=err?"error":(fractfunction renderObjectList(summary){
  let all=[];
  summary.filter(x=>!x.error).forEach(x=>(x.features||[]).forEach(f=>all.push({...f.properties,radar_site:x.site,source_kind:"current"})));
  all.sort((a,b)=>Number(shadowProbability(b)||0)-Number(shadowProbability(a)||0));
  let usingHistory=false;
  if(!all.length){
    usingHistory=true;
    summary.filter(x=>!x.error).forEach(x=>{
      const latestByObject=new Map();
      (x.history||[]).forEach(r=>{
        if(r.track_id==null)return;
        const id=String(r.track_id),prior=latestByObject.get(id);
        if(!prior||String(r.timestamp)>String(prior.timestamp))latestByObject.set(id,r);
      });
      latestByObject.forEach(r=>all.push({...r,radar_site:x.site,source_kind:"recent"}));
    });
    all.sort((a,b)=>String(b.timestamp||"").localeCompare(String(a.timestamp||"")));
  }
  document.getElementById("objectCount").textContent=String(all.length)+(usingHistory?" recent":" active");
  if(!all.length){
    document.getElementById("objectList").innerHTML="<div class='live-card'>No current or recent objects are available.</div>";
    return;
  }
  document.getElementById("objectList").innerHTML=all.slice(0,20).map(p=>{
    const score=shadowProbability(p),color=snowSquallColor(score),state=evolutionSignal(p);
    return "<div class='live-object "+(selected&&selected.track_id===p.track_id&&selected.radar_site===p.radar_site?"selected":"")+"' data-id='"+esc(p.radar_site+"|"+p.track_id)+"'>"+
      "<div class='title'>"+esc(p.radar_site)+" • Object "+esc(p.track_id)+" <span class='chip'>"+esc(state.short)+"</span></div>"+
      "<div class='sub'>"+esc(fmt(p.timestamp))+"</div>"+
      "<div class='chips'><span class='chip' style='border:1px solid "+color+"'>Snow Squall "+probabilityLabel(score)+"</span><span class='chip'>"+num(p.max_reflectivity_dbz)+" dBZ</span><span class='chip'>"+num(p.area_km2)+" km²</span></div></div>";
  }).join("");
  document.querySelectorAll(".live-object").forEach(el=>el.onclick=()=>{
    const [site,id]=el.dataset.id.split("|");
    const item=all.find(p=>p.radar_site===site&&String(p.track_id)===String(id));
    if(item)selectObject(item);
  });
}
function evolutionRows(p){
  const rows=(datasets[p.radar_site]?.history||[])
    .filter(r=>String(r.track_id)===String(p.track_id))
    .sort((a,b)=>String(a.timestamp).localeCompare(String(b.timestamp)))
    .map(r=>({...r,motion_speed_kt:validMotionSpeed(r)}));
  if(p.timestamp&&!rows.some(r=>String(r.timestamp)===String(p.timestamp))){
    rows.push({...p,motion_speed_kt:validMotionSpeed(p)});
  }
  return rows;
}
function probabilityHistory(p,rows){
  const records=(datasets[p.radar_site]?.shadowHistory||[])
    .filter(r=>String(r.track_id)===String(p.track_id))
    .sort((a,b)=>String(a.timestamp).localeCompare(String(b.timestamp)));
  const points=records.map(r=>{
    const rp=r.research_probabilities||{};
    const v=rp["30"]??r.probability_30min;
    return {timestamp:r.timestamp,value:Number.isFinite(Number(v))?Number(v):null};
  }).filter(x=>x.value!=null);
  const current=shadowProbability(p);
  if(current!=null&&!points.some(x=>String(x.timestamp)===String(p.timestamp)))points.push({timestamp:p.timestamp,value:current});
  return points;
}
function probabilityChart(points){
  if(!points.length)return "<div class='history-empty'>Snow Squall probability history is not available for this object yet.</div>";
  const W=700,H=210,P=28,min=0,max=1,innerW=W-2*P,innerH=H-2*P;
  const x=i=>P+(points.length===1?innerW/2:i*innerW/(points.length-1));
  const y=v=>(H-P)-v*innerH;
  const path=points.map((pt,i)=>(i?"L":"M")+x(i).toFixed(1)+" "+y(pt.value).toFixed(1)).join(" ");
  const ticks=[0,.25,.5,.75,1];
  return "<svg class='evolution-chart' viewBox='0 0 "+W+" "+H+" aria-label='Snow Squall probability evolution'>"+
    ticks.map(v=>"<line x1='"+P+"' y1='"+y(v)+"' x2='"+(W-P)+"' y2='"+y(v)+"' class='chart-grid'/><text x='"+(P-6)+"' y='"+(y(v)+3)+"' text-anchor='end' class='chart-label'>"+(v*100).toFixed(0)+"%</text>").join("")+
    "<path d='"+path+"' class='probability-path'/>"+
    points.map((pt,i)=>"<circle cx='"+x(i)+"' cy='"+y(pt.value)+"' r='4' class='probability-point'><title>"+fmt(pt.timestamp)+" • "+(pt.value*100).toFixed(1)+"%</title></circle>").join("")+
    (points.length>1?"<text x='"+P+"' y='"+(H-5)+"' class='chart-label'>"+esc(fmt(points[0].timestamp))+"</text><text x='"+(W-P)+"' y='"+(H-5)+"' text-anchor='end' class='chart-label'>"+esc(fmt(points[points.length-1].timestamp))+"</text>":"")+
    "</svg>";
}
function renderLiveTrend(p){
  const box=document.getElementById("liveTrend");
  if(!box)return;
  if(!p){
    box.innerHTML="<div class='history-empty'>Select a live object to see its evolution.</div>";
    return;
  }
  const rows=evolutionRows(p);
  const probs=probabilityHistory(p,rows);
  const signal=evolutionSignal(p),score=shadowProbability(p),color=snowSquallColor(score);
  box.innerHTML=
    "<div class='evolution-header'><div><span>OBJECT "+esc(p.track_id)+" • "+esc(p.radar_site)+"</span><b>"+esc(signal.label)+"</b></div><span>"+rows.length+" observations</span></div>"+
    "<div class='probability-readout'><div class='probability-readout-head'><span>SNOW SQUALL PROBABILITY</span><b style='color:"+color+"'>"+probabilityLabel(score)+"</b></div>"+
      "<div class='probability-grid'>"+[15,30,45,60].map(h=>{
        const v=shadowProbabilities(p)[h];
        return "<div class='probability-cell'><span>"+h+" min</span><b>"+probabilityLabel(v)+"</b></div>";
      }).join("")+"</div>"+
      "<div class='probability-note'>Research shadow score; operational probability remains gated during model validation.</div></div>"+
    "<div class='evolution-chart-card'><div class='evolution-chart-head'><span>30-minute Snow Squall probability through object lifetime</span><b>"+esc(signal.short)+"</b></div>"+probabilityChart(probs)+"</div>"+
    "<div class='trend-set'>"+
      liveSpark(rows,"max_reflectivity_dbz","Max Z","dBZ")+
      liveSpark(rows,"area_km2","Area","km²")+
      liveSpark(rows,"motion_speed_kt","Motion","kt")+
    "</div>";
}
function selectObject(p){
  selected=p;
  document.getElementById("selectionState").textContent="Selected: "+p.radar_site+" object "+p.track_id;
  const env=p.environment||{};
  const nested=env.fields||{};
  const envFields={
    ...nested,
    cape_jkg:nested.cape_jkg?.value??p.cape_jkg,
    cin_jkg:nested.cin_jkg?.value??p.cin_jkg,
    mlcape_jkg:nested.mlcape_jkg?.value??p.mlcape_jkg,
    mlcin_jkg:nested.mlcin_jkg?.value??p.mlcin_jkg,
    mucape_jkg:nested.mucape_jkg?.value??p.mucape_jkg,
    pwat_mm:nested.pwat_mm?.value??p.pwat_mm,
    srh01_m2s2:nested.srh01_m2s2?.value??p.srh01_m2s2,
    shear_0_6km_ms:nested.shear_0_6km_ms?.value??p.shear_0_6km_ms,
    temperature_2m_k:nested.temperature_2m_k?.value??p.temperature_2m_k,
    dewpoint_2m_k:nested.dewpoint_2m_k?.value??p.dewpoint_2m_k,
    gust_ms:nested.gust_ms?.value??p.gust_ms
  };
  const score=shadowProbability(p),color=snowSquallColor(score),signal=evolutionSignal(p);
  document.getElementById("selectedSummary").innerHTML=
    "<div class='selected-object-head'><div><div class='detail-title'>"+esc(p.radar_site)+" • Object "+esc(p.track_id)+"</div><div class='detail-sub'>"+esc(fmt(p.timestamp))+"</div></div>"+
    "<div class='selected-probability' style='border-color:"+color+"'><span>Snow Squall</span><b>"+probabilityLabel(score)+"</b></div></div>"+
    "<div class='live-stat'><span>Evolution</span><b>"+esc(signal.label)+"</b></div>"+
    "<div class='live-stat'><span>Max Z</span><b>"+num(p.max_reflectivity_dbz)+" dBZ</b></div>"+
    "<div class='live-stat'><span>Area</span><b>"+num(p.area_km2)+" km²</b></div>"+
    "<div class='live-stat'><span>Motion</span><b>"+num(p.motion_speed_kt)+" kt @ "+num(p.motion_direction_deg??p.motion_dir_deg,0)+"°</b></div>"+
    renderEnvironment(envFields);
  renderLiveTrend(p);
}

