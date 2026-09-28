const map=L.map("map",{zoomControl:true}).setView([44.2,-73.1],8);
const framesLayer=L.layerGroup().addTo(map),objectsLayer=L.layerGroup().addTo(map),tracksLayer=L.layerGroup().addTo(map);
let manifest,frames=[],frameBounds=null,featuresByTime={},playing=false,timer=null;const times=[];
const fmt=v=>v==null||Number.isNaN(Number(v))?"—":Number(v).toFixed(1);
const pct=v=>v==null||Number.isNaN(Number(v))?"Not scored":Number(v).toFixed(0)+"%";
const metricRows=p=>[
 ["Max Z",fmt(p.max_reflectivity_dbz)+" dBZ"],["Mean Z",fmt(p.mean_reflectivity_dbz)+" dBZ"],
 ["Area",fmt(p.area_km2)+" km²"],["Length",fmt(p.length_km)+" km"],["Width",fmt(p.width_km)+" km"],
 ["Aspect",fmt(p.aspect_ratio)],["Motion",fmt(p.motion_speed_kt)+" kt"],
 ["Direction",fmt(p.motion_direction_deg)+"°"],["Z trend",fmt(p.reflectivity_trend_dbz_per_hr)+" dBZ/hr"],
 ["Age",String(p.age_scans??"—")+" scans"],["Core",fmt(p.core_fraction*100)+"%"]
];
function popupHtml(p){
 const e=(p.environment||{}).fields||{};
 const envRows=[["SBCAPE",e.cape_jkg==null?"—":fmt(e.cape_jkg)+" J/kg"],["SBCIN",e.cin_jkg==null?"—":fmt(e.cin_jkg)+" J/kg"],["MLCAPE",e.mlcape_jkg==null?"—":fmt(e.mlcape_jkg)+" J/kg"],["MLCIN",e.mlcin_jkg==null?"—":fmt(e.mlcin_jkg)+" J/kg"],["MUCAPE",e.mucape_jkg==null?"—":fmt(e.mucape_jkg)+" J/kg"],["PWAT",e.pwat_mm==null?"—":fmt(e.pwat_mm)+" mm"],["0–1 km SRH",e.srh01_m2s2==null?"—":fmt(e.srh01_m2s2)+" m²/s²"],["0–3 km SRH",e.srh03_m2s2==null?"—":fmt(e.srh03_m2s2)+" m²/s²"],["0–6 km shear",e.shear_0_6km_ms==null?"—":fmt(e.shear_0_6km_ms)+" m/s"],["2 m RH",e.rh_2m_pct==null?"—":fmt(e.rh_2m_pct)+"%"],["Visibility",e.visibility_m==null?"—":fmt(e.visibility_m)+" m"],["10 m gust",e.gust_ms==null?"—":fmt(e.gust_ms)+" m/s"]];
 return '<div class="object-popup"><strong>Object '+p.track_id+'</strong>'+
 '<div class="popup-sub">'+new Date(p.timestamp).toLocaleString()+'</div>'+
 '<div class="popup-prob"><span>30-min probability</span><b>'+pct(p.probability_30min)+'</b></div>'+
 metricRows(p).map(x=>'<div class="popup-row"><span>'+x[0]+'</span><b>'+x[1]+'</b></div>').join('')+
 '<div class="popup-section-title">RAP ENVIRONMENT</div>'+envRows.map(x=>'<div class="popup-row"><span>'+x[0]+'</span><b>'+x[1]+'</b></div>').join('')+
 '<div class="popup-status">Environment: '+(p.environment_status||"not attached")+'<br>RAP valid: '+((p.environment||{}).source_valid_time_utc||"—")+'<br>RAP age: '+fmt((p.environment||{}).age_minutes)+' min<br>Model: '+(p.model_version||"—")+'</div></div>';
}
Promise.all([fetch("data/manifest.json").then(r=>r.json()),fetch("data/objects.geojson").then(r=>r.json()),fetch("data/frames.json").then(r=>r.json())]).then(([m,g,fd])=>{
 manifest=m;frames=fd.frames||[];frameBounds=fd.bounds;document.getElementById("subtitle").textContent=m.case_id+" • "+m.radar_site+" • "+m.scan_times_utc.length+" scans • "+m.track_ids.length+" tracks";
 g.features.forEach(x=>(featuresByTime[x.properties.timestamp]??=[]).push(x));times.push(...m.scan_times_utc);
 if(frameBounds)map.fitBounds(frameBounds,{padding:[20,20]});const s=document.getElementById("slider");s.max=Math.max(0,times.length-1);s.addEventListener("input",e=>render(+e.target.value));document.getElementById("play").onclick=toggle;render(0);
}).catch(e=>document.getElementById("subtitle").textContent="Viewer data not found: "+e);
function render(i){if(!times.length)return;const ts=times[i];document.getElementById("time").textContent=new Date(ts).toLocaleString()+" ("+ts+")";renderRadar(ts);renderObjects(ts)}
function renderRadar(ts){framesLayer.clearLayers();const f=frames.find(x=>x.timestamp===ts);if(!f||!frameBounds)return;L.imageOverlay("data/"+f.file,frameBounds,{opacity:.78,interactive:false}).addTo(framesLayer)}
function renderObjects(ts){
 objectsLayer.clearLayers();
 (featuresByTime[ts]||[]).forEach(f=>{
  const p=f.properties;
  const layer=L.geoJSON(f,{style:{color:"#39b5ff",fillOpacity:.25,weight:2,className:"object"}}).addTo(objectsLayer);
  layer.bindTooltip("Object "+p.track_id+" • "+fmt(p.max_reflectivity_dbz)+" dBZ • "+fmt(p.motion_speed_kt)+" kt",{sticky:true});
  layer.bindPopup(popupHtml(p),{maxWidth:330,closeButton:true});
  layer.on("mouseover",()=>showObject(f));
  layer.on("click",()=>showObject(f));
 });
 renderTracks(ts)
}
function renderTracks(ts){
 tracksLayer.clearLayers();const by={};
 Object.values(featuresByTime).flat().forEach(f=>{const p=f.properties;if(p.timestamp>ts)return;(by[p.track_id]??=[]).push(f)});
 Object.values(by).forEach(fs=>{fs.sort((a,b)=>a.properties.timestamp.localeCompare(b.properties.timestamp));if(fs.length>1)L.polyline(fs.map(f=>[f.properties.centroid_lat,f.properties.centroid_lon]),{color:"#9aa8b5",weight:3,opacity:.7}).addTo(tracksLayer)})
}
function showObject(f){
 const p=f.properties;
 document.getElementById("objectTitle").textContent="Track "+p.track_id+" • "+new Date(p.timestamp).toLocaleTimeString();
 document.getElementById("prob").textContent=pct(p.probability_30min);
 document.getElementById("metrics").innerHTML=metricRows(p).map(x=>'<div class="metric"><span>'+x[0]+'</span><b>'+x[1]+'</b></div>').join("");
 const e=(p.environment||{}).fields||{};
 document.getElementById("drivers").innerHTML='<div class="status-line">Radar diagnostics: <b>active</b></div><div class="status-line">Environment: <b>'+(p.environment_status||"not attached")+'</b></div><div class="status-line">RAP: <b>'+((p.environment||{}).source_valid_time_utc||"—")+'</b></div><div class="status-line">SBCAPE: <b>'+(e.cape_jkg==null?"—":fmt(e.cape_jkg)+" J/kg")+'</b></div><div class="status-line">MLCAPE: <b>'+(e.mlcape_jkg==null?"—":fmt(e.mlcape_jkg)+" J/kg")+'</b></div><div class="status-line">PWAT: <b>'+(e.pwat_mm==null?"—":fmt(e.pwat_mm)+" mm")+'</b></div><div class="status-line">0–6 km shear: <b>'+(e.shear_0_6km_ms==null?"—":fmt(e.shear_0_6km_ms)+" m/s")+'</b></div><div class="status-line">Probability: <b>'+pct(p.probability_30min)+'</b></div>';
}
function toggle(){playing=!playing;document.getElementById("play").textContent=playing?"❚❚ Pause":"▶ Play";if(playing)tick();else clearTimeout(timer)}
function tick(){if(!playing)return;const s=document.getElementById("slider");s.value=(+s.value+1)%times.length;render(+s.value);timer=setTimeout(tick,600)}
document.getElementById("popout").onclick=()=>window.open("probability.html","snowSquallProbability","width=1100,height=760");