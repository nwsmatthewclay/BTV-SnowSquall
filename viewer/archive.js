
(function(){
"use strict";

var map=L.map("map",{zoomControl:true,preferCanvas:true}).setView([44.2,-73.1],8);
var objectHitPane=map.createPane("objectHitPane");
objectHitPane.style.zIndex=650;
var radarPane=map.createPane("archiveRadarPane");
radarPane.style.zIndex=240;

var imagery=L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",{
  maxZoom:12,attribution:"Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
}).addTo(map);
var ref=L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",{
  maxZoom:12,opacity:.75,attribution:"Labels © Esri"
}).addTo(map);

var radarLayer=L.layerGroup().addTo(map);
var objectsLayer=L.layerGroup().addTo(map);
var motionLayer=L.layerGroup().addTo(map);
var labelLayer=L.layerGroup().addTo(map);

var radarLocations={KCXX:[44.511,-73.166],KTYX:[43.756,-75.680],KBTV:[44.472,-73.154]};
var BTV=[44.472,-73.154];
var catalog=null,current=null,features=[],times=[],currentIndex=0,selectedKey=null,playing=false,timer=null,objectNumbers=true;

function q(id){return document.getElementById(id)}
function setText(id,v){var e=q(id);if(e)e.textContent=v==null?"—":v}
function num(v,d){if(d===undefined)d=1;var n=Number(v);return v==null||!Number.isFinite(n)?"—":n.toFixed(d)}
function esc(v){return String(v==null?"—":v).replace(/[&<>"']/g,function(m){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]})}
function fmtTime(t){return t?new Date(t).toLocaleString(undefined,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}):"—"}
function fmtUTC(t){return t?new Date(t).toISOString().replace("T"," ").replace(/\.\d{3}Z$/,"Z"):"—"}
function kmToMi(k){return Number.isFinite(Number(k))?Number(k)*.621371:"—"}
function msToKt(v){return v==null||!Number.isFinite(Number(v))?"—":Number(v)*1.943844492}
function kToC(v){return v==null||!Number.isFinite(Number(v))?"—":Number(v)-273.15}
function fieldValue(obj,key){if(!obj||obj[key]==null)return null;return obj[key]&&typeof obj[key]==="object"&&"value" in obj[key]?obj[key].value:obj[key]}
function fieldUnits(obj,key){return obj&&obj[key]&&typeof obj[key]==="object"?obj[key].units||"":""}
function envValue(p,key){return fieldValue(p&&p.environment,key)}
function probValue(p,key){var v=p&&p.research_probabilities; if(!v)return null; return v[key]??v[key.replace("min","")]??v[key.replace("m","")];}
function probabilityFor(p,h){var v=probValue(p,h); if(v==null)v=probValue(p,h.replace("min","m")); if(v==null)v=p&&p["probability_"+h]; return v==null?null:Number(v)}
function rankValue(p){var candidates=[p&&p.candidate_rank_score,p&&p.rank_score,p&&p.object_rank_score];for(var i=0;i<candidates.length;i++){if(Number.isFinite(Number(candidates[i])))return Number(candidates[i])}return null}
function compass(deg){var d=Number(deg);if(!Number.isFinite(d))return "—";var names=["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];return names[Math.round(((d%360)+360)%360/22.5)%16]}
function haversineMi(lat,lon,lat2,lon2){var R=3958.7613,rad=Math.PI/180;var p1=Number(lat)*rad,p2=Number(lat2)*rad;var dp=(Number(lat2)-Number(lat))*rad,dl=(Number(lon2)-Number(lon))*rad;var a=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;return R*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a))}
function formatProb(v){return Number.isFinite(Number(v))?(Number(v)*100).toFixed(0)+"%":"—"}
function objectRisk(p){var score=probabilityFor(p,"15min");if(Number.isFinite(score)){if(score>=.70)return "#ff4d3d";if(score>=.45)return "#ff9a3c";if(score>=.25)return "#efcd48";return "#54b6ee"}var z=Number(p&&p.max_reflectivity_dbz);if(z>=45)return "#ff4d3d";if(z>=35)return "#ff9a3c";if(z>=25)return "#efcd48";return "#54b6ee"}

function addRadarMarker(){
  map.eachLayer(function(l){if(l.options&&l.options.className==="radar-station")map.removeLayer(l)});
  var loc=radarLocations[current&&current.radar_site];
  if(!loc)return;
  L.marker(loc,{icon:L.divIcon({className:"radar-station",iconSize:[12,12],iconAnchor:[6,6],html:""}),interactive:false,title:current.radar_site}).addTo(map);
}
function fitToCase(){
  if(current&&current.radar_bounds){map.fitBounds(current.radar_bounds,{padding:[30,30],maxZoom:8});return}
  var pts=features.map(function(f){return [Number(f.properties.centroid_lat),Number(f.properties.centroid_lon)]}).filter(function(x){return x.every(Number.isFinite)});
  if(pts.length)map.fitBounds(L.latLngBounds(pts),{padding:[35,35],maxZoom:9});
}
function cellPoints(p){
  var lat=Number(p.centroid_lat),lon=Number(p.centroid_lon); if(!Number.isFinite(lat)||!Number.isFinite(lon))return [];
  var major=Number(p.shape_major_km);if(!Number.isFinite(major)||major<=0)major=Number(p.length_km);if(!Number.isFinite(major)||major<=0){var a=Number(p.area_km2);major=Number.isFinite(a)?Math.max(1.5,Math.sqrt(a*1.8)):2}
  var minor=Number(p.shape_minor_km);if(!Number.isFinite(minor)||minor<=0)minor=Number(p.width_km);if(!Number.isFinite(minor)||minor<=0)minor=Math.max(1,major*.45);
  var angle=(Number(p.orientation_deg)||0)*Math.PI/180;var pts=[],n=16;
  for(var i=0;i<n;i++){var t=i/n*Math.PI*2,x=Math.min(35,Math.max(1.5,major))/2*Math.cos(t),y=Math.min(20,Math.max(.8,minor))/2*Math.sin(t),east=x*Math.cos(angle)-y*Math.sin(angle),north=x*Math.sin(angle)+y*Math.cos(angle);pts.push([lat+north/111,lon+east/(111*Math.max(.2,Math.cos(lat*Math.PI/180)))])}
  return pts;
}
function renderRadar(ts){
  radarLayer.clearLayers();
  var frames=current&&current.radar_frames||[],bounds=current&&current.radar_bounds;if(!frames.length||!bounds){setText("radarStatus","No reconstructed radar frame loaded");return}
  var exact=frames.find(function(f){return f.timestamp===ts});var frame=exact||frames.slice().reverse().find(function(f){return f.timestamp<ts});if(!frame){setText("radarStatus","No frame at or before current time");return}
  var op=.82;var overlay=L.imageOverlay("data/"+frame.file,bounds,{pane:"archiveRadarPane",opacity:op,interactive:false,attribution:"Historical Level-II reflectivity reconstruction"});overlay.addTo(radarLayer);
  setText("radarStatus","Frame "+fmtUTC(frame.timestamp)+(exact?"":" • prior available scan"));
}
function renderMapObjects(ts){
  objectsLayer.clearLayers();motionLayer.clearLayers();labelLayer.clearLayers();
  var rows=features.filter(function(f){return f.properties.timestamp===ts&&!f.properties.context_only});
  rows.forEach(function(f){
    var p=f.properties,key=p.track_key,selected=selectedKey===key,pts=cellPoints(p);if(pts.length<3)return;
    var c=objectRisk(p);
    var poly=L.polygon(pts,{color:selected?"#fff":c,weight:selected?3:1.7,fillColor:c,fillOpacity:selected?.26:0,opacity:selected?1:.95,lineJoin:"round",interactive:true}).addTo(objectsLayer);
    poly.bindTooltip("<b>OBJECT "+esc(objectOrdinal(f))+"</b><br>"+num(p.max_reflectivity_dbz)+" dBZ • "+num(p.area_km2)+" km²",{sticky:true});
    poly.on("click",function(){selectObject(f)});
    var hit=L.polygon(pts,{pane:"objectHitPane",color:"#fff",weight:12,opacity:.001,fillColor:"#fff",fillOpacity:.001,bubblingMouseEvents:false}).addTo(objectsLayer);
    hit.on("click",function(){selectObject(f)});
    var lat=Number(p.centroid_lat),lon=Number(p.centroid_lon);
    if(objectNumbers&&Number.isFinite(lat)&&Number.isFinite(lon)){
      L.marker([lat,lon],{icon:L.divIcon({className:"sq-object-label-wrap",iconSize:null,iconAnchor:[0,0],html:"<div class='sq-object-label "+(selected?"":"dim")+"'>"+esc(objectOrdinal(f))+"</div>"}),interactive:false}).addTo(labelLayer);
    }
    var speed=Number(p.motion_speed_kt),dir=Number(p.motion_direction_deg??p.motion_dir_deg);
    if(Number.isFinite(speed)&&Number.isFinite(dir)&&speed<=75&&Number.isFinite(lat)&&Number.isFinite(lon)){
      var km=Math.max(5,Math.min(14,4+speed*.18)),br=dir*Math.PI/180,lat2=lat+km*Math.cos(br)/111,lon2=lon+km*Math.sin(br)/(111*Math.max(.2,Math.cos(lat*Math.PI/180)));
      L.polyline([[lat,lon],[lat2,lon2]],{color:selected?"#fff":"#d7e7ef",weight:selected?2.7:1.4,opacity:selected?.95:.72,interactive:false}).addTo(motionLayer);
      L.circleMarker([lat2,lon2],{radius:selected?4:2.5,color:selected?"#fff":"#d7e7ef",fillColor:selected?"#fff":"#d7e7ef",fillOpacity:.85,weight:0,interactive:false}).addTo(motionLayer);
    }
  });
}
function objectOrdinal(f){
  var rows=features.filter(function(x){return x.properties.timestamp===f.properties.timestamp&&!x.properties.context_only}).slice().sort(function(a,b){var ar=rankValue(a.properties),br=rankValue(b.properties);if(ar!=null||br!=null)return (br??-1)-(ar??-1);return Number(b.properties.max_reflectivity_dbz||0)-Number(a.properties.max_reflectivity_dbz||0)});
  var i=rows.findIndex(function(x){return x.properties.track_key===f.properties.track_key});return String(i+1).padStart(2,"0");
}
function renderObjectPicker(){
  var box=q("objectPicker"),rows=features.filter(function(f){return f.properties.timestamp===times[currentIndex]&&!f.properties.context_only}).slice().sort(function(a,b){var ar=rankValue(a.properties),br=rankValue(b.properties);if(ar!=null||br!=null)return (br??-1)-(ar??-1);return Number(b.properties.max_reflectivity_dbz||0)-Number(a.properties.max_reflectivity_dbz||0)});
  setText("objectCount",rows.length+" objects");
  if(!rows.length){box.innerHTML="<div class='history-empty'>No cell objects at this scan.</div>";return}
  box.innerHTML=rows.map(function(f){var p=f.properties,ord=objectOrdinal(f),sel=selectedKey===p.track_key,c=objectRisk(p);return "<button type='button' class='object-pick "+(sel?"active":"")+"' data-track='"+esc(p.track_key)+"'><b><span class='risk-dot' style='background:"+c+"'></span>OBJECT "+ord+"</b><span>Cell "+esc(p.object_id)+" • "+num(p.max_reflectivity_dbz)+" dBZ</span></button>"}).join("");
  box.querySelectorAll("[data-track]").forEach(function(btn){btn.onclick=function(){var f=rows.find(function(x){return x.properties.track_key===btn.dataset.track});if(f)selectObject(f)}});
}
function trackRows(){
  if(!selectedKey)return [];
  return features.filter(function(f){return f.properties.track_key===selectedKey}).sort(function(a,b){return a.properties.timestamp.localeCompare(b.properties.timestamp)});
}
function closestRow(rows,target,after){
  if(!rows.length)return null;
  var t=new Date(target).getTime(),best=null,bd=Infinity;
  rows.forEach(function(f){var tt=new Date(f.properties.timestamp).getTime();if(after&&tt<t)return;if(!after&&tt>t)return;var d=Math.abs(tt-t);if(d<bd){bd=d;best=f}});
  return best;
}
function selectedAtTime(){
  var rows=trackRows();if(!rows.length)return null;var ts=times[currentIndex];return rows.find(function(f){return f.properties.timestamp===ts})||rows.slice().reverse().find(function(f){return f.properties.timestamp<=ts})||rows[0];
}
function durationText(rows){
  if(rows.length<2)return rows.length+" scan";
  var d=(new Date(rows.at(-1).properties.timestamp)-new Date(rows[0].properties.timestamp))/60000;return num(d,0)+" min";
}
function renderObjectCard(f){
  if(!f){
    setText("objectTitle","OBJECT —");setText("objectSubtitle","Select an object on the map or from the inventory.");setText("objectTime","—");setText("objectBadge","NO SELECTION");["objectLatLon","objectMotion","objectDistance","objectAge","objectDuration","objectQuality"].forEach(function(id){setText(id,"—")});q("objectAccent").style.background="#526776";return;
  }
  var p=f.properties,rows=trackRows(),age=Number(p.age_scans),dur=durationText(rows),dist=haversineMi(p.centroid_lat,p.centroid_lon,BTV[0],BTV[1]),dir=Number(p.motion_direction_deg??p.motion_dir_deg),speed=Number(p.motion_speed_kt);
  q("objectAccent").style.background=objectRisk(p);
  setText("objectTitle","OBJECT "+objectOrdinal(f));
  setText("objectSubtitle",p.radar_site+" • Track "+p.track_key+" • Cell "+(p.object_id??"—"));
  setText("objectTime",fmtTime(p.timestamp)+" • "+fmtUTC(p.timestamp));
  var z=Number(p.max_reflectivity_dbz);setText("objectBadge",Number.isFinite(z)?(z>=45?"HIGH Z":z>=35?"MODERATE":"CANDIDATE"):"OBJECT");
  setText("objectLatLon",num(p.centroid_lat,2)+"°N / "+num(Math.abs(Number(p.centroid_lon)),2)+"°W");
  setText("objectMotion",Number.isFinite(speed)?Math.round(speed)+" kt • "+num(dir,0)+"° ("+compass(dir)+")":"Motion —");
  setText("objectDistance",Number.isFinite(dist)?num(dist,0)+" mi":"—");
  setText("objectAge",age?age+" scans":"< 1 scan");
  setText("objectDuration",dur);
  setText("objectQuality",p.data_quality||p.track_quality||"—");
}
function probabilityHistory(rows){
  return rows.map(function(f){var p=f.properties;return {ts:p.timestamp,vals:[probabilityFor(p,"15min"),probabilityFor(p,"30min"),probabilityFor(p,"45min"),probabilityFor(p,"60min")]}}).filter(function(x){return x.vals.some(function(v){return Number.isFinite(v))});
}
function linePath(points,idx,W,H,L,R,T,B){
  var valid=points.map(function(x,i){return {i:i,v:x.vals[idx]}}).filter(function(x){return Number.isFinite(x.v)});
  if(!valid.length)return "";
  var plotW=W-L-R,plotH=H-T-B;
  var x=function(i){return L+(points.length===1?plotW/2:i*plotW/(points.length-1))};
  var y=function(v){return T+(1-Math.max(0,Math.min(1,Number(v)||0)))*plotH};
  return valid.map(function(pt,n){return (n?"L":"M")+x(pt.i).toFixed(1)+" "+y(pt.v).toFixed(1)}).join(" ");
}
function renderProbabilityChart(points){
  var svg=q("probChart");if(!svg)return;svg.innerHTML="";
  if(!points.length){svg.innerHTML="<text x='260' y='92' text-anchor='middle' class='chart-text'>No attached research probability history</text>";return}
  var W=520,H=190,L=38,R=10,T=18,B=28,plotW=W-L-R,plotH=H-T-B;
  var x=function(i){return L+(points.length===1?plotW/2:i*plotW/(points.length-1))};
  var y=function(v){return T+(1-Math.max(0,Math.min(1,Number(v)||0)))*plotH};
  for(var g=0;g<=4;g++){
    var pct=g*25,yy=y(pct/100);
    svg.innerHTML+="<line x1='"+L+"' y1='"+yy.toFixed(1)+"' x2='"+(W-R)+"' y2='"+yy.toFixed(1)+"' class='chart-gridline'/>";
    svg.innerHTML+="<text x='"+(L-6)+"' y='"+(yy+3).toFixed(1)+"' text-anchor='end' class='chart-text'>"+pct+"%</text>";
  }
  var firstTs=new Date(points[0].ts),lastTs=new Date(points.at(-1).ts);
  var lastAge=Math.max(5,(lastTs-firstTs)/60000);
  svg.innerHTML+="<text x='"+L+"' y='"+(H-7)+"' class='chart-text'>0 min</text><text x='"+(W-R)+"' y='"+(H-7)+"' text-anchor='end' class='chart-text'>"+num(lastAge,0)+" min</text>";
  svg.innerHTML+="<line x1='"+L+"' y1='"+(H-B)+"' x2='"+(W-R)+"' y2='"+(H-B)+"' class='chart-axis'/>";
  var cls=["chart-line-15","chart-line-30","chart-line-45","chart-line-60"];
  for(var i=0;i<4;i++){
    var path=linePath(points,i,W,H,L,R,T,B);
    if(!path)continue;
    svg.innerHTML+="<path d='"+path+"' class='chart-path "+cls[i]+"'/>";
    points.forEach(function(pt,idx){
      var v=pt.vals[i];if(!Number.isFinite(v))return;
      var age=(new Date(pt.ts)-firstTs)/60000;
      svg.innerHTML+="<circle cx='"+x(idx).toFixed(1)+"' cy='"+y(v).toFixed(1)+"' r='2.8' class='prob-point "+cls[i]+"'><title>"+esc(fmtTime(pt.ts)+" • age "+num(age,0)+" min • "+[15,30,45,60][i]+"m "+(v*100).toFixed(1)+"%")+"</title></circle>";
    });
  }
  var activeTs=times[currentIndex],idx=points.findIndex(function(x){return x.ts===activeTs});
  if(idx<0){for(var j=0;j<points.length;j++)if(points[j].ts<=activeTs)idx=j;if(idx<0)idx=0}
  var xx=x(idx);
  svg.innerHTML+="<line x1='"+xx.toFixed(1)+"' y1='"+T+"' x2='"+xx.toFixed(1)+"' y2='"+(H-B)+"' class='chart-current'/><text x='"+xx.toFixed(1)+"' y='"+(T-5)+"' text-anchor='middle' class='chart-text'>CURRENT</text>";
}
function renderProbability(f){
  var p=f&&f.properties,rows=trackRows(),points=probabilityHistory(rows),v=p?probabilityFor(p,"15min"):null,prior=null;
  if(p&&rows.length){var idx=rows.findIndex(function(x){return x.properties.timestamp===p.timestamp});if(idx>0)prior=probabilityFor(rows[idx-1].properties,"15min")}
  if(v==null){q("probabilityValue").classList.add("na");setText("probabilityValue","—");setText("probabilityDelta","No score attached");q("probabilityDelta").className="prob-delta flat";setText("probabilityNote","This historical scan has no attached research probability. The viewer keeps the field visible so training progress can be seen without inventing a score.");}
  else{q("probabilityValue").classList.remove("na");setText("probabilityValue",formatProb(v));var d=prior==null?null:v-prior;setText("probabilityDelta",d==null?"Score attached":(d>0?"▲ +":"▼ ")+(Math.abs(d)*100).toFixed(1)+" pp");q("probabilityDelta").className="prob-delta "+(d==null?"flat":d>0?"up":"down");setText("probabilityNote","Every historical scan is evaluated independently from its causal feature state. The horizon lines show what the model expected from each scan onward • research only.");}
  var vals=[["Model",v,"#1f90e9"],["Analog",p&&p.analog_probability,"#f0c54c"],["Environment",p&&p.environment_signal,"#62ce73"],["Overall",p&&p.ensemble_probability,"#ff5648"]];
  q("probComponents").innerHTML=vals.map(function(x){return "<div class='prob-component'><span><i class='comp-dot' style='background:"+x[2]+"'></i>"+x[0]+"</span><b>"+formatProb(x[1])+"</b></div>"}).join("")+"<div style='margin-top:5px;font-size:8px;color:#748a9b'>Each point is one retained scan from the same tracked object. Hover a point for exact time/age/horizon.</div>";
  var scored=points.filter(function(x){return Number.isFinite(x.vals[0])});
  var peak=scored.reduce(function(best,x){return best==null||x.vals[0]>best.v?{v:x.vals[0],ts:x.ts}:best},null);
  var age=rows.length?((new Date(rows.at(-1).properties.timestamp)-new Date(rows[0].properties.timestamp))/60000):0;
  setText("probabilitySummary",num(age,0)+" min track • "+scored.length+" scored scans • current "+(v==null?"—":formatProb(v))+" • "+(peak?formatProb(peak.v)+" peak 15m":"—"));
  renderProbabilityChart(points);
  renderEnvironmentOutlook(f,rows);
}
function renderEnvironmentOutlook(f,rows){
  var box=q("environmentOutlook");if(!box)return;
  var p=f&&f.properties,next=closestRow(rows,p?.timestamp,true),curEnv=p?.environment||{},nextEnv=next?.properties?.environment||{};
  var defs=[["SNSQ","snsq","",2],["MUCAPE","mucape_jkg","J/kg",0],["0–6 km shear","shear_0_6km_kt","kt",0],["0–1 km SRH","srh01_m2s2","m²/s²",0],["PWAT","pwat_mm","mm",1],["RH 0–2 km","rh_0_2km_pct","%",0]];
  var fmt=function(v,d,u){return v==null?"—":num(v,d)+(u?" "+u:"")};
  box.innerHTML=defs.map(function(d){
    var now=fieldValue(curEnv,d[1]),later=fieldValue(nextEnv,d[1]),delta=(now!=null&&later!=null)?Number(later)-Number(now):null;
    var arrow=delta==null?"→":Math.abs(delta)<(d[1]==="snsq"?.05:.5)?"→":delta>0?"↑":"↓";
    return "<div class='env-outlook-tile'><span>"+d[0]+"</span><b>"+fmt(now,d[3],d[2])+"</b><i>"+arrow+" "+(later==null?"next scan unavailable":fmt(later,d[3],d[2]))+"</i></div>";
  }).join("");
}
function renderKeyTrends(f){
  var p=f&&f.properties,rows=trackRows();if(!p){q("keyTrends").innerHTML="<div class='history-empty'>Select a cell to populate trends.</div>";return}
  var first=rows[0]?.properties,last=rows.at(-1)?.properties;
  var delta=function(a,b,d){var x=Number(a),y=Number(b);return Number.isFinite(x)&&Number.isFinite(y)?(x-y).toFixed(d||0):null}
  var tiles=[
    ["MAX REFLECTIVITY",num(p.max_reflectivity_dbz,0)+" dBZ",delta(p.max_reflectivity_dbz,first?.max_reflectivity_dbz,0),"dBZ"],
    ["OBJECT AREA",num(p.area_km2,0)+" km²",delta(p.area_km2,first?.area_km2,0),"km²"],
    ["MOTION SPEED",num(p.motion_speed_kt,0)+" kt",delta(p.motion_speed_kt,first?.motion_speed_kt,0),"kt"],
    ["AGE",p.age_scans==null?"—":p.age_scans+" scans",null,""]
  ];
  q("keyTrends").innerHTML=tiles.map(function(x){var d=x[2];return "<div class='trend-tile'><div class='label'>"+x[0]+"</div><div class='value'>"+x[1]+"</div><div class='delta "+(d==null?"neutral":"")+"'>"+(d==null?"Track context":(Number(d)>=0?"▲ +":"▼ ")+Math.abs(Number(d))+" "+x[3])+"</div></div>"}).join("");
}
function envDisplay(e,key){
  var v=fieldValue(e,key);if(v==null)return "—";var u=fieldUnits(e,key);return num(v,key==="lcl_m"?0:key==="sbcape_jkg"||key==="mlcape_jkg"||key==="mucape_jkg"||key==="dcape_jkg"?0:1)+(u?" "+u:"");
}
function renderEnvironment(f){
  var p=f&&f.properties; if(!p){q("environmentTable").innerHTML="";setText("envSource","—");return}
  var rows=trackRows(),center=p,prev=closestRow(rows,p.timestamp,false),next=closestRow(rows,p.timestamp,true);
  var fields=[["SBCAPE","sbcape_jkg"],["MLCAPE","mlcape_jkg"],["MUCAPE","mucape_jkg"],["MLCIN","mlcin_jkg"],["DCAPE","dcape_jkg"],["PWAT","pwat_mm"],["LCL","lcl_m"],["0–3 km lapse","lapse_rate_0_3km_c_km"],["0–7.5 km lapse","lapse_rate_0_7_5km_c_km"],["0–6 km shear","shear_0_6km_kt"],["0–1 km SRH","srh01_m2s2"],["SNSQ","snsq"],["RH 0–2 km","rh_0_2km_pct"],["Wet-bulb 0–3 km","wet_bulb_0_3km_c"]];
  var header="<thead><tr><th>Parameter</th><th>Previous scan</th><th>Current</th><th>Next scan</th></tr></thead><tbody>";
  header+=fields.map(function(x){return "<tr><td>"+x[0]+"</td><td class='ctx-prev'>"+envDisplay(prev?.properties.environment,x[1])+"</td><td class='ctx-current'>"+envDisplay(center.environment,x[1])+"</td><td class='ctx-next'>"+envDisplay(next?.properties.environment,x[1])+"</td></tr>"}).join("");
  q("environmentTable").innerHTML=header+"</tbody>";
  var age=p.environment_age_minutes??p.environment?.age_minutes;setText("envSource",(p.environment_source||p.environment?.source||"RAP")+(age==null?"":" • "+num(age,0)+" min"));
}
function evidenceItem(icon,cls,title,body){return "<div class='evidence-card'><div class='evidence-icon "+(cls||"")+"'>"+icon+"</div><div><b>"+title+"</b><span>"+body+"</span></div></div>"}
function renderEvidence(f){
  var p=f&&f.properties,c=current;
  if(!p){q("evidenceGrid").innerHTML="";return}
  var envStatus=p.environment_status||p.environment?.status||"—";
  var metarBody=c?.observing_station?c.observing_station+" • min visibility "+(c.min_visibility_km==null?"—":num(c.min_visibility_km,2)+" km")+" • peak wind "+(c.peak_wind_kt==null?"—":num(c.peak_wind_kt,0)+" kt"):"Case station not attached";
  var mping=p.mping_reports||p.mping_count||p.mping_support;
  var warnings=p.warning_distance_mi??p.nearest_warning_distance_mi;
  q("evidenceGrid").innerHTML=
    evidenceItem("✓","", "METAR / ASOS context", metarBody)+
    evidenceItem(mping?"✓":"—",mping?"":"warn","MPING reports",mping?(String(mping)+" attached report(s)"):"Not attached to this case package")+
    evidenceItem(warnings!=null?"!":"—",warnings!=null?"warn":"","Warnings / alerts",warnings!=null?"Nearest documented context: "+num(warnings,0)+" mi":"No warning proximity field attached")+
    evidenceItem(envStatus==="complete"?"✓":"! ",envStatus==="complete"?"":"warn","Environmental attachment",String(envStatus).replace("_"," ")+" • source "+(p.environment_source||"RAP"));
}
function renderHistory(f){
  var rows=trackRows();setText("historyCount",rows.length+" scans");
  if(!rows.length){q("historyChart").innerHTML="<text x='260' y='70' text-anchor='middle' class='chart-text'>No retained object history</text>";q("historyTable").innerHTML="";return}
  var W=520,H=145,P=28,vals=rows.map(function(r){return {z:Number(r.properties.max_reflectivity_dbz),a:Number(r.properties.area_km2),m:Number(r.properties.motion_speed_kt)}}),z=vals.map(x=>x.z).filter(Number.isFinite),a=vals.map(x=>x.a).filter(Number.isFinite),m=vals.map(x=>x.m).filter(Number.isFinite);
  var minZ=z.length?Math.min.apply(null,z):0,maxZ=z.length?Math.max.apply(null,z):1,minA=a.length?Math.min.apply(null,a):0,maxA=a.length?Math.max.apply(null,a):1,minM=m.length?Math.min.apply(null,m):0,maxM=m.length?Math.max.apply(null,m):1;
  var norm=function(v,min,max){return Number.isFinite(v)?(v-min)/(Math.max(.001,max-min)):null};
  var x=function(i){return P+(rows.length===1?0:i*(W-2*P)/(rows.length-1))},y=function(v){return H-P-v*(H-2*P)};
  var svg="<line x1='"+P+"' y1='"+(H-P)+"' x2='"+(W-P)+"' y2='"+(H-P)+"' class='chart-axis'/>";
  svg+="<text x='3' y='12' class='chart-text'>100</text><text x='7' y='"+(H/2+3)+"' class='chart-text'>50</text><text x='7' y='"+(H-P+3)+"' class='chart-text'>0</text>";
  var lines=[["z","#d34bc0",minZ,maxZ],["a","#1f90e9",minA,maxA],["m","#54c56b",minM,maxM]];
  lines.forEach(function(line){
    var path=rows.map(function(r,i){var v=norm(Number(r.properties[line[0]==="z"?"max_reflectivity_dbz":line[0]==="a"?"area_km2":"motion_speed_kt"]),line[2],line[3]);return v==null?null:(i?"L":"M")+x(i).toFixed(1)+" "+y(v).toFixed(1)}).filter(Boolean).join(" ");if(path)svg+="<path d='"+path+"' fill='none' stroke='"+line[1]+"' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'/>";
  });
  var active=f?rows.findIndex(function(r){return r.properties.timestamp===f.properties.timestamp}):-1;if(active<0)active=rows.length-1;
  svg+="<line x1='"+x(active).toFixed(1)+"' y1='"+P+"' x2='"+x(active).toFixed(1)+"' y2='"+(H-P)+"' class='chart-current'/>";
  q("historyChart").innerHTML=svg+"<text x='"+P+"' y='"+(H-2)+"' class='chart-text'>"+fmtTime(rows[0].properties.timestamp)+"</text><text x='"+(W-P)+"' y='"+(H-2)+"' text-anchor='end' class='chart-text'>"+fmtTime(rows.at(-1).properties.timestamp)+"</text>";
  q("historyTable").innerHTML="<thead><tr><th>Time</th><th>15m</th><th>30m</th><th>45m</th><th>60m</th><th>Max Z</th><th>Area</th><th>L × W</th><th>Motion</th><th>Z trend</th><th>Env</th></tr></thead><tbody>"+rows.map(function(r){var p=r.properties,cur=f&&p.timestamp===f.properties.timestamp,pv=p.research_probabilities||{},pf=function(v){return Number.isFinite(Number(v))?(Number(v)*100).toFixed(0)+"%":"—"};return "<tr class='"+(cur?"current":"")+"' data-ts='"+esc(p.timestamp)+"'><td>"+fmtTime(p.timestamp)+"</td><td>"+pf(pv["15"]??pv["15min"])+"</td><td>"+pf(pv["30"]??pv["30min"])+"</td><td>"+pf(pv["45"]??pv["45min"])+"</td><td>"+pf(pv["60"]??pv["60min"])+"</td><td>"+num(p.max_reflectivity_dbz,0)+" dBZ</td><td>"+num(p.area_km2,0)+" km²</td><td>"+num(p.length_km,1)+" × "+num(p.width_km,1)+" km</td><td>"+num(p.motion_speed_kt,0)+" kt</td><td>"+num(p.reflectivity_trend_dbz_per_hr,1)+"</td><td>"+esc(p.environment_status||"—")+"</td></tr>"}).join("")+"</tbody>";
  q("historyTable").querySelectorAll("[data-ts]").forEach(function(row){row.onclick=function(){var i=times.indexOf(row.dataset.ts);if(i>=0){currentIndex=i;render()}}});
}
function renderModelStatus(){
  var s=catalog?.model_summary, h=s?.horizons||{};setText("modelStatus",catalog?.probability_status||"research");
  var items=[["Archive cases",catalog?.cases?.length],["Object rows",catalog?.source_object_rows],["Probability",catalog?.probability_status],["Release",s?.release_status||"candidate_only_not_operational"]];
  var horizonValues=Object.keys(h);
  if(horizonValues.length)items.push(["15m ROC / PR",num((h["15m"]?.metrics?.auc_roc),2)+" / "+num((h["15m"]?.metrics?.average_precision),2)]);
  q("modelStatusCard").innerHTML=items.map(function(x){return "<div class='status-cell'><span>"+x[0]+"</span><b>"+(x[1]??"—")+"</b></div>"}).join("");
}
function renderCaseInfo(){
  var c=current;setText("archiveSite",(c?.radar_site||"—")+" • BTV CWA");setText("archiveTime",c?fmtUTC(times.at(-1)): "");setText("caseTitle",c?c.case_id+" • "+c.radar_site:"No case");setText("caseMeta",c?(c.source_study||"Historical study")+" • "+fmtUTC(c.first_scan_utc)+" → "+fmtUTC(c.last_scan_utc):"—");setText("caseBadge",c?.status==="historical_pilot"?"PILOT":"ARCHIVE");}
async function loadCase(index){
  current=catalog.cases[index];selectedKey=null;currentIndex=0;
  var geo=await (await fetch("data/"+current.file,{cache:"no-store"})).json();features=geo.features||[];
  times=[...new Set(features.map(function(f){return f.properties.timestamp}))].sort();
  q("slider").max=Math.max(0,times.length-1);q("slider").value=0;
  renderCaseInfo();addRadarMarker();fitToCase();render();
}
function render(){
  if(!times.length)return;
  var ts=times[currentIndex];setText("timelineTime",fmtTime(ts)+" • "+fmtUTC(ts));setText("mapScanLabel",fmtTime(ts));q("mapScanLabel").title=fmtUTC(ts);
  renderRadar(ts);renderMapObjects(ts);renderObjectPicker();
  var f=selectedAtTime();renderObjectCard(f);renderKeyTrends(f);renderProbability(f);renderEnvironment(f);renderEvidence(f);renderHistory(f);
}
function selectObject(f){
  if(!f)return;selectedKey=f.properties.track_key;
  var idx=times.indexOf(f.properties.timestamp);if(idx>=0)currentIndex=idx;
  render();
}
function advance(step){if(!times.length)return;currentIndex=(currentIndex+step+times.length)%times.length;render()}
function tick(){if(!playing)return;advance(1);timer=setTimeout(tick,800)}
function togglePlay(){playing=!playing;setText("playBtn",playing?"❚❚":"▶ Play");if(playing)tick();else clearTimeout(timer)}

q("slider").addEventListener("input",function(e){currentIndex=Number(e.target.value);render()});
q("prevBtn").onclick=function(){advance(-1)};q("nextBtn").onclick=function(){advance(1)};q("playBtn").onclick=togglePlay;
q("objectNumbersBtn").onclick=function(){objectNumbers=!objectNumbers;q("objectNumbersBtn").classList.toggle("active",objectNumbers);renderMapObjects(times[currentIndex])};
document.querySelectorAll("[data-jump]").forEach(function(btn){btn.onclick=function(){var el=q(btn.dataset.jump);if(el)el.scrollIntoView({behavior:"smooth",block:"start"});document.querySelectorAll("[data-jump]").forEach(function(b){b.classList.toggle("active",b===btn)})}});
q("detailsBtn").onclick=function(){var modal=q("modal");q("statusText").textContent=catalog?.truth_note||"—";q("statusList").innerHTML=[["Package",catalog?.version],["Data status",catalog?.data_status],["Probability",catalog?.probability_status],["Cases",catalog?.cases?.length],["Object rows",catalog?.source_object_rows],["Build",catalog?.build_time_utc]].map(function(x){return "<div class='status-row'><span>"+x[0]+"</span><b>"+(x[1]??"—")+"</b></div>"}).join("");modal.classList.remove("hidden")};
q("closeModal").onclick=function(){q("modal").classList.add("hidden")};

fetch("data/catalog.json",{cache:"no-store"}).then(function(r){if(!r.ok)throw new Error("catalog HTTP "+r.status);return r.json()}).then(function(c){catalog=c;renderModelStatus();var sel=q("caseSelect");sel.innerHTML=(catalog.cases||[]).map(function(x,i){return "<option value='"+i+"'>"+esc(x.case_id)+" • "+esc(x.radar_site)+"</option>"}).join("");sel.onchange=function(){loadCase(Number(sel.value)).catch(function(e){setText("subtitle","Archive load error: "+e.message)})};return loadCase(0)}).catch(function(e){setText("subtitle","Archive viewer failed: "+e.message);if(q("objectPicker"))q("objectPicker").innerHTML="<div class='history-empty'>"+esc(e.message)+"</div>"});
})();
