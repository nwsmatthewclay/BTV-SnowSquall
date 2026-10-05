
(function(){
"use strict";

var map=L.map("liveMap",{zoomControl:true,preferCanvas:true}).setView([44.15,-73.65],8);
var radarPane=map.createPane("liveRadarPane");radarPane.style.zIndex=240;
var hitPane=map.createPane("liveHitPane");hitPane.style.zIndex=650;
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",{maxZoom:12,attribution:"Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"}).addTo(map);
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",{maxZoom:12,opacity:.78,attribution:"Labels © Esri"}).addTo(map);

var layers={KCXX:L.layerGroup().addTo(map),KTYX:L.layerGroup().addTo(map),labels:L.layerGroup().addTo(map),motion:L.layerGroup().addTo(map)};
var radarLayer=L.layerGroup().addTo(map),radarMosaic=null,radarMode="clean";
var radarLocations={KCXX:[44.511,-73.166],KTYX:[43.756,-75.680],KBTV:[44.472,-73.154]};
var BTV=[44.472,-73.154];
var datasets={},allObjects=[],selected=null,objectNumbers=true,refreshTimer=null;

var LIVE_BASE="https://raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-live-data/viewer/data/live/";
var SHADOW_BASE="https://raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-shadow-data/viewer/data/shadow/";

function q(id){return document.getElementById(id)}
function setText(id,v){var e=q(id);if(e)e.textContent=v==null?"—":v}
function num(v,d){if(d===undefined)d=1;var n=Number(v);return v==null||!Number.isFinite(n)?"—":n.toFixed(d)}
function esc(v){return String(v==null?"—":v).replace(/[&<>"']/g,function(m){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}})}
function fmtTime(t){return t?new Date(t).toLocaleString(undefined,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}):"—"}
function fmtUTC(t){return t?new Date(t).toISOString().replace("T"," ").replace(/\.\d{3}Z$/,"Z"):"—"}
function ageMinutes(t){return t?Math.max(0,(Date.now()-new Date(t).getTime())/60000):Infinity}
function msToKt(v){return v==null||!Number.isFinite(Number(v))?"—":Number(v)*1.943844492}
function kToC(v){return v==null||!Number.isFinite(Number(v))?"—":Number(v)-273.15}
function fieldValue(obj,key){if(!obj||obj[key]==null)return null;return obj[key]&&typeof obj[key]==="object"&&"value" in obj[key]?obj[key].value:obj[key]}
function fieldUnits(obj,key){return obj&&obj[key]&&typeof obj[key]==="object"?obj[key].units||"":""}
function envField(p,key){var e=p&&p.environment||{},f=e.fields||{};return fieldValue(f,key)??fieldValue(e,key)??p?.[key]}
function compass(deg){var d=Number(deg);if(!Number.isFinite(d))return "—";var names=["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];return names[Math.round(((d%360)+360)%360/22.5)%16]}
function haversineMi(lat,lon,lat2,lon2){var R=3958.7613,rad=Math.PI/180,p1=Number(lat)*rad,p2=Number(lat2)*rad,dp=(Number(lat2)-Number(lat))*rad,dl=(Number(lon2)-Number(lon))*rad,a=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;return R*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a))}
function shadowRecord(site,trackId){return datasets[site]?.shadow?.records?.find(function(r){return String(r.track_id)===String(trackId)})||null}
function shadowRows(site,trackId){return (datasets[site]?.shadowHistory||[]).filter(function(r){return String(r.track_id)===String(trackId)}).sort(function(a,b){return String(a.timestamp).localeCompare(String(b.timestamp))})}
function probValue(r,h){var v=r?.research_probabilities;if(!v)return null;return v[h]??v[String(h).replace("min","")]??null}
function riskScore(p){var s=shadowRecord(p.radar_site,p.track_id),v=probValue(s,"15");if(Number.isFinite(Number(v)))return Number(v);var rank=Number(p.candidate_rank_score);if(Number.isFinite(rank))return rank/100;var z=Number(p.max_reflectivity_dbz);if(z>=45)return .85;if(z>=35)return .62;if(z>=25)return .38;return .16}
function objectRisk(p){var s=riskScore(p);return s>=.70?"#ff4d3d":s>=.45?"#ff9a3c":s>=.25?"#efcd48":"#54b6ee"}
function objectOrdinal(p){var idx=allObjects.findIndex(function(x){return x.radar_site===p.radar_site&&String(x.track_id)===String(p.track_id)});return String(idx+1).padStart(2,"0")}
function latestForSelected(){
  if(!selected)return null;
  var x=allObjects.find(function(p){return p.radar_site===selected.radar_site&&String(p.track_id)===String(selected.track_id)});
  if(x)return x;
  var rows=shadowRows(selected.radar_site,selected.track_id);if(rows.length){var r=rows.at(-1);return Object.assign({},r,{radar_site:selected.radar_site})}
  return selected;
}
function trackHistory(p){
  var rows=datasets[p.radar_site]?.history||[];
  var res=rows.filter(function(r){return String(r.track_id)===String(p.track_id)}).sort(function(a,b){return String(a.timestamp).localeCompare(String(b.timestamp))});
  return res;
}
function durationText(rows){if(rows.length<2)return rows.length+" scan";var d=(new Date(rows.at(-1).timestamp)-new Date(rows[0].timestamp))/60000;return num(d,0)+" min"}
function currentHistoryRow(p){var rows=trackHistory(p);return rows.at(-1)||p}

function addStations(){
  Object.entries(radarLocations).forEach(function(entry){var site=entry[0],loc=entry[1];L.marker(loc,{icon:L.divIcon({className:"radar-station",iconSize:[12,12],iconAnchor:[6,6],html:""}),interactive:false,title:site}).addTo(map)});
}
function mosaicMetaUrl(){return LIVE_BASE+"radar_mosaic.json?cb="+Date.now()}
function mosaicImageUrl(mode){var product=radarMosaic?.display_products||{},name=mode==="raw"?(product.raw_image||"radar_mosaic_raw.png"):(product.clean_image||"radar_mosaic_clean.png");return LIVE_BASE+name+"?cb="+Date.now()}
function addNoaaFallback(){
  var u="https://mapservices.weather.noaa.gov/eventdriven/rest/services/radar/radar_base_reflectivity/MapServer/export?bbox=-76.91,41.86,-70.39,46.40&bboxSR=4326&imageSR=4326&size=1400,900&format=png32&transparent=true&f=image";
  L.imageOverlay(u,[[41.86,-76.91],[46.40,-70.39]],{pane:"liveRadarPane",opacity:.56,interactive:false,crossOrigin:true}).addTo(radarLayer);
}
async function renderRadarMosaic(){
  radarLayer.clearLayers();
  try{
    var response=await fetch(mosaicMetaUrl(),{cache:"no-store"});if(!response.ok)throw new Error(response.status);
    radarMosaic=await response.json();
  }catch(_){radarMosaic=null}
  if(!radarMosaic||radarMosaic.status!=="ready"||!radarMosaic.bounds){setText("radarStatus","Local mosaic unavailable • NOAA QC fallback");addNoaaFallback();return}
  var src=(radarMosaic.sources||[]).map(function(x){return x.radar}).filter(Boolean);setText("radarStatus","Mosaic READY • "+(src.join(" + ")||"KCXX + KTYX"));
  var ov=L.imageOverlay(mosaicImageUrl(radarMode),radarMosaic.bounds,{pane:"liveRadarPane",opacity:radarMode==="raw"?.66:.84,interactive:false,crossOrigin:true});ov.addTo(radarLayer);
  if(!map._sqExtent){map.fitBounds(radarMosaic.bounds,{padding:[25,25],maxZoom:8});map._sqExtent=true}
}
function setRadarMode(mode){radarMode=mode;document.querySelectorAll(".display-btn").forEach(function(b){b.classList.toggle("active",b.dataset.radarMode===mode)});renderRadarMosaic()}
function cellPoints(p){
  var lat=Number(p.centroid_lat),lon=Number(p.centroid_lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return [];
  var major=Number(p.length_km);if(!Number.isFinite(major)||major<=0)major=2;
  var minor=Number(p.width_km);if(!Number.isFinite(minor)||minor<=0)minor=Math.max(1,major*.45);
  var angle=(Number(p.orientation_deg)||0)*Math.PI/180,pts=[],n=16;
  for(var i=0;i<n;i++){var t=i/n*Math.PI*2,x=Math.min(35,Math.max(1.5,major))/2*Math.cos(t),y=Math.min(20,Math.max(.8,minor))/2*Math.sin(t),east=x*Math.cos(angle)-y*Math.sin(angle),north=x*Math.sin(angle)+y*Math.cos(angle);pts.push([lat+north/111,lon+east/(111*Math.max(.2,Math.cos(lat*Math.PI/180)))])}
  return pts;
}
function renderMap(){
  Object.values(layers).forEach(function(l){l.clearLayers()});
  if(!allObjects.length)return;
  allObjects.forEach(function(p){
    var c=objectRisk(p),sel=selected&&selected.radar_site===p.radar_site&&String(selected.track_id)===String(p.track_id),pts=cellPoints(p);if(pts.length<3)return;
    var poly=L.polygon(pts,{color:sel?"#fff":c,weight:sel?3:1.7,fillColor:c,fillOpacity:sel?.28:0,opacity:sel?1:.92,interactive:true,lineJoin:"round"}).addTo(layers[p.radar_site]);
    poly.bindTooltip("<b>OBJECT "+objectOrdinal(p)+"</b><br>"+p.radar_site+" • Track "+p.track_id+"<br>"+num(p.max_reflectivity_dbz)+" dBZ • "+num(p.area_km2)+" km²",{sticky:true});
    poly.on("click",function(){selectObject(p)});
    var hit=L.polygon(pts,{pane:"liveHitPane",color:"#fff",weight:12,opacity:.001,fillColor:"#fff",fillOpacity:.001,bubblingMouseEvents:false}).addTo(layers[p.radar_site]);hit.on("click",function(){selectObject(p)});
    var lat=Number(p.centroid_lat),lon=Number(p.centroid_lon);
    if(objectNumbers&&Number.isFinite(lat)&&Number.isFinite(lon))L.marker([lat,lon],{icon:L.divIcon({className:"sq-object-label-wrap",iconSize:null,iconAnchor:[0,0],html:"<div class='sq-object-label "+(sel?"":"dim")+"'>"+objectOrdinal(p)+"</div>"}),interactive:false}).addTo(layers.labels);
    var speed=Number(p.motion_speed_kt),dir=Number(p.motion_direction_deg??p.motion_dir_deg);
    if(Number.isFinite(speed)&&Number.isFinite(dir)&&speed<=75){var km=Math.max(5,Math.min(14,4+speed*.18)),br=dir*Math.PI/180,lat2=lat+km*Math.cos(br)/111,lon2=lon+km*Math.sin(br)/(111*Math.max(.2,Math.cos(lat*Math.PI/180)));L.polyline([[lat,lon],[lat2,lon2]],{color:sel?"#fff":"#d7e7ef",weight:sel?2.7:1.4,opacity:sel?.95:.72,interactive:false}).addTo(layers.motion);L.circleMarker([lat2,lon2],{radius:sel?4:2.5,color:sel?"#fff":"#d7e7ef",fillColor:"#fff",fillOpacity:.85,weight:0,interactive:false}).addTo(layers.motion)}
  });
}
function renderInventory(){
  var box=q("objectPicker");setText("objectCount",allObjects.length+" active");
  if(!allObjects.length){box.innerHTML="<div class='history-empty'>No current radar objects are available.</div>";return}
  box.innerHTML=allObjects.slice(0,24).map(function(p){var c=objectRisk(p),sel=selected&&selected.radar_site===p.radar_site&&String(selected.track_id)===String(p.track_id);return "<button type='button' class='object-pick "+(sel?"active":"")+"' data-id='"+esc(p.radar_site+"|"+p.track_id)+"'><b><span class='risk-dot' style='background:"+c+"'></span>OBJECT "+objectOrdinal(p)+"</b><span>"+p.radar_site+" • "+num(p.max_reflectivity_dbz,0)+" dBZ • "+num(p.motion_speed_kt,0)+" kt</span></button>"}).join("");
  box.querySelectorAll("[data-id]").forEach(function(btn){btn.onclick=function(){var s=btn.dataset.id.split("|");var p=allObjects.find(function(x){return x.radar_site===s[0]&&String(x.track_id)===s[1]});if(p)selectObject(p)}});
}
function selectDefault(){if(selected&&allObjects.some(function(p){return p.radar_site===selected.radar_site&&String(p.track_id)===String(selected.track_id)}))return;var sorted=allObjects.slice().sort(function(a,b){var d=riskScore(b)-riskScore(a);return d||Number(b.max_reflectivity_dbz||0)-Number(a.max_reflectivity_dbz||0)});selected=sorted[0]||null}
function renderObjectCard(){
  var p=latestForSelected();if(!p){setText("objectTitle","OBJECT —");setText("objectSubtitle","No current object selected.");setText("objectBadge","NO SELECTION");q("objectAccent").style.background="#526776";return}
  var rows=trackHistory(p),last=rows.at(-1)||p,first=rows[0]||p,dist=haversineMi(p.centroid_lat,p.centroid_lon,BTV[0],BTV[1]),speed=Number(p.motion_speed_kt),dir=Number(p.motion_direction_deg??p.motion_dir_deg),age=Number(p.age_scans),ageMin=Number(p.track_age_min);
  q("objectAccent").style.background=objectRisk(p);
  setText("objectTitle","OBJECT "+objectOrdinal(p));
  setText("objectSubtitle",p.radar_site+" • Track "+p.track_id);
  setText("objectTime",fmtTime(p.timestamp)+" • "+fmtUTC(p.timestamp));
  var z=Number(p.max_reflectivity_dbz);setText("objectBadge",riskScore(p)>=.70?"ELEVATED":riskScore(p)>=.45?"WATCH":"CANDIDATE");
  setText("objectTrack",p.radar_site+" • "+p.track_id);
  setText("objectLatLon",num(p.centroid_lat,2)+"°N / "+num(Math.abs(Number(p.centroid_lon)),2)+"°W");
  setText("objectMotion",Number.isFinite(speed)?Math.round(speed)+" kt • "+num(dir,0)+"° ("+compass(dir)+")":"Motion —");
  setText("objectDistance",Number.isFinite(dist)?num(dist,0)+" mi":"—");
  setText("objectAge",Number.isFinite(ageMin)?num(ageMin,0)+" min • "+(Number.isFinite(age)?age+" scans":"—"):Number.isFinite(age)?age+" scans":"< 1 scan");
  setText("objectDuration",durationText(rows));
  setText("objectQuality",p.track_quality||p.data_quality||"—");
  setText("objectDataQuality",p.data_quality||"good");
}
function renderProbability(){
  var p=latestForSelected();if(!p){return}
  var shadow=shadowRecord(p.radar_site,p.track_id),hist=shadowRows(p.radar_site,p.track_id),score=probValue(shadow,15),prev=hist.length>1?probValue(hist.at(-2),15):null;
  if(score==null){
    q("probabilityValue").classList.add("na");setText("probabilityValue","—");setText("probabilityDelta","GATED • waiting for coverage");q("probabilityDelta").className="prob-delta flat";
    var cov=shadow?.feature_coverage?.["15"]?.fraction;setText("probabilityNote",cov==null?"No live research score is attached to this object yet.":("Feature coverage "+(Number(cov)*100).toFixed(0)+"% • candidate threshold 80% • probability remains gated."));
  }else{
    q("probabilityValue").classList.remove("na");setText("probabilityValue",(Number(score)*100).toFixed(0)+"%");
    var d=prev==null?null:Number(score)-Number(prev);
    setText("probabilityDelta",d==null?"Score attached":(d>=0?"▲ +":"▼ ")+(Math.abs(d)*100).toFixed(1)+" pp");
    q("probabilityDelta").className="prob-delta "+(d==null?"flat":d>=0?"up":"down");
    setText("probabilityNote","Each radar scan is rescored from its own causal feature state. The 15/30/45/60 curves show what the model was expecting from that scan onward • candidate only.");
  }
  var vals=[["Model",score,"#1f90e9"],["Analog",shadow?.analog_probability,"#f0c54c"],["Environment",shadow?.environment_signal,"#62ce73"],["Overall",shadow?.ensemble_probability,"#ff5648"]];
  q("probComponents").innerHTML=vals.map(function(x){return "<div class='prob-component'><span><i class='comp-dot' style='background:"+x[2]+"'></i>"+x[0]+"</span><b>"+(x[1]==null?"—":(Number(x[1])*100).toFixed(0)+"%")+"</b></div>"}).join("")+"<div style='margin-top:5px;font-size:8px;color:#748a9b'>The timeline below is the selected track, scan by scan; it is not a time series of the same frozen probability.</div>";
  var scored=hist.filter(function(r){return Object.values(r.research_probabilities||{}).some(function(v){return Number.isFinite(Number(v))})});
  var peak=scored.reduce(function(best,r){var v=probValue(r,15);return v!=null&&(best==null||v>best.v)?{v:v,ts:r.timestamp}:best},null);
  var age=shadow?.track_age_min;
  var peakText=peak?(Number(peak.v)*100).toFixed(0)+"% peak 15m":"—";
  setText("probabilitySummary",(age!=null?num(age,0)+" min track":"Track duration unavailable")+" • "+scored.length+" scored scans • current "+(score==null?"—":(Number(score)*100).toFixed(0)+"%")+" • "+peakText);
  renderProbabilityChart(hist);
  renderEnvironmentOutlook(p,hist);
}

function renderProbabilityChart(hist){
  var svg=q("probChart");if(!svg)return;svg.innerHTML="";
  var rows=hist.filter(function(r){return Object.values(r.research_probabilities||{}).some(function(v){return Number.isFinite(Number(v))})});
  if(!rows.length){
    svg.setAttribute("viewBox","0 0 520 190");
    svg.innerHTML="<text x='260' y='92' text-anchor='middle' class='chart-text'>Probability history will populate as each scan is rescored</text>";
    return;
  }
  var W=520,H=190,L=38,R=10,T=18,B=28,PLOTW=W-L-R, PLOTH=H-T-B;
  var ageOf=function(r,i){var n=Number(r.track_age_min);return Number.isFinite(n)?n:i*5};
  var ages=rows.map(ageOf),maxAge=Math.max(5,ages[ages.length-1]||0);
  var x=function(i){return L+(rows.length===1?PLOTW/2:i*(PLOTW)/(rows.length-1))};
  var y=function(v){return T+(1-Math.max(0,Math.min(1,Number(v)||0)))*PLOTH};
  for(var g=0;g<=4;g++){
    var pct=g*25,yy=y(pct/100);
    svg.innerHTML+="<line x1='"+L+"' y1='"+yy.toFixed(1)+"' x2='"+(W-R)+"' y2='"+yy.toFixed(1)+"' class='chart-gridline'/>";
    svg.innerHTML+="<text x='"+(L-6)+"' y='"+(yy+3).toFixed(1)+"' text-anchor='end' class='chart-text'>"+pct+"%</text>";
  }
  [0,maxAge].forEach(function(a,i){
    var xx=i?W-R:L;svg.innerHTML+="<text x='"+xx+"' y='"+(H-7)+"' text-anchor='"+(i?"end":"start")+"' class='chart-text'>"+num(a,0)+" min</text>";
  });
  svg.innerHTML+="<line x1='"+L+"' y1='"+(H-B)+"' x2='"+(W-R)+"' y2='"+(H-B)+"' class='chart-axis'/>";
  var cls=["chart-line-15","chart-line-30","chart-line-45","chart-line-60"];
  for(var j=0;j<4;j++){
    var valid=rows.map(function(r,i){var v=probValue(r,String([15,30,45,60][j]));return {i:i,v:v}}).filter(function(pt){return Number.isFinite(Number(pt.v))});
    if(!valid.length)continue;
    var path=valid.map(function(pt,n){return (n?"L":"M")+x(pt.i).toFixed(1)+" "+y(pt.v).toFixed(1)}).join(" ");
    svg.innerHTML+="<path d='"+path+"' class='chart-path "+cls[j]+"' />";
    valid.forEach(function(pt){
      var rr=rows[pt.i],title="Scan "+fmtTime(rr.timestamp)+" • age "+num(ageOf(rr,pt.i),0)+" min • "+[15,30,45,60][j]+"m "+(Number(pt.v)*100).toFixed(1)+"%";
      svg.innerHTML+="<circle cx='"+x(pt.i).toFixed(1)+"' cy='"+y(pt.v).toFixed(1)+"' r='2.8' class='prob-point "+cls[j]+"'><title>"+esc(title)+"</title></circle>";
    });
  }
  var latestX=x(rows.length-1);
  svg.innerHTML+="<line x1='"+latestX.toFixed(1)+"' y1='"+T+"' x2='"+latestX.toFixed(1)+"' y2='"+(H-B)+"' class='chart-current'/>";
  svg.innerHTML+="<text x='"+latestX.toFixed(1)+"' y='"+(T-5)+"' text-anchor='middle' class='chart-text'>CURRENT</text>";
}

function renderEnvironmentOutlook(p,hist){
  var box=q("environmentOutlook");if(!box)return;
  var shadowRowsForTrack=hist.slice().reverse();
  var currentShadow=shadowRowsForTrack.find(function(r){return r.environment_snapshot})||null;
  var snap=currentShadow?.environment_snapshot||{};
  var forecast=currentShadow?.environment_forecast_30min_snapshot||{};
  var fallback=function(key){var v=p[key];return v==null?null:Number(v)};
  var current=function(key){var v=snap[key];return v==null?fallback(key):Number(v)};
  var defs=[
    ["SNSQ","snsq","",2],
    ["MUCAPE","mucape_jkg","J/kg",0],
    ["0–6 km shear","shear_0_6km_kt","kt",0],
    ["0–1 km SRH","srh01_m2s2","m²/s²",0],
    ["PWAT","pwat_mm","mm",1],
    ["RH 0–2 km","mean_rh_0_2km_pct","%",0]
  ];
  var out=defs.map(function(d){
    var now=current(d[1]),later=forecast[d[1]];
    if(later==null && p["expected_30min_"+d[1]]!=null)later=Number(p["expected_30min_"+d[1]]);
    var delta=(now!=null&&later!=null)?Number(later)-Number(now):null;
    var arrow=delta==null?"→":Math.abs(delta)<(d[1]==="snsq"?.05:.5)?"→":delta>0?"↑":"↓";
    var value=function(v){return v==null?"—":(d[1]==="snsq"?num(v,2):num(v,d[3]))+(d[2]?" "+d[2]:"")};
    return "<div class='env-outlook-tile'><span>"+d[0]+"</span><b>"+value(now)+"</b><i>"+arrow+" "+(later==null?"no +30m value":value(later))+"</i></div>";
  }).join("");
  box.innerHTML=out||"<div class='history-empty'>Environmental trajectory unavailable.</div>";
}
function renderKeyTrends(){
  var p=latestForSelected();if(!p){q("keyTrends").innerHTML="";return}var rows=trackHistory(p),first=rows[0]||p;
  var delta=function(a,b){var x=Number(a),y=Number(b);return Number.isFinite(x)&&Number.isFinite(y)?x-y:null}
  var items=[["MAX REFLECTIVITY",num(p.max_reflectivity_dbz,0)+" dBZ",delta(p.max_reflectivity_dbz,first.max_reflectivity_dbz),"dBZ"],["OBJECT AREA",num(p.area_km2,0)+" km²",delta(p.area_km2,first.area_km2),"km²"],["MOTION SPEED",num(p.motion_speed_kt,0)+" kt",delta(p.motion_speed_kt,first.motion_speed_kt),"kt"],["FEATURE COVERAGE",shadowRecord(p.radar_site,p.track_id)?.feature_coverage?.["15"]?.fraction==null?"—":(Number(shadowRecord(p.radar_site,p.track_id).feature_coverage["15"].fraction)*100).toFixed(0)+"%",null,""]];
  q("keyTrends").innerHTML=items.map(function(x){var d=x[2];return "<div class='trend-tile'><div class='label'>"+x[0]+"</div><div class='value'>"+x[1]+"</div><div class='delta "+(d==null?"neutral":"")+"'>"+(d==null?"Live snapshot":(d>=0?"▲ +":"▼ ")+Math.abs(d).toFixed(0)+" "+x[3])+"</div></div>"}).join("");
}
function fmtLiveEnv(v,key){if(v==null)return "—";if(key.indexOf("cape")>=0||key.indexOf("cin")>=0||key==="dcape_jkg")return num(v,0);if(key==="srh01_m2s2"||key.indexOf("shear")>=0&&key!=="shear_0_6km_ms")return num(v,0);return num(v,1)}
function renderEnvironment(){
  var p=latestForSelected();if(!p){q("environmentTable").innerHTML="";return}
  var fields=[
    ["SBCAPE","cape_jkg"],["MLCAPE","mlcape_jkg"],["MUCAPE","mucape_jkg"],["MLCIN","mlcin_jkg"],["DCAPE","dcape_jkg"],["PWAT","pwat_mm"],["LCL","lcl_m"],["0–1 km SRH","srh01_m2s2"],["0–6 km shear","shear_0_6km_ms"],["2 m temp","temperature_2m_k"],["2 m dewpoint","dewpoint_2m_k"],["Surface gust","gust_ms"],["SNSQ","snsq"],["SNSQ 0–2 km RH","mean_rh_0_2km_pct"],["SNSQ Δθe 0–2 km","thetae_delta_0_2km_k"],["SNSQ 0–2 km wind","mean_wind_0_2km_ms"],["2 m wet-bulb","wetbulb_2m_c"]
  ];
  var rows=trackHistory(p),current=p,prev=rows.length>1?rows[Math.max(0,rows.length-2)]:null,next=null;
  var header="<thead><tr><th>Parameter</th><th>−30 min</th><th>Current</th><th>Next scan</th></tr></thead><tbody>";
  header+=fields.map(function(x){
    var pv=prev?envField(prev,x[1]):null,cv=envField(current,x[1]),nv=null;
    var format=function(val,key){if(val==null)return "—";if(key==="temperature_2m_k"||key==="dewpoint_2m_k")return num(kToC(val),1)+" °C";if(key==="gust_ms"||key==="shear_0_6km_ms"||key==="mean_wind_0_2km_ms")return num(msToKt(val),0)+" kt";return fmtLiveEnv(val,key)};
    return "<tr><td>"+x[0]+"</td><td class='ctx-prev'>"+format(pv,x[1])+"</td><td class='ctx-current'>"+format(cv,x[1])+"</td><td class='ctx-next ctx-na'>—</td></tr>";
  }).join("");
  q("environmentTable").innerHTML=header+"</tbody>";
  var e=p.environment||{};setText("envSource",(e.source||p.environment_source||"RAP")+(e.age_minutes==null?"":" • "+num(e.age_minutes,0)+" min"));
}
function evidenceItem(icon,cls,title,body){return "<div class='evidence-card'><div class='evidence-icon "+(cls||"")+"'>"+icon+"</div><div><b>"+title+"</b><span>"+body+"</span></div></div>"}
function renderEvidence(){
  var p=latestForSelected();if(!p){q("evidenceGrid").innerHTML="";return}
  var e=p.environment||{},f=e.fields||{},vis=fieldValue(f,"visibility_m")??fieldValue(e,"visibility_m")??p.visibility_m,gust=fieldValue(f,"gust_ms")??fieldValue(e,"gust_ms")??p.gust_ms,geo=datasets[p.radar_site]?.geo,fields=geo?.metadata?.fields||{};
  var mping=p.mping_reports||p.mping_count||p.mping_support,shadow=shadowRecord(p.radar_site,p.track_id),cov=shadow?.feature_coverage?.["15"]?.fraction;
  q("evidenceGrid").innerHTML=
    evidenceItem(vis!=null?"✓":"—",vis!=null?"":"warn","METAR / ASOS context",vis!=null?"Visibility "+num(vis/1609.344,1)+" mi"+(gust!=null?" • gust "+num(msToKt(gust),0)+" kt":""):"Surface observation not attached to this object")+
    evidenceItem(mping?"✓":"—",mping?"":"warn","MPING reports",mping?(String(mping)+" attached report(s)"):"No MPING report field in current live object")+
    evidenceItem(cov!=null&&cov>=.8?"✓":"!",cov!=null&&cov>=.8?"":"warn","Model feature coverage",cov==null?"No candidate score package attached":(Number(cov)*100).toFixed(0)+"% of 15-min predictors available • target ≥80%")+
    evidenceItem(fields.velocity?"✓":"!",fields.velocity?"":"warn","Radar inputs",fields.velocity?"Base velocity present • dual-pol fields tracked": "Radar velocity field not confirmed in feed metadata");
}
function renderHistory(){
  var p=latestForSelected(),rows=p?trackHistory(p):[];setText("historyCount",rows.length+" retained scans");if(!rows.length){q("historyChart").innerHTML="<text x='260' y='70' text-anchor='middle' class='chart-text'>No retained track history</text>";q("historyTable").innerHTML="";return}
  var W=520,H=145,P=28,vals=rows.map(function(r){return {z:Number(r.max_reflectivity_dbz),a:Number(r.area_km2),m:Number(r.motion_speed_kt)}}),z=vals.map(x=>x.z).filter(Number.isFinite),a=vals.map(x=>x.a).filter(Number.isFinite),m=vals.map(x=>x.m).filter(Number.isFinite),minZ=z.length?Math.min(...z):0,maxZ=z.length?Math.max(...z):1,minA=a.length?Math.min(...a):0,maxA=a.length?Math.max(...a):1,minM=m.length?Math.min(...m):0,maxM=m.length?Math.max(...m):1;
  var norm=function(v,min,max){return Number.isFinite(v)?(v-min)/(Math.max(.001,max-min)):null};var x=function(i){return P+(rows.length===1?0:i*(W-2*P)/(rows.length-1))},y=function(v){return H-P-v*(H-2*P)},svg="<line x1='"+P+"' y1='"+(H-P)+"' x2='"+(W-P)+"' y2='"+(H-P)+"' class='chart-axis'/><text x='3' y='12' class='chart-text'>100</text><text x='7' y='"+(H/2+3)+"' class='chart-text'>50</text><text x='7' y='"+(H-P+3)+"' class='chart-text'>0</text>";
  [["max_reflectivity_dbz","#d34bc0",minZ,maxZ,"z"],["area_km2","#1f90e9",minA,maxA,"a"],["motion_speed_kt","#54c56b",minM,maxM,"m"]].forEach(function(line){var path=rows.map(function(r,i){var key=line[4],val=norm(Number(r[key]),line[2],line[3]);return val==null?null:(i?"L":"M")+x(i).toFixed(1)+" "+y(val).toFixed(1)}).filter(Boolean).join(" ");if(path)svg+="<path d='"+path+"' fill='none' stroke='"+line[1]+"' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'/>"});
  var xx=x(rows.length-1);svg+="<line x1='"+xx+"' y1='"+P+"' x2='"+xx+"' y2='"+(H-P)+"' class='chart-current'/>";q("historyChart").innerHTML=svg+"<text x='"+P+"' y='"+(H-2)+"' class='chart-text'>"+fmtTime(rows[0].timestamp)+"</text><text x='"+(W-P)+"' y='"+(H-2)+"' text-anchor='end' class='chart-text'>"+fmtTime(rows.at(-1).timestamp)+"</text>";
  var probByKey={};shadowRows(p.radar_site,p.track_id).forEach(function(s){probByKey[String(s.timestamp)]=s.research_probabilities||{}});
   q("historyTable").innerHTML="<thead><tr><th>Time</th><th>15m</th><th>30m</th><th>45m</th><th>60m</th><th>Max Z</th><th>Area</th><th>L × W</th><th>Motion</th><th>Z trend</th><th>Env</th></tr></thead><tbody>"+rows.slice(-60).reverse().map(function(r){
     var cur=p&&String(r.timestamp)===String(p.timestamp),pv=probByKey[String(r.timestamp)]||{};
     var pf=function(v){return Number.isFinite(Number(v))?(Number(v)*100).toFixed(0)+"%":"—"};
     return "<tr class='"+(cur?"current":"")+"' data-ts='"+esc(r.timestamp)+"'><td>"+fmtTime(r.timestamp)+"</td><td>"+pf(pv["15"]??pv["15min"])+"</td><td>"+pf(pv["30"]??pv["30min"])+"</td><td>"+pf(pv["45"]??pv["45min"])+"</td><td>"+pf(pv["60"]??pv["60min"])+"</td><td>"+num(r.max_reflectivity_dbz,0)+" dBZ</td><td>"+num(r.area_km2,0)+" km²</td><td>"+num(r.length_km,1)+" × "+num(r.width_km,1)+" km</td><td>"+num(r.motion_speed_kt,0)+" kt</td><td>"+num(r.reflectivity_trend_dbz_per_hr,1)+"</td><td>"+esc(r.environment_status||"—")+"</td></tr>"}).join("")+"</tbody>";
}
function renderModelStatus(){
  var rows=Object.values(datasets).filter(function(x){return x.shadow}).map(function(x){var s=x.shadow;return {site:x.site,scored:s.scored_object_count||0,total:s.current_object_count||0,status:s.operational_release_status||"unknown"}});
  var selectedShadow=selected?shadowRecord(selected.radar_site,selected.track_id):null,cov=selectedShadow?.feature_coverage?.["15"]?.fraction;
  setText("modelStatus",cov==null?"GATED":(cov>=.8?"CANDIDATE READY":"GATED"));
  q("modelStatusCard").innerHTML=rows.map(function(r){return "<div class='status-cell'><span>"+r.site+" shadow</span><b>"+r.scored+" / "+r.total+" scored</b></div>"}).join("")+
    "<div class='status-cell'><span>15-min coverage</span><b>"+(cov==null?"—":(Number(cov)*100).toFixed(0)+"%")+"</b></div>"+
    "<div class='status-cell'><span>Release</span><b>Candidate only</b></div>";
  q("liveGate").style.display="flex";
  setText("liveGateText",cov==null?"Research shadow data are not attached to this object yet.":(Number(cov)*100).toFixed(0)+"% 15-min feature coverage for selected object; probability stays gated below the 80% candidate threshold.");
}
async function fetchOptional(url,fallback){try{var r=await fetch(url,{cache:"no-store"});if(!r.ok)return fallback;return await r.json()}catch(_){return fallback}}
async function getSite(site){
  var base=LIVE_BASE;
  var results=await Promise.all([
    fetch(base+site+"_objects.geojson?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw new Error(site+" objects HTTP "+r.status);return r.json()}),
    fetch(base+site+"_state.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw new Error(site+" state HTTP "+r.status);return r.json()}),
    fetchOptional(base+site+"_history.json?cb="+Date.now(),[]),
    fetchOptional(base+site+"_health.json?cb="+Date.now(),null),
    fetchOptional(SHADOW_BASE+site+"_shadow.json?cb="+Date.now(),null),
    fetchOptional(SHADOW_BASE+site+"_shadow_history.json?cb="+Date.now(),[])
  ]);
  return {site:site,geo:results[0],state:results[1],history:results[2],health:results[3],shadow:results[4],shadowHistory:results[5]};
}
async function refresh(){
  setText("feedSummary","Refreshing KCXX + KTYX…");
  try{
    var got=await Promise.all(["KCXX","KTYX"].map(function(site){return getSite(site).catch(function(e){return {site:site,error:String(e.message||e),geo:{features:[]},state:{},history:[],shadow:null}})}));
    datasets=Object.fromEntries(got.map(function(x){return [x.site,x]}));
    allObjects=got.flatMap(function(x){return (x.geo.features||[]).map(function(f){return Object.assign({},f.properties,{radar_site:x.site})})});
    allObjects.sort(function(a,b){var d=riskScore(b)-riskScore(a);return d||Number(b.max_reflectivity_dbz||0)-Number(a.max_reflectivity_dbz||0)});
    selectDefault();
    await renderRadarMosaic();
    renderMap();renderInventory();renderObjectCard();renderProbability();renderKeyTrends();renderEnvironment();renderEvidence();renderHistory();renderModelStatus();
    var latest=got.map(function(x){return x.state?.last_scan_time_utc||x.geo?.metadata?.scan_time_utc}).filter(Boolean).sort().at(-1);
    setText("liveTime",latest?fmtTime(latest)+" • "+fmtUTC(latest):"No scan time available");
    setText("mapScanLabel",latest?fmtTime(latest):"No live radar");
    setText("feedSummary",(allObjects.length)+" active objects • "+got.map(function(x){return x.site+" "+(x.error?"OFFLINE":(ageMinutes(x.state?.last_scan_time_utc)<=30?"LIVE":"STALE"))}).join(" • "));
    var degraded=got.filter(function(x){return x.error||ageMinutes(x.state?.last_scan_time_utc)>30}).length>0;
    q("liveBadge").classList.toggle("gated",degraded);if(degraded)setText("liveBadge","DEGRADED");
  }catch(e){setText("feedSummary","Live feed error: "+e.message);q("liveBadge").classList.add("gated");setText("liveBadge","DEGRADED")}
}
document.querySelectorAll(".display-btn").forEach(function(b){b.onclick=function(){setRadarMode(b.dataset.radarMode)}});
document.querySelectorAll("[data-jump]").forEach(function(btn){btn.onclick=function(){var el=q(btn.dataset.jump);if(el)el.scrollIntoView({behavior:"smooth",block:"start"});document.querySelectorAll("[data-jump]").forEach(function(b){b.classList.toggle("active",b===btn)})}});
q("refreshBtn").onclick=refresh;q("refreshBtn2").onclick=refresh;q("objectNumbersBtn").onclick=function(){objectNumbers=!objectNumbers;q("objectNumbersBtn").classList.toggle("active",objectNumbers);renderMap()};
addStations();refresh();refreshTimer=setInterval(refresh,60000);
})();
