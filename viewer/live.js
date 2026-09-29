const map=L.map("liveMap",{zoomControl:true,preferCanvas:true}).setView([44.15,-73.65],8);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:12,attribution:"© OpenStreetMap contributors"}).addTo(map);
const layers={KCXX:L.layerGroup().addTo(map),KTYX:L.layerGroup().addTo(map)};
const radarLocations={KCXX:[44.511,-73.166],KTYX:[43.756,-75.680]};
const LIVE_BASE="https://raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-live-data/viewer/data/live/";
let datasets={},selected=null,refreshTimer=null,hasInitialExtent=false;

const num=(v,d=1)=>v==null||Number.isNaN(Number(v))?"—":Number(v).toFixed(d);
const fmt=t=>t?new Date(t).toLocaleString(undefined,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit",second:"2-digit"}):"—";
const ageMinutes=t=>t?Math.max(0,(Date.now()-new Date(t).getTime())/60000):Infinity;
const esc=s=>String(s??"—").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
const ktFromMs=v=>v==null||Number.isNaN(Number(v))?null:Number(v)*1.943844492;
const cFromK=v=>v==null||Number.isNaN(Number(v))?null:Number(v)-273.15;
const url=name=>LIVE_BASE+name+"?cb="+Date.now();

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
  const [geo,state,history,health]=await Promise.all([
    fetch(feedUrl(site,"objects")).then(r=>r.ok?r.json():Promise.reject(new Error(site+" objects HTTP "+r.status))),
    fetch(feedUrl(site,"state")).then(r=>r.ok?r.json():Promise.reject(new Error(site+" state HTTP "+r.status))),
    fetchOptionalJson(feedUrl(site,"history"),[]),
    fetchOptionalJson(feedUrl(site,"health"),null)
  ]);
  return {geo,state,history,health};
}

function summarize(site,item){
  const {geo,state,history,health}=item;
  const features=geo.features||[];
  const last=state.last_scan_time_utc||geo.metadata?.scan_time_utc||geo.metadata?.last_scan_utc;
  const age=ageMinutes(last);
  const good=age<=30;
  return {site,features,state,geo,history,health,last,age,good};
}

