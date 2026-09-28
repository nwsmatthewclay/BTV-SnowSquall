const map=L.map("liveMap",{zoomControl:true,preferCanvas:true}).setView([44.15,-73.65],8);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:12,attribution:"© OpenStreetMap contributors"}).addTo(map);
const layers={KCXX:L.layerGroup().addTo(map),KTYX:L.layerGroup().addTo(map)};
const radarLocations={KCXX:[44.511,-73.166],KTYX:[43.756,-75.680]};
const LIVE_BASE="https://raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-model-foundation/viewer/data/live/";
let datasets={},selected=null,refreshTimer=null;

const num=(v,d=1)=>v==null||Number.isNaN(Number(v))?"—":Number(v).toFixed(d);
const fmt=t=>t?new Date(t).toLocaleString(undefined,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit",second:"2-digit"}):"—";
const ageMinutes=t=>t?Math.max(0,(Date.now()-new Date(t).getTime())/60000):Infinity;
const esc=s=>String(s??"—").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
const url=(name)=>LIVE_BASE+name+"?cb="+Date.now();

function markerIcon(site){
  return L.divIcon({className:"radar-station",iconSize:[12,12],iconAnchor:[6,6],html:""});
}
function addRadarMarkers(){
  Object.entries(radarLocations).forEach(([site,loc])=>{
    L.marker(loc,{icon:markerIcon(site),interactive:false,title:site}).addTo(map);
  });
}
function feedUrl(site,kind){return url(site+"_"+kind+".json");}

async function getFeed(site){
  const [geo,state]=await Promise.all([
    fetch(feedUrl(site,"objects")).then(r=>r.ok?r.json():Promise.reject(new Error("objects HTTP "+r.status))),
    fetch(feedUrl(site,"state")).then(r=>r.ok?r.json():Promise.reject(new Error("state HTTP "+r.status)))
  ]);
  return {geo,state};
}

function summarize(site,item){
  const {geo,state}=item;
  const features=geo.features||[];
  const last=state.last_scan_time_utc||geo.metadata?.scan_time_utc||geo.metadata?.last_scan_utc;
  const age=ageMinutes(last);
  const good=age<=30;
  return {site,features,state,geo,last,age,good};
}

function renderRadarCards(summary){
  document.getElementById("radarCards").innerHTML=summary.map(x=>{
    const quality=x.good?"LIVE":"STALE";
    return "<div class='live-card'><h3>"+x.site+" <span class='chip'>"+quality+"</span></h3>"+
      "<div class='live-stat'><span>Last scan</span><b>"+esc(fmt(x.last))+"</b></div>"+
      "<div class='live-stat'><span>Age</span><b>"+(Number.isFinite(x.age)?num(x.age,1)+" min":"—")+"</b></div>"+
      "<div class='live-stat'><span>Objects</span><b>"+x.features.length+"</b></div>"+
      "<div class='live-stat'><span>Probability</span><b>Disabled</b></div></div>";
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
  summary.forEach(x=>{
    (x.features||[]).forEach(f=>{
      const p=f.properties||{};
      const selected=selected?.track_id===p.track_id && selected?.radar_site===p.radar_site;
      const layer=L.geoJSON(f,{style:{
        color:selected?"#ffffff":objectColor(p),
        fillColor:objectColor(p),
        fillOpacity:selected?.48:.24,
        weight:selected?3:2
      }}).addTo(layers[x.site]);
      if(f.geometry?.coordinates) layer.eachLayer(g=>{const b=g.getBounds?.();if(b&&b.isValid())bounds.push(b)});
      layer.bindTooltip(
        x.site+" • Track "+esc(p.track_id)+" • "+num(p.max_reflectivity_dbz)+" dBZ • "+num(p.motion_speed_kt)+" kt",
        {sticky:true}
      );
      layer.on("click",()=>selectObject({...p,radar_site:x.site}));
    });
  });
  if(bounds.length){
    let b=bounds[0];
    for(let i=1;i<bounds.length;i++)b=b.extend(bounds[i]);
    map.fitBounds(b,{padding:[30,30],maxZoom:9});
  }
}

function renderObjectList(summary){
  const all=[];
  summary.forEach(x=>(x.features||[]).forEach(f=>all.push({...f.properties,radar_site:x.site})));
  all.sort((a,b)=>Number(b.max_reflectivity_dbz||0)-Number(a.max_reflectivity_dbz||0));
  document.getElementById("objectCount").textContent=all.length;
  if(!all.length){
    document.getElementById("objectList").innerHTML="<div class='live-card'>No candidate objects on the latest available scans.</div>";
    return;
  }
  document.getElementById("objectList").innerHTML=all.slice(0,20).map(p=>
    "<div class='live-object "+(selected&&selected.track_id===p.track_id&&selected.radar_site===p.radar_site?"selected":"")+"' data-id='"+esc(p.radar_site+"|"+p.track_id)+"'>"+
    "<div class='title'>"+esc(p.radar_site)+" • Track "+esc(p.track_id)+"</div>"+
    "<div class='sub'>"+esc(fmt(p.timestamp))+"</div>"+
    "<div class='chips'><span class='chip'>"+num(p.max_reflectivity_dbz)+" dBZ</span><span class='chip'>"+num(p.motion_speed_kt)+" kt</span><span class='chip'>"+num(p.area_km2)+" km²</span><span class='chip'>"+esc(p.data_quality||"—")+"</span></div></div>"
  ).join("");
  document.querySelectorAll(".live-object").forEach(el=>el.onclick=()=>{
    const [site,id]=el.dataset.id.split("|");
    const item=all.find(p=>p.radar_site===site&&String(p.track_id)===String(id));
    if(item)selectObject(item);
  });
}

function selectObject(p){
  selected=p;
  document.getElementById("selectionState").textContent=p.radar_site+" track "+p.track_id;
  const env=p.environment||{};
  const envSource=env.source||p.environment_source||"—";
  document.getElementById("selectedObject").innerHTML=
    "<div class='live-stat'><span>Radar</span><b>"+esc(p.radar_site)+"</b></div>"+
    "<div class='live-stat'><span>Track</span><b>"+esc(p.track_id)+"</b></div>"+
    "<div class='live-stat'><span>Time</span><b>"+esc(fmt(p.timestamp))+"</b></div>"+
    "<div class='live-stat'><span>Max Z</span><b>"+num(p.max_reflectivity_dbz)+" dBZ</b></div>"+
    "<div class='live-stat'><span>Mean Z</span><b>"+num(p.mean_reflectivity_dbz)+" dBZ</b></div>"+
    "<div class='live-stat'><span>Area</span><b>"+num(p.area_km2)+" km²</b></div>"+
    "<div class='live-stat'><span>Motion</span><b>"+num(p.motion_speed_kt)+" kt @ "+num(p.motion_direction_deg,0)+"°</b></div>"+
    "<div class='live-stat'><span>Age</span><b>"+(p.age_scans==null?"—":esc(p.age_scans+" scans"))+"</b></div>"+
    "<div class='live-stat'><span>Z trend</span><b>"+num(p.reflectivity_trend_dbz_per_hr)+" dBZ/hr</b></div>"+
    "<div class='live-stat'><span>Environment</span><b>"+esc(envSource)+" • "+esc(p.environment_status||"—")+"</b></div>"+
    "<div class='live-stat'><span>Data quality</span><b>"+esc(p.data_quality||"—")+"</b></div>";
}

async function refresh(){
  document.getElementById("overallTitle").textContent="Refreshing live feeds…";
  document.getElementById("overallText").textContent="Fetching latest persisted KCXX/KTYX objects.";
  try{
    const summary=(await Promise.all(["KCXX","KTYX"].map(s=>getFeed(s)))).map((item,i)=>summarize(i?"KTYX":"KCXX",item));
    datasets=Object.fromEntries(summary.map(x=>[x.site,x]));
    renderRadarCards(summary);
    renderMap(summary);
    renderObjectList(summary);
    const stale=summary.filter(x=>!x.good);
    const allObjects=summary.reduce((n,x)=>n+x.features.length,0);
    document.getElementById("overallTitle").textContent=stale.length?"Live feed degraded":"Live feeds healthy";
    document.getElementById("overallText").textContent=stale.length?
      stale.map(x=>x.site+" stale").join(", ")+" • "+allObjects+" current objects":
      "KCXX/KTYX current object feeds • "+allObjects+" candidate objects • probability scoring disabled";
    document.getElementById("overallStatus").classList.toggle("degraded",stale.length>0);
    document.getElementById("subtitle").textContent="Last successful refresh: "+fmt(new Date().toISOString());
  }catch(err){
    document.getElementById("overallTitle").textContent="Live feed unavailable";
    document.getElementById("overallText").textContent=String(err);
    document.getElementById("overallStatus").classList.add("degraded");
  }
}

addRadarMarkers();
document.getElementById("refreshBtn").onclick=refresh;
refresh();
refreshTimer=setInterval(refresh,60000);