function renderRadarCards(summary){
  document.getElementById("radarCards").innerHTML=summary.map(x=>{
    if(x.error){
      return "<div class='live-card'><h3>"+esc(x.site)+" <span class='chip'>ERROR</span></h3>"+
        "<div class='live-stat'><span>Feed</span><b>Unavailable</b></div>"+
        "<div class='live-stat'><span>Reason</span><b>"+esc(x.error)+"</b></div>"+
        "<div class='live-stat'><span>Probability</span><b>Disabled</b></div></div>";
    }
    const quality=x.good?"LIVE":"STALE";
    return "<div class='live-card'><h3>"+x.site+" <span class='chip'>"+quality+"</span></h3>"+
      "<div class='live-stat'><span>Last scan</span><b>"+esc(fmt(x.last))+"</b></div>"+
      "<div class='live-stat'><span>Age</span><b>"+(Number.isFinite(x.age)?num(x.age,1)+" min":"—")+"</b></div>"+
      "<div class='live-stat'><span>Objects</span><b>"+x.features.length+"</b></div>"+
      "<div class='live-stat'><span>History</span><b>"+x.history.length.toLocaleString()+" records</b></div>"+
      "<div class='live-stat'><span>Publish state</span><b>"+esc(x.health?.status||"unknown")+"</b></div>"+
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
  summary.filter(x=>!x.error).forEach(x=>{
    const grouped={};
    (x.history||[]).forEach(r=>{
      if(r.track_id==null||r.centroid_lat==null||r.centroid_lon==null)return;
      (grouped[String(r.track_id)]??=[]).push(r);
    });
    Object.values(grouped).forEach(rows=>{
      rows.sort((a,b)=>String(a.timestamp).localeCompare(String(b.timestamp)));
      const coords=rows.slice(-12).map(r=>[Number(r.centroid_lat),Number(r.centroid_lon)])
        .filter(v=>v.every(Number.isFinite));
      if(coords.length<2)return;
      const id=String(rows[0].track_id);
      const selectedTrack=selected&&selected.radar_site===x.site&&String(selected.track_id)===id;
      L.polyline(coords,{
        color:selectedTrack?"#ffffff":"#8795a3",
        weight:selectedTrack?4:2,
        opacity:selectedTrack?.9:.38,
        dashArray:selectedTrack?null:"4 5",
        interactive:false
      }).addTo(layers[x.site]);
    });
    (x.features||[]).forEach(f=>{
      const p=f.properties||{};
      const isSelected=selected&&selected.track_id===p.track_id&&selected.radar_site===p.radar_site;
      const layer=L.geoJSON(f,{style:{
        color:isSelected?"#ffffff":objectColor(p),
        fillColor:objectColor(p),
        fillOpacity:isSelected?.48:.24,
        weight:isSelected?3:2
      }}).addTo(layers[x.site]);
      layer.eachLayer(g=>{
        const b=g.getBounds?.();
        if(b&&b.isValid())bounds.push(b);
      });
      layer.bindTooltip(
        x.site+" • Track "+esc(p.track_id)+" • "+num(p.max_reflectivity_dbz)+" dBZ • "+num(p.motion_speed_kt)+" kt",
        {sticky:true}
      );
      layer.on("click",()=>selectObject({...p,radar_site:x.site}));
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
  const all=[];
  summary.filter(x=>!x.error).forEach(x=>(x.features||[]).forEach(f=>all.push({...f.properties,radar_site:x.site})));
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
    ["Surface gust","gust_ms",v=>num(ktFromMs(v),1)+" kt"]
  ];
  return "<div class='live-env-grid'>"+rows.map(([label,key,format])=>{
    const value=env[key];
    return "<div class='env-item'><span>"+label+"</span><b>"+(value==null?"—":format(value))+"</b></div>";
  }).join("")+"</div>";
}

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
  const envFields=env.fields||{};
  const envSource=env.source||p.environment_source||"—";
  const envStatus=p.environment_status||env.status||"—";
  document.getElementById("selectedSummary").innerHTML=
    "<div class='live-stat'><span>Radar</span><b>"+esc(p.radar_site)+"</b></div>"+
    "<div class='live-stat'><span>Track</span><b>"+esc(p.track_id)+"</b></div>"+
    "<div class='live-stat'><span>Time</span><b>"+esc(fmt(p.timestamp))+"</b></div>"+
    "<div class='live-stat'><span>Max Z</span><b>"+num(p.max_reflectivity_dbz)+" dBZ</b></div>"+
    "<div class='live-stat'><span>Mean Z</span><b>"+num(p.mean_reflectivity_dbz)+" dBZ</b></div>"+
    "<div class='live-stat'><span>Area</span><b>"+num(p.area_km2)+" km²</b></div>"+
    "<div class='live-stat'><span>Shape</span><b>"+num(p.length_km)+" × "+num(p.width_km)+" km</b></div>"+
    "<div class='live-stat'><span>Motion</span><b>"+num(p.motion_speed_kt)+" kt @ "+num(p.motion_direction_deg,0)+"°</b></div>"+
    "<div class='live-stat'><span>Age</span><b>"+(p.age_scans==null?"—":esc(p.age_scans+" scans"))+"</b></div>"+
    "<div class='live-stat'><span>Z trend</span><b>"+num(p.reflectivity_trend_dbz_per_hr)+" dBZ/hr</b></div>"+
    "<div class='live-stat'><span>Environment</span><b>"+esc(envSource)+" • "+esc(envStatus)+"</b></div>"+
    renderEnvironment(envFields)+
    "<div class='live-stat'><span>Data quality</span><b>"+esc(p.data_quality||"—")+"</b></div>";
  renderSelectedHistory(p);
}

async function refresh(){
  document.getElementById("overallTitle").textContent="Refreshing live feeds…";
  document.getElementById("overallText").textContent="Fetching latest persisted KCXX/KTYX objects and histories.";
  try{
    const sites=["KCXX","KTYX"];
    const results=await Promise.all(sites.map(async site=>{
      try{
        return summarize(site,await getFeed(site));
      }catch(err){
        return {site,error:String(err.message||err),features:[],history:[],state:{},geo:{},good:false};
      }
    }));
    const summary=results;
    datasets=Object.fromEntries(summary.map(x=>[x.site,x]));
    renderRadarCards(summary);
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
    document.getElementById("overallTitle").textContent=degraded.length?"Live feed degraded":"Live feeds healthy";
    document.getElementById("overallText").textContent=degraded.length?
      degraded.map(x=>x.site+" "+(x.error?"unavailable":"stale")).join(", ")+" • "+allObjects+" current objects":
      "KCXX/KTYX current object feeds • "+allObjects+" candidate objects • probability scoring disabled";
    document.getElementById("overallStatus").classList.toggle("degraded",degraded.length>0);
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
refreshTimer=setInterval(refresh,120000);
