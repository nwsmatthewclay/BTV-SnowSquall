// Snow Squall live viewer v15: probability cells + robust click + canonical MetPy environment

var map=L.map("liveMap",{zoomControl:false,keyboard:false,preferCanvas:true}).setView([44.15,-73.65],8);
L.control.zoom({position:"topright"}).addTo(map);
var radarPane=map.createPane("liveRadarPane");radarPane.style.zIndex=240;
var hitPane=map.createPane("liveHitPane");hitPane.style.zIndex=650;hitPane.style.pointerEvents="auto";
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",{maxZoom:12,attribution:"Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"}).addTo(map);
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",{maxZoom:12,opacity:.78,attribution:"Labels © Esri"}).addTo(map);

var layers={KCXX:L.layerGroup().addTo(map),KTYX:L.layerGroup().addTo(map),labels:L.layerGroup().addTo(map),motion:L.layerGroup().addTo(map)};
var radarLayer=L.layerGroup().addTo(map),radarMosaic=null,radarMode="reflectivity";
var radarLocations={KCXX:[44.511,-73.166],KTYX:[43.756,-75.680],KBTV:[44.472,-73.154]};
var BTV=[44.472,-73.154];
var datasets={},allObjects=[],selected=null,objectNumbers=true,refreshTimer=null,cursorGrid=null,cursorBound=false,lastObjectClickAt=0;
var radarHistory={frames:[]},radarHistoryIndex=-1,radarAnimationTimer=null;

var LIVE_BASE="https://raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-live-data/viewer/data/live/";
var SHADOW_BASE="https://raw.githubusercontent.com/nwsmatthewclay/BTV-SnowSquall/snow-squall-shadow-data/viewer/data/shadow/";
var SHADOW_MIN_COVERAGE=0.40;
var MAX_LIVE_OBJECT_AGE_MIN=75;
var DISPLAY_MIN_SCORE=35;

function q(id){return document.getElementById(id)}
function cursorGridIndex(lat,lon){
  if(!cursorGrid||!cursorGrid.shape)return null;
  var ny=Number(cursorGrid.shape[0]),nx=Number(cursorGrid.shape[1]),spacing=Number(cursorGrid.spacing_km||1),half=Number(cursorGrid.half_width_km||180),clat=Number(cursorGrid.center_lat||44.15),clon=Number(cursorGrid.center_lon||-73.65);
  if(![ny,nx,spacing,half,clat,clon].every(Number.isFinite)||ny<2||nx<2)return null;
  var latKm=(Number(lat)-clat)*111.32;
  var lonKm=(Number(lon)-clon)*111.32*Math.cos(clat*Math.PI/180);
  var row=Math.round((latKm+half)/spacing),col=Math.round((lonKm+half)/spacing);
  if(row<0||row>=ny||col<0||col>=nx)return null;
  return {row:row,col:col,index:row*nx+col};
}
function cursorValue(values,index,missing){
  if(!values||index<0||index>=values.length)return null;
  var v=Number(values[index]);
  return Number.isFinite(v)&&v!==Number(missing) ? v : null;
}
function updateCursorReadout(lat,lon){
  var box=q("cursorReadout");
  if(!box)return;
  var idx=cursorGridIndex(lat,lon);
  if(!idx||!cursorGrid){
    box.textContent="CURSOR — | Z — dBZ | V —";
    return;
  }
  var z=cursorValue(cursorGrid.reflectivity_dbz,idx.index,cursorGrid.reflectivity_missing??-9999);
  var parts=[];
  var velocity=cursorGrid.velocity_by_site||{};
  Object.keys(velocity).sort().forEach(function(site){
    var v=cursorValue(velocity[site],idx.index,cursorGrid.velocity_missing??-9999);
    if(v!=null)parts.push(site+" "+Math.round(v)+" kt");
  });
  box.textContent="CURSOR "+Number(lat).toFixed(2)+"°N "+Number(Math.abs(lon)).toFixed(2)+"°W | Z "+(z==null?"—":Math.round(z)+" dBZ")+" | V "+(parts.length?parts.join(" / "):"—");
}
function bindCursorReadout(){
  if(cursorBound)return;
  cursorBound=true;
  map.on("mousemove",function(e){updateCursorReadout(e.latlng.lat,e.latlng.lng)});
  map.on("mouseout",function(){var box=q("cursorReadout");if(box)box.textContent="CURSOR — | Z — dBZ | V —"});
}
function setText(id,v){var e=q(id);if(e)e.textContent=v==null?"—":v}
function num(v,d){if(d===undefined)d=1;var n=Number(v);return v==null||!Number.isFinite(n)?"—":n.toFixed(d)}
function esc(v){return String(v==null?"—":v).replace(/[&<>"']/g,function(m){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}})}
function parseUtcDate(t){
  if(t==null||t==="")return null;
  if(t instanceof Date)return isNaN(t.getTime())?null:t;
  var s=String(t).trim();
  // Live radar timestamps are UTC. If an ISO timestamp has no explicit
  // timezone, treat it as UTC rather than browser-local time.
  if(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(s))s+="Z";
  var d=new Date(s);
  return isNaN(d.getTime())?null:d;
}
function fmtTime(t){
  var d=parseUtcDate(t);
  if(!d)return "—";
  try{
    return new Intl.DateTimeFormat("en-US",{
      timeZone:"America/New_York",
      month:"short",day:"numeric",hour:"numeric",minute:"2-digit",
      timeZoneName:"short"
    }).format(d);
  }catch(_){
    return d.toLocaleString("en-US",{timeZone:"America/New_York",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
  }
}
function fmtUTC(t){return fmtTime(t)}
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
function riskScore(p){var v=p?.research_probabilities?.["15min"]??p?.research_probabilities?.["15"]??p?.probability_15min; if(Number.isFinite(Number(v)))return Number(v); var s=shadowRecord(p.radar_site,p.track_id),sv=probValue(s,"15"); if(Number.isFinite(Number(sv)))return Number(sv); var rank=Number(p.candidate_rank_score);if(Number.isFinite(rank))return rank/100;var z=Number(p.max_reflectivity_dbz);if(z>=45)return .85;if(z>=35)return .62;if(z>=25)return .38;return .16}
function objectRisk(p){var s=riskScore(p);return s>=.70?"#ff4d3d":s>=.45?"#ff9a3c":s>=.25?"#efcd48":"#54b6ee"}
function objectOrdinal(p){var site=String(p?.radar_site||"RADAR").toUpperCase();var track=String(p?.track_id??p?.object_id??"—");return site+"-"+track}
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
function radarHistoryFrame(){return radarHistory.frames&&radarHistory.frames.length&&radarHistoryIndex>=0?radarHistory.frames[radarHistoryIndex]:null}
function updateRadarTimelineUI(){
  var slider=q("radarTimelineSlider"),label=q("radarTimelineLabel"),play=q("radarPlayBtn");
  if(!slider)return;
  slider.max=Math.max(0,(radarHistory.frames||[]).length-1);
  slider.value=Math.max(0,radarHistoryIndex<0?slider.max:radarHistoryIndex);
  var f=radarHistoryFrame();
  setText("radarTimelineLabel",f?fmtTime(f.timestamp):"Live");
  if(play)play.textContent=radarAnimationTimer?"❚❚ PAUSE":"▶ PLAY";
}
function stopRadarAnimation(){if(radarAnimationTimer){clearInterval(radarAnimationTimer);radarAnimationTimer=null}updateRadarTimelineUI()}
function setRadarHistoryIndex(index){
  var frames=radarHistory.frames||[];
  if(!frames.length){radarHistoryIndex=-1;updateRadarTimelineUI();return}
  radarHistoryIndex=Math.max(0,Math.min(frames.length-1,Number(index)||0));
  stopRadarAnimation();
  updateRadarTimelineUI();
  renderRadarMosaic();
}
function playRadarAnimation(){
  var frames=radarHistory.frames||[];
  if(frames.length<2)return;
  if(radarAnimationTimer){stopRadarAnimation();return}
  if(radarHistoryIndex<0||radarHistoryIndex>=frames.length-1)radarHistoryIndex=0;
  updateRadarTimelineUI();
  radarAnimationTimer=setInterval(function(){
    radarHistoryIndex++;
    if(radarHistoryIndex>=frames.length){radarHistoryIndex=0}
    updateRadarTimelineUI();
    renderRadarMosaic();
  },900);
}
async function loadRadarHistory(){
  radarHistory=await fetchOptional(LIVE_BASE+"radar_history/manifest.json?cb="+Date.now(),{frames:[]});
  if(!Array.isArray(radarHistory.frames))radarHistory={frames:[]};
  if(radarHistory.frames.length){
    radarHistory.frames=radarHistory.frames.filter(function(f){return parseUtcDate(f.timestamp)});radarHistory.frames.sort(function(a,b){return parseUtcDate(a.timestamp).getTime()-parseUtcDate(b.timestamp).getTime()});
    radarHistoryIndex=radarHistory.frames.length-1;
  }else radarHistoryIndex=-1;
  updateRadarTimelineUI();
}
function mosaicMetaUrl(){return LIVE_BASE+"radar_mosaic.json?cb="+Date.now()}
function mosaicImageUrl(mode){var product=radarMosaic?.display_products||{};var name=(mode==="clean"?product.clean_image:product.raw_image)||(mode==="clean"?"radar_mosaic_clean.png":"radar_mosaic_raw.png");return LIVE_BASE+name+"?cb="+Date.now()}
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
  if(!radarMosaic||!radarMosaic.bounds){
    if(radarMode==="reflectivity"){
      var histFrameForWms=radarHistoryFrame();
      var useHistorical=radarHistoryIndex>=0 && radarHistoryIndex<(radarHistory.frames||[]).length-1;
      var wmsTime=useHistorical&&histFrameForWms?histFrameForWms.timestamp:new Date().toISOString();
      var iem=L.tileLayer.wms("https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0r-t.cgi",{
        layers:"nexrad-n0r-wmst",format:"image/png",transparent:true,version:"1.1.1",
        opacity:.72,time:wmsTime
      });
      iem.addTo(radarLayer);
      setText("radarStatus",useHistorical&&histFrameForWms?"IEM radar fallback • "+fmtTime(histFrameForWms.timestamp):"IEM live radar fallback • current NEXRAD mosaic");
      setText("legendTitle","WINTER REFLECTIVITY • dBZ");
      setText("legendNote","External fallback: IEM NEXRAD mosaic. Local KCXX/KTYX products resume automatically when published.");
      return;
    }
    var histFrame=radarHistoryFrame();
    if(histFrame&&radarMode==="reflectivity"){
      var histBounds=histFrame.bounds||[[41.90,-76.78],[46.40,-70.52]];
      var histName=histFrame.image.split("/").pop();
      L.imageOverlay(LIVE_BASE+"radar_history/"+histName+"?cb="+Date.now(),histBounds,{pane:"liveRadarPane",opacity:.96,interactive:false,crossOrigin:true}).addTo(radarLayer);
      setText("radarStatus","Historical radar frame • "+fmtTime(histFrame.timestamp)+" • live acquisition unavailable");
      setText("legendTitle","WINTER REFLECTIVITY • dBZ");
      setText("legendNote","Historical frame retained locally while the live radar publisher recovers.");
      if(!map._sqExtent){map.fitBounds(histBounds,{padding:[25,25],maxZoom:8});map._sqExtent=true}
      return;
    }
    if(radarMode==="velocity"){
      // Display-only emergency fallback: IEM serves current single-site
      // NEXRAD Level-III base velocity (N0U). This keeps the velocity control
      // useful when our local Level-II mosaic publisher is delayed.
      var ridgeUrl="https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/ridge.cgi";
      var ridgeSites=[["CXX","KCXX"],["KTYX","KTYX"]];
      ridgeSites.forEach(function(pair){
        var sector=pair[0],site=pair[1];
        L.tileLayer.wms(ridgeUrl,{
          layers:"single",format:"image/png",transparent:true,version:"1.1.1",
          sector:sector,prod:"N0U",opacity:.62
        }).addTo(radarLayer);
      });
      setText("radarStatus","IEM velocity fallback • KCXX + KTYX • current");
      setText("legendTitle","RADIAL VELOCITY • kt");
      setText("legendNote","Display fallback: current single-site NEXRAD base velocity. Local Level-II velocity resumes automatically when published.");
    }else{
      setText("radarStatus","Local mosaic unavailable • NOAA QC fallback");
      setText("legendTitle","WINTER REFLECTIVITY • dBZ");
      setText("legendNote","NOAA fallback is display-only; local object analysis remains independent.");
      addNoaaFallback();
    }
    return}
  var src=(radarMosaic.sources||[]).map(function(x){return x.radar}).filter(Boolean);var freshness=radarMosaic.status==="stale"?"RETAINED":"READY";setText("radarStatus","Mosaic "+freshness+" • "+(src.join(" + ")||"KCXX + KTYX"));
  if(radarMode==="velocity"){
    var vp=radarMosaic.display_products?.base_velocity||{};
    ["KCXX","KTYX"].forEach(function(site){
      var item=vp[site];
      if(!item||!item.clean_image)return;
      L.imageOverlay(LIVE_BASE+item.clean_image+"?cb="+Date.now(),item.bounds||radarMosaic.bounds,{
        pane:"liveRadarPane",opacity:.52,interactive:false,crossOrigin:true
      }).addTo(radarLayer);
    });
    setText("radarStatus","Base velocity • KCXX + KTYX • knots");
    setText("legendTitle","RADIAL VELOCITY • kt");
    setText("legendNote","Lowest-valid-sweep KCXX + KTYX velocity. Signed inbound/outbound flow is shown for cell analysis.");
  }else{
    var frame=radarHistoryFrame();
    var syncFrame=synchronizedRadarFrame();
    // A manual slider selection must control the displayed radar image.  The
    // synchronized frame is only the automatic/default selection; otherwise
    // the timeline can move while the map remains visually stuck on one image.
    var selectedFrame=(radarHistoryIndex>=0&&frame)?frame:syncFrame;
    var useStoredFrame=!!(selectedFrame&&selectedFrame.image&&selectedFrame.image!=="iem-wms");
    var imageName=useStoredFrame?selectedFrame.image.split("/").pop():"";
    var imageUrl=useStoredFrame?(LIVE_BASE+"radar_history/"+imageName+"?cb="+Date.now()):mosaicImageUrl("reflectivity");
    var imageBounds=useStoredFrame&&selectedFrame.bounds?selectedFrame.bounds:radarMosaic.bounds;
    var ov=L.imageOverlay(imageUrl,imageBounds,{pane:"liveRadarPane",opacity:.96,interactive:false,crossOrigin:true});
    ov.addTo(radarLayer);
    var ref=objectReferenceTime();
    var refText=ref?fmtTime(new Date(ref).toISOString()):"";
    var syncText=useStoredFrame&&selectedFrame.timestamp?" • "+(radarHistoryIndex>=0?"timeline ":"synced ")+fmtTime(selectedFrame.timestamp):"";
    setText("radarStatus","Reflectivity mosaic "+(radarMosaic.status==="stale"?"RETAINED":"READY")+" • KCXX + KTYX"+syncText+(refText?" • objects "+refText:""));
    setText("legendTitle","WINTER REFLECTIVITY • dBZ");
    setText("legendNote","KCXX + KTYX reflectivity mosaic. Object footprints are clickable and expose full attributes.");
  }
  if(!map._sqExtent){map.fitBounds(radarMosaic.bounds,{padding:[25,25],maxZoom:8});map._sqExtent=true}
}
function setRadarMode(mode){if(mode!=="reflectivity"&&mode!=="velocity")mode="reflectivity";radarMode=mode;document.querySelectorAll(".display-btn").forEach(function(b){b.classList.toggle("active",b.dataset.radarMode===mode)});renderRadarMosaic()}
function objectReferenceTime(){
  var times=allObjects.map(function(p){return p&&p.timestamp?new Date(p.timestamp).getTime():NaN}).filter(Number.isFinite);
  return times.length?Math.max.apply(null,times):null;
}
function alignRadarHistoryToObjects(){
  var ref=objectReferenceTime(),frames=radarHistory&&Array.isArray(radarHistory.frames)?radarHistory.frames:[];
  if(ref==null||!frames.length){radarHistoryIndex=-1;updateRadarTimelineUI();return}
  var best=-1,bestDiff=Infinity;
  frames.forEach(function(f,i){
    var d=parseUtcDate(f.timestamp);if(!d)return;
    var diff=Math.abs(d.getTime()-ref);if(diff<bestDiff){bestDiff=diff;best=i;}
  });
  // Never let an old archive frame masquerade as the current radar image.
  // If there is no frame within 12 minutes of the object cycle, show the
  // current synchronized mosaic instead and label the timeline LIVE.
  if(best>=0&&bestDiff<=12*60000)radarHistoryIndex=best;else radarHistoryIndex=-1;
  updateRadarTimelineUI();
}
function synchronizedRadarFrame(){
  var ref=objectReferenceTime();
  var frames=radarHistory&&Array.isArray(radarHistory.frames)?radarHistory.frames:[];
  if(ref==null||!frames.length)return null;
  var usable=frames.map(function(f){
    var t=parseUtcDate(f.timestamp||"").getTime();
    return Number.isFinite(t)?{f:f,t:t,diff:t-ref}:null;
  }).filter(Boolean);
  if(!usable.length)return null;
  // Prefer the latest frame at or before the object scan. If the archive does
  // not contain one, use the nearest frame only when it is reasonably close.
  var prior=usable.filter(function(x){return x.t<=ref}).sort(function(a,b){return b.t-a.t})[0];
  if(prior&&ref-prior.t<=12*60000)return prior.f;
  usable.sort(function(a,b){return Math.abs(a.diff)-Math.abs(b.diff)});
  return usable[0]&&Math.abs(usable[0].diff)<=8*60000?usable[0].f:null;
}
function geometryPoints(p){
  var g=p&&p.radar_geometry;
  if(!g||!g.type||!g.coordinates)return [];
  var rings=[];
  if(g.type==="Polygon"){
    rings=(g.coordinates||[]).filter(function(r){return Array.isArray(r)&&r.length>=3});
  }else if(g.type==="MultiPolygon"){
    (g.coordinates||[]).forEach(function(poly){
      if(Array.isArray(poly))poly.forEach(function(r){if(Array.isArray(r)&&r.length>=3)rings.push(r)});
    });
  }
  if(!rings.length)return [];
  // Use the largest exterior ring. The detector footprint is the meteorological
  // feature; do not replace it with an ellipse unless the footprint is absent.
  rings.sort(function(a,b){return b.length-a.length});
  var ring=rings[0].map(function(x){return [Number(x[1]),Number(x[0])]}).filter(function(x){return Number.isFinite(x[0])&&Number.isFinite(x[1])});
  if(ring.length<3)return [];
  var lat=Number(p.centroid_lat),lon=Number(p.centroid_lon);
  if(!Number.isFinite(lat)||!Number.isFinite(lon))return ring;

  // Very small connected components can be only one radar pixel wide. ProbSevere
  // style polygons need enough screen area to be visually identifiable, so gently
  // expand only genuinely tiny footprints while preserving their observed shape.
  var minLat=Math.min.apply(null,ring.map(function(x){return x[0]}));
  var maxLat=Math.max.apply(null,ring.map(function(x){return x[0]}));
  var minLon=Math.min.apply(null,ring.map(function(x){return x[1]}));
  var maxLon=Math.max.apply(null,ring.map(function(x){return x[1]}));
  var northKm=(maxLat-minLat)*111;
  var eastKm=(maxLon-minLon)*111*Math.max(.2,Math.cos(lat*Math.PI/180));
  var spanKm=Math.max(northKm,eastKm);
  var minDisplayKm=2.5;
  if(Number.isFinite(spanKm)&&spanKm>0&&spanKm<minDisplayKm){
    var scale=Math.min(3.5,minDisplayKm/spanKm);
    ring=ring.map(function(x){
      var east=(x[1]-lon)*111*Math.max(.2,Math.cos(lat*Math.PI/180));
      var north=(x[0]-lat)*111;
      return [lat+(north*scale)/111,lon+(east*scale)/(111*Math.max(.2,Math.cos(lat*Math.PI/180)))];
    });
  }
  return ring;
}
function cellPoints(p){
  var footprint=geometryPoints(p);
  if(footprint.length>=3)return footprint;
  var lat=Number(p.centroid_lat),lon=Number(p.centroid_lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return [];
  var major=Number(p.length_km);if(!Number.isFinite(major)||major<=0)major=2;
  var minor=Number(p.width_km);if(!Number.isFinite(minor)||minor<=0)minor=Math.max(1,major*.45);
  var angle=(Number(p.orientation_deg)||0)*Math.PI/180,pts=[],n=16;
  for(var i=0;i<n;i++){var t=i/n*Math.PI*2,x=Math.min(35,Math.max(1.5,major))/2*Math.cos(t),y=Math.min(20,Math.max(.8,minor))/2*Math.sin(t),east=x*Math.cos(angle)-y*Math.sin(angle),north=x*Math.sin(angle)+y*Math.cos(angle);pts.push([lat+north/111,lon+east/(111*Math.max(.2,Math.cos(lat*Math.PI/180)))])}
  return pts;
}
function selectObject(p){
  lastObjectClickAt=Date.now();
  selected=p;
  renderMap();
  renderInventory();
  renderObjectCard();
  renderProbability();
  renderKeyTrends();
  renderEnvironment();
  renderEvidence();
  renderHistory();
  renderModelStatus();
}
function renderMap(){
  Object.values(layers).forEach(function(l){l.clearLayers()});
  if(!allObjects.length)return;
  allObjects.forEach(function(p){
    var c=objectRisk(p),sel=selected&&selected.radar_site===p.radar_site&&String(selected.track_id)===String(p.track_id);
    var feature=p.radar_geometry?{type:"Feature",geometry:p.radar_geometry,properties:{}}:null;
    var pts=cellPoints(p);
    if(!feature&&!pts.length)return;
    var tooltip="<b>OBJECT "+objectOrdinal(p)+"</b><br>"+p.radar_site+" • Track "+p.track_id+"<br>"+num(p.max_reflectivity_dbz,0)+" dBZ • "+num(p.area_km2,0)+" km²<br>Click for attributes";

    // Display the actual radar-derived meteorological footprint, colored by Snow Squall probability.
    // Only fall back to a dimension-based shape when no usable footprint was published.
    var visual;
    if(pts.length){
      visual=L.polygon(pts,{
        color:sel?"#fff":c,
        weight:sel?3.5:2.5,
        fillColor:c,
        fillOpacity:sel?.52:.30,
        opacity:sel?1:.96,
        interactive:true,
        lineJoin:"round",
        lineCap:"round"
      }).addTo(layers[p.radar_site]);
    }else{
      visual=L.geoJSON(feature,{
        style:{color:sel?"#fff":c,weight:sel?3.5:2.5,fillColor:c,fillOpacity:sel?.52:.30,opacity:sel?1:.96,interactive:true}
      }).addTo(layers[p.radar_site]);
    }
    visual.bindTooltip(tooltip,{sticky:true});
    visual.on("click",function(e){if(e&&e.originalEvent)L.DomEvent.stopPropagation(e.originalEvent);selectObject(p)});

    // Show the persisted track path for the selected object. This is the
    // observed path, not a projected future track, and makes stable identity
    // visible across successive radar scans.
    var trackTrail=Array.isArray(p.track_position_history)?p.track_position_history.map(function(h){
      var tlat=Number(h&&h.lat),tlon=Number(h&&h.lon);
      return Number.isFinite(tlat)&&Number.isFinite(tlon)?[tlat,tlon]:null;
    }).filter(Boolean):[];
    if(sel&&trackTrail.length>1){
      L.polyline(trackTrail,{
        color:"#fff",
        weight:2.4,
        opacity:.9,
        dashArray:"5 4",
        interactive:false,
        lineCap:"round",
        lineJoin:"round"
      }).addTo(layers.motion);
    }

    var hitLat=Number(p.centroid_lat),hitLon=Number(p.centroid_lon);
    if(Number.isFinite(hitLat)&&Number.isFinite(hitLon)){var hit=L.circleMarker([hitLat,hitLon],{pane:"liveHitPane",radius:18,color:"#fff",weight:1,opacity:0.01,fillColor:"#fff",fillOpacity:0.01,interactive:true}).addTo(layers[p.radar_site]);hit.on("click",function(e){if(e&&e.originalEvent)L.DomEvent.stopPropagation(e.originalEvent);selectObject(p)});}


    var lat=Number(p.centroid_lat),lon=Number(p.centroid_lon);
    if(objectNumbers&&Number.isFinite(lat)&&Number.isFinite(lon)){
      var lab=L.marker([lat,lon],{
        icon:L.divIcon({
          className:"sq-object-label-wrap",
          iconSize:null,
          iconAnchor:[0,0],
          html:"<div class='sq-object-label "+(sel?"":"dim")+"'>"+objectOrdinal(p)+"</div>"
        }),
        interactive:true
      });
      lab.addTo(layers.labels);
      lab.on("click",function(e){if(e&&e.originalEvent)L.DomEvent.stopPropagation(e.originalEvent);selectObject(p)});
      lab.bindTooltip("OBJECT "+objectOrdinal(p)+" • "+p.radar_site+" • "+num(p.max_reflectivity_dbz,0)+" dBZ",{direction:"top",offset:[0,-8]});
    }

    var speed=Number(p.motion_speed_kt),dir=Number(p.motion_direction_deg??p.motion_dir_deg);
    if(Number.isFinite(speed)&&Number.isFinite(dir)&&speed<=75){
      var km=Math.max(5,Math.min(14,4+speed*.18)),br=dir*Math.PI/180;
      var lat2=lat+km*Math.cos(br)/111;
      var lon2=lon+km*Math.sin(br)/(111*Math.max(.2,Math.cos(lat*Math.PI/180)));
      L.polyline([[lat,lon],[lat2,lon2]],{
        color:sel?"#fff":"#d7e7ef",weight:sel?2.7:1.4,opacity:sel?.95:.72,interactive:false
      }).addTo(layers.motion);
      L.circleMarker([lat2,lon2],{
        radius:sel?4:2.5,color:sel?"#fff":"#d7e7ef",fillColor:"#fff",fillOpacity:.85,weight:0,interactive:false
      }).addTo(layers.motion);
    }
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
  var rows=trackHistory(p),last=rows.at(-1)||p,first=rows[0]||p,dist=haversineMi(p.centroid_lat,p.centroid_lon,BTV[0],BTV[1]),speed=Number(p.motion_speed_kt),dir=Number(p.motion_direction_deg??p.motion_dir_deg),age=Number(p.age_scans);
  q("objectAccent").style.background=objectRisk(p);
  setText("objectTitle","OBJECT "+objectOrdinal(p));
  setText("objectSubtitle",p.radar_site+" • Track "+p.track_id);
  setText("objectTime",fmtTime(p.timestamp));
  var z=Number(p.max_reflectivity_dbz);setText("objectBadge",riskScore(p)>=.70?"ELEVATED":riskScore(p)>=.45?"WATCH":"CANDIDATE");
  setText("objectTrack",p.radar_site+" • "+p.track_id);
  setText("objectLatLon",num(p.centroid_lat,2)+"°N / "+num(Math.abs(Number(p.centroid_lon)),2)+"°W");
  setText("objectMotion",Number.isFinite(speed)?Math.round(speed)+" kt • "+num(dir,0)+"° ("+compass(dir)+")":"Motion —");
  setText("objectDistance",Number.isFinite(dist)?num(dist,0)+" mi":"—");
  setText("objectAge",Number.isFinite(age)?age+" scans":"< 1 scan");
  setText("objectDuration",durationText(rows));
  setText("objectQuality",p.track_quality||p.data_quality||"—");
  setText("objectDataQuality",p.data_quality||"good");
}
function renderProbability(){
  var p=latestForSelected();if(!p){return}
  var probs=p.research_probabilities||{};
  var horizons=[15,30,45,60];
  var nowScore=p.research_probability_now??p.probability_now??probs.now;
  if(nowScore==null) nowScore=probs["15min"]??probs["15"]??p.probability_15min;
  var prevRows=trackHistory(p).slice(0,-1),prev=prevRows.length?prevRows.at(-1):null;
  var prevNow=prev?.research_probability_now??prev?.probability_now??prev?.research_probabilities?.now;
  if(prevNow==null&&prev) prevNow=prev.research_probabilities?.["15min"]??prev.research_probabilities?.["15"]??null;
  if(nowScore==null){
    q("probabilityValue").classList.add("na");setText("probabilityValue","—");setText("probabilityDelta","Awaiting weighted score");q("probabilityDelta").className="prob-delta flat";
    setText("probabilityNote","Research component score is waiting for a usable radar/environment object record. Analog guidance remains provisional.");
  }else{
    q("probabilityValue").classList.remove("na");setText("probabilityValue",(Number(nowScore)*100).toFixed(1)+"%");
    var d=prevNow==null?null:Number(nowScore)-Number(prevNow);
    setText("probabilityDelta",d==null?"Current weighted score":(d>=0?"▲ +":"▼ ")+(Math.abs(d)*100).toFixed(1)+" pp");
    q("probabilityDelta").className="prob-delta "+(d==null?"flat":d>=0?"up":"down");
    setText("probabilityNote","NOW = current object-state score • +15/+30/+45/+60 = forward guidance. Research only; Radar 50% + Environment 50%.");
  }
  var radar=p.radar_component_score,env=p.environment_component_score;
  var cards=[
    ["RADAR","50%",radar,"#ff5648"],
    ["ENVIRONMENT","50%",env,"#62ce73"]
  ];
  var cardHtml=cards.map(function(x){return "<div class='prob-component'><span><i class='comp-dot' style='background:"+x[3]+"'></i>"+x[0]+" <small style='color:#748a9b'>("+x[1]+")</small></span><b>"+(x[2]==null?"—":Number(x[2]).toFixed(1)+"%")+"</b></div>"}).join("");
  var horizonHtml="<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-top:7px'>"+horizons.map(function(h){var v=probs[h+"min"]??probs[String(h)];return "<div style='border:1px solid rgba(190,210,220,.14);padding:5px;text-align:center'><span style='display:block;font-size:8px;color:#748a9b'>+"+h+" MIN</span><b style='font-size:13px'>"+(v==null?"—":(Number(v)*100).toFixed(1)+"%")+"</b></div>"}).join("")+"</div>";
  q("probComponents").innerHTML=cardHtml+horizonHtml+"<div style='margin-top:6px;font-size:8px;color:#748a9b'>NOW = current weighted state. Forward horizons use the transparent radar/environment projection.</div>";
  renderProbabilityChart(trackHistory(p));
}
function renderProbabilityChart(hist){
  var svg=q("probChart");svg.innerHTML="";
  var rows=(hist||[]).filter(function(r){
    var v=r.research_probability_now??r.probability_now??r.research_probabilities?.now;
    if(v==null)v=r.research_probabilities?.["15min"]??r.research_probabilities?.["15"];
    return Number.isFinite(Number(v));
  });
  if(!rows.length){
    svg.innerHTML="<text x='210' y='70' text-anchor='middle' class='chart-text'>Observed probability history is warming up</text>";
    setText("probabilityChartState","WAITING FOR OBSERVATIONS");
    return;
  }

  var W=420,H=142,P=24,TOP=16,BOTTOM=24;
  var latest=rows.at(-1);
  var latestTime=new Date(latest.timestamp||Date.now()).getTime();
  var observed=rows.map(function(r){
    var t=new Date(r.timestamp||latest.timestamp).getTime();
    var v=r.research_probability_now??r.probability_now??r.research_probabilities?.now;
    if(v==null)v=r.research_probabilities?.["15min"]??r.research_probabilities?.["15"];
    return {x:(t-latestTime)/60000,v:Number(v)};
  }).filter(function(pt){return Number.isFinite(pt.x)&&Number.isFinite(pt.v)});

  var latestProbs=latest.research_probabilities||{};
  var currentNow=latest.research_probability_now??latest.probability_now??latestProbs.now;
  if(currentNow==null)currentNow=latestProbs["15min"]??latestProbs["15"]??latest.probability_15min;
  var forecast=[
    [0,Number(currentNow)],
    [15,Number(latestProbs["15"]??latestProbs["15min"])],
    [30,Number(latestProbs["30"]??latestProbs["30min"])],
    [45,Number(latestProbs["45"]??latestProbs["45min"])],
    [60,Number(latestProbs["60"]??latestProbs["60min"])]
  ].filter(function(pt){return Number.isFinite(pt[1])});

  var minX=Math.min(-60,observed.length?Math.min.apply(null,observed.map(function(pt){return pt.x})):0);
  var maxX=60;
  var x=function(v){return P+(v-minX)/(maxX-minX)*(W-2*P)};
  var y=function(v){return H-BOTTOM-Math.max(0,Math.min(1,v))*(H-TOP-BOTTOM)};

  [0,.25,.5,.75,1].forEach(function(v){
    var yy=y(v);
    svg.innerHTML+="<line x1='"+P+"' y1='"+yy+"' x2='"+(W-P)+"' y2='"+yy+"' class='chart-gridline'/><text x='"+(P-4)+"' y='"+(yy+3)+"' text-anchor='end' class='chart-text'>"+Math.round(v*100)+"</text>";
  });
  svg.innerHTML+="<line x1='"+P+"' y1='"+(H-BOTTOM)+"' x2='"+(W-P)+"' y2='"+(H-BOTTOM)+"' class='chart-axis'/>";
  svg.innerHTML+="<text x='"+x(minX)+"' y='"+(H-7)+"' text-anchor='start' class='chart-text'>"+Math.round(minX)+"m</text>";
  svg.innerHTML+="<text x='"+x(0)+"' y='"+(H-7)+"' text-anchor='middle' class='chart-text'>NOW</text>";
  svg.innerHTML+="<text x='"+x(60)+"' y='"+(H-7)+"' text-anchor='end' class='chart-text'>+60m</text>";

  if(observed.length){
    var observedPath=observed.map(function(pt,n){return (n?"L":"M")+x(pt.x).toFixed(1)+" "+y(pt.v).toFixed(1)}).join(" ");
    svg.innerHTML+="<path d='"+observedPath+"' class='prob-observed'/>";
    observed.forEach(function(pt){svg.innerHTML+="<circle cx='"+x(pt.x).toFixed(1)+"' cy='"+y(pt.v).toFixed(1)+"' r='2.5' fill='#eaf4f8'/>"});
  }

  if(forecast.length){
    var forecastPath=forecast.map(function(pt,n){return (n?"L":"M")+x(pt[0]).toFixed(1)+" "+y(pt[1]).toFixed(1)}).join(" ");
    svg.innerHTML+="<path d='"+forecastPath+"' class='prob-forecast'/>";
    forecast.forEach(function(pt){svg.innerHTML+="<circle cx='"+x(pt[0]).toFixed(1)+"' cy='"+y(pt[1]).toFixed(1)+"' r='2.5' fill='#6fb8e5'/>"});
  }

  svg.innerHTML+="<line x1='"+x(0)+"' y1='"+TOP+"' x2='"+x(0)+"' y2='"+(H-BOTTOM)+"' class='prob-now'/>";
  setText("probabilityChartState",forecast.length>1?"NOW / FORECAST":"NOW ONLY");
}
function renderKeyTrends(){
  var p=latestForSelected();if(!p){q("keyTrends").innerHTML="";return}var rows=trackHistory(p),first=rows[0]||p;
  var delta=function(a,b){var x=Number(a),y=Number(b);return Number.isFinite(x)&&Number.isFinite(y)?x-y:null}
  var items=[["MAX REFLECTIVITY",num(p.max_reflectivity_dbz,0)+" dBZ",delta(p.max_reflectivity_dbz,first.max_reflectivity_dbz),"dBZ"],["OBJECT AREA",num(p.area_km2,0)+" km²",delta(p.area_km2,first.area_km2),"km²"],["MOTION SPEED",num(p.motion_speed_kt,0)+" kt",delta(p.motion_speed_kt,first.motion_speed_kt),"kt"],["FEATURE COVERAGE",shadowRecord(p.radar_site,p.track_id)?.feature_coverage?.["15"]?.fraction==null?"—":(Number(shadowRecord(p.radar_site,p.track_id).feature_coverage["15"].fraction)*100).toFixed(0)+"%",null,""]];
  q("keyTrends").innerHTML=items.map(function(x){var d=x[2];return "<div class='trend-tile'><div class='label'>"+x[0]+"</div><div class='value'>"+x[1]+"</div><div class='delta "+(d==null?"neutral":"")+"'>"+(d==null?"Live snapshot":(d>=0?"▲ +":"▼ ")+Math.abs(d).toFixed(0)+" "+x[3])+"</div></div>"}).join("");
}
function fmtLiveEnv(v,key){if(v==null)return "—";if(key==="pwat_mm")return num(Number(v)/25.4,2)+" in";if(key.indexOf("cape")>=0||key.indexOf("cin")>=0||key==="dcape_jkg")return num(v,0);if(key==="srh01_m2s2"||key.indexOf("shear")>=0&&key!=="shear_0_6km_ms")return num(v,0);return num(v,1)}
function envRiskClass(key,val){
  if(val==null||!Number.isFinite(Number(val)))return "env-risk-na";
  var v=Number(val),y=null,r=null,hi=true;
  // Snow-squall-oriented traffic-light guidance. These are diagnostic
  // context thresholds, not independent probability triggers.
  if(key==="cape_jkg"||key==="mlcape_jkg"||key==="mucape_jkg"){y=25;r=75}
  else if(key==="mlcin_jkg"){y=-100;r=-25;hi=false}
  else if(key==="dcape_jkg"){y=300;r=600}
  else if(key==="pwat_mm"){y=8;r=15}
  else if(key==="lcl_m"){y=1500;r=1000;hi=false}
  else if(key==="lfc_m"){y=2000;r=1500;hi=false}
  else if(key==="srh01_m2s2"){y=25;r=75}
  else if(key==="shear_0_1km_kt"){y=15;r=25}
  else if(key==="shear_0_3km_kt"){y=20;r=30}
  else if(key==="shear_0_6km_kt"){y=25;r=40}
  else if(key==="lapse_rate_0_3km_c_km"){y=6;r=7}
  else if(key==="lapse_rate_0_7_5km_c_km"){y=5.5;r=7}
  else if(key==="mean_rh_0_2km_pct"){y=60;r=75}
  else if(key==="thetae_delta_0_2km_k"){y=4;r=0;hi=false}
  else if(key==="mean_wind_0_2km_ms"){y=9;r=13.1}
  else if(key==="snsq"){y=.5;r=1}
  else if(key==="freezing_level_m"){y=1000;r=500;hi=false}
  else if(key==="visibility_m"){y=4000;r=800;hi=false}
  else if(key==="gust_ms"){y=10;r=18}
  else if(key==="wetbulb_2m_c"){y=1;r=-1;hi=false}
  else if(key==="rh_2m_pct"){y=60;r=75}
  else if(key==="temperature_2m_k"){y=275.15;r=273.15;hi=false}
  else if(key==="dewpoint_2m_k"){y=273.15;r=270.15;hi=false}
  else if(key==="el_m"){y=3000;r=1500;hi=false}
  else return "env-risk-neutral";
  var s=hi?(v<=y?0:v>=r?1:(v-y)/(r-y)):(v>=y?0:v<=r?1:(y-v)/(y-r));
  return s>=1?"env-risk-red":s>0?"env-risk-yellow":"env-risk-green";
}
function renderEnvironment(){
  var p=latestForSelected();if(!p){q("environmentTable").innerHTML="";return}
  var fields=[
    ["SBCAPE","cape_jkg"],["MLCAPE","mlcape_jkg"],["MUCAPE","mucape_jkg"],["MLCIN","mlcin_jkg"],["DCAPE","dcape_jkg"],["PWAT (in)","pwat_mm"],["LCL","lcl_m"],["LFC","lfc_m"],["EL","el_m"],
    ["0–1 km SRH","srh01_m2s2"],["0–1 km shear","shear_0_1km_kt"],["0–3 km shear","shear_0_3km_kt"],["0–6 km shear","shear_0_6km_kt"],
    ["0–3 km lapse","lapse_rate_0_3km_c_km"],["0–7.5 km lapse","lapse_rate_0_7_5km_c_km"],["Freezing level","freezing_level_m"],
    ["2 m temperature","temperature_2m_k"],["2 m dewpoint","dewpoint_2m_k"],["2 m RH","rh_2m_pct"],["Surface gust","gust_ms"],
    ["SNSQ","snsq"],["SNSQ 0–2 km RH","mean_rh_0_2km_pct"],["SNSQ Δθe 0–2 km","thetae_delta_0_2km_k"],["SNSQ 0–2 km wind","mean_wind_0_2km_ms"],["2 m wet-bulb","wetbulb_2m_c"]
  ];
  var rows=trackHistory(p),current=p,prev=rows.length>1?rows[Math.max(0,rows.length-2)]:null;
  var forecast=p.environment_forecast_30min||{},forecastFields=forecast.fields||{};
  var forecastReady=p.environment_forecast_30min_model_ready;
  var format=function(val,key){
    if(val==null)return "—";
    if(key==="temperature_2m_k"||key==="dewpoint_2m_k")return num(kToC(val),1)+" °C";
    if(key==="gust_ms"||key==="mean_wind_0_2km_ms")return num(msToKt(val),0)+" kt";
    if(key==="shear_0_1km_kt"||key==="shear_0_3km_kt"||key==="shear_0_6km_kt")return num(val,0)+" kt";
    if(key==="lapse_rate_0_3km_c_km"||key==="lapse_rate_0_7_5km_c_km")return num(val,2)+" °C/km";
    if(key==="lcl_m"||key==="lfc_m"||key==="el_m"||key==="freezing_level_m")return num(val/1000,2)+" km";
    if(key==="wetbulb_2m_c")return num(val,1)+" °C";
    return fmtLiveEnv(val,key);
  };
  var html="<div class='env-grid-row env-grid-head' role='row'><div role='columnheader'>Parameter</div><div role='columnheader'>−30 min</div><div role='columnheader'>Current</div><div role='columnheader'>Expected +30 min</div></div>";
  html+=fields.map(function(x){
    var pv=prev?envField(prev,x[1]):null,cv=envField(current,x[1]),nv=forecastFields[x[1]];
    return "<div class='env-grid-row' role='row'><div class='env-grid-name' role='rowheader'>"+x[0]+"</div><div class='"+envRiskClass(x[1],pv)+"' role='cell'>"+format(pv,x[1])+"</div><div class='"+envRiskClass(x[1],cv)+"' role='cell'>"+format(cv,x[1])+"</div><div class='"+envRiskClass(x[1],nv)+" "+(forecastReady?"":"env-risk-na")+"' role='cell'>"+format(nv,x[1])+"</div></div>";
  }).join("");
  q("environmentTable").innerHTML=html;
  var e=p.environment||{},forecastLabel=forecast.valid_time_utc||forecast.forecast_valid_time_utc,derivedCount=(e.metpy_derived_fields||[]).length;
  setText("envSource",(e.source||p.environment_source||"RAP")+(e.age_minutes==null?"":" • analysis "+num(e.age_minutes,0)+" min old")+(derivedCount?" • MetPy "+derivedCount+" derived":"")+" • forecast "+(forecastLabel?fmtTime(forecastLabel):"unavailable")+(forecast.actual_valid_offset_minutes==null?"":" (+"+num(forecast.actual_valid_offset_minutes,0)+" min)"));
}
function evidenceItem(icon,cls,title,body){return "<div class='evidence-card'><div class='evidence-icon "+(cls||"")+"'>"+icon+"</div><div><b>"+title+"</b><span>"+body+"</span></div></div>"}
function renderEvidence(){
  var p=latestForSelected();if(!p){q("evidenceGrid").innerHTML="";return}
  var e=p.environment||{},f=e.fields||{},gust=fieldValue(f,"gust_ms")??fieldValue(e,"gust_ms")??p.gust_ms,geo=datasets[p.radar_site]?.geo,fields=geo?.metadata?.fields||{};
  var mping=p.mping_reports||p.mping_count||p.mping_support,shadow=shadowRecord(p.radar_site,p.track_id),cov=shadow?.feature_coverage?.["15"]?.fraction;
  q("evidenceGrid").innerHTML=
    evidenceItem(gust!=null?"✓":"—",gust!=null?"":"warn","METAR / ASOS context",gust!=null?"Surface gust "+num(msToKt(gust),0)+" kt":"Surface observation not attached to this object")+
    evidenceItem(mping?"✓":"—",mping?"":"warn","MPING reports",mping?(String(mping)+" attached report(s)"):"No MPING report field in current live object")+
    evidenceItem(cov!=null&&cov>=SHADOW_MIN_COVERAGE?"✓":"!",cov!=null&&cov>=SHADOW_MIN_COVERAGE?"":"warn","Model feature coverage",cov==null?"No candidate score package attached":(Number(cov)*100).toFixed(0)+"% of 15-min predictors available • research threshold ≥"+(SHADOW_MIN_COVERAGE*100).toFixed(0)+"%")+
    evidenceItem(fields.velocity?"✓":"!",fields.velocity?"":"warn","Radar inputs",fields.velocity?"Base velocity present • dual-pol fields tracked": "Radar velocity field not confirmed in feed metadata")+
    evidenceItem(p.environment_forecast_30min_model_ready?"✓":"!",p.environment_forecast_30min_model_ready?"":"warn","RAP +30 min forecast",p.environment_forecast_30min_model_ready?"Expected conditions attached for the +30 minute horizon":"Waiting for a usable RAP forecast at +30 minutes");
}
function renderHistory(){
  var p=latestForSelected(),rows=p?trackHistory(p):[];setText("historyCount",rows.length+" retained scans");if(!rows.length){q("historyChart").innerHTML="<text x='260' y='70' text-anchor='middle' class='chart-text'>No retained track history</text>";q("historyTable").innerHTML="";return}
  var W=520,H=145,P=28,vals=rows.map(function(r){return {z:Number(r.max_reflectivity_dbz),a:Number(r.area_km2),m:Number(r.motion_speed_kt)}}),z=vals.map(x=>x.z).filter(Number.isFinite),a=vals.map(x=>x.a).filter(Number.isFinite),m=vals.map(x=>x.m).filter(Number.isFinite),minZ=z.length?Math.min(...z):0,maxZ=z.length?Math.max(...z):1,minA=a.length?Math.min(...a):0,maxA=a.length?Math.max(...a):1,minM=m.length?Math.min(...m):0,maxM=m.length?Math.max(...m):1;
  var norm=function(v,min,max){return Number.isFinite(v)?(v-min)/(Math.max(.001,max-min)):null};var x=function(i){return P+(rows.length===1?0:i*(W-2*P)/(rows.length-1))},y=function(v){return H-P-v*(H-2*P)},svg="<line x1='"+P+"' y1='"+(H-P)+"' x2='"+(W-P)+"' y2='"+(H-P)+"' class='chart-axis'/><text x='3' y='12' class='chart-text'>100</text><text x='7' y='"+(H/2+3)+"' class='chart-text'>50</text><text x='7' y='"+(H-P+3)+"' class='chart-text'>0</text>";
  [["max_reflectivity_dbz","#d34bc0",minZ,maxZ,"z"],["area_km2","#1f90e9",minA,maxA,"a"],["motion_speed_kt","#54c56b",minM,maxM,"m"]].forEach(function(line){var path=rows.map(function(r,i){var key=line[4],val=norm(Number(r[key]),line[2],line[3]);return val==null?null:(i?"L":"M")+x(i).toFixed(1)+" "+y(val).toFixed(1)}).filter(Boolean).join(" ");if(path)svg+="<path d='"+path+"' fill='none' stroke='"+line[1]+"' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'/>"});
  var xx=x(rows.length-1);svg+="<line x1='"+xx+"' y1='"+P+"' x2='"+xx+"' y2='"+(H-P)+"' class='chart-current'/>";q("historyChart").innerHTML=svg+"<text x='"+P+"' y='"+(H-2)+"' class='chart-text'>"+fmtTime(rows[0].timestamp)+"</text><text x='"+(W-P)+"' y='"+(H-2)+"' text-anchor='end' class='chart-text'>"+fmtTime(rows.at(-1).timestamp)+"</text>";
  q("historyTable").innerHTML="<thead><tr><th>Time</th><th>Max Z</th><th>Area</th><th>L × W</th><th>Motion</th><th>Z trend</th><th>Env</th></tr></thead><tbody>"+rows.slice(-60).reverse().map(function(r){var cur=p&&String(r.timestamp)===String(p.timestamp);return "<tr class='"+(cur?"current":"")+"' data-ts='"+esc(r.timestamp)+"'><td>"+fmtTime(r.timestamp)+"</td><td>"+num(r.max_reflectivity_dbz,0)+" dBZ</td><td>"+num(r.area_km2,0)+" km²</td><td>"+num(r.length_km,1)+" × "+num(r.width_km,1)+" km</td><td>"+num(r.motion_speed_kt,0)+" kt</td><td>"+num(r.reflectivity_trend_dbz_per_hr,1)+"</td><td>"+esc(r.environment_status||"—")+"</td></tr>"}).join("")+"</tbody>";
}
function renderModelStatus(){
  var rows=Object.values(datasets).filter(function(x){return x.shadow}).map(function(x){var s=x.shadow;return {site:x.site,scored:s.scored_object_count||0,total:s.current_object_count||0,status:s.operational_release_status||"unknown"}});
  var selectedShadow=selected?shadowRecord(selected.radar_site,selected.track_id):null,cov=selectedShadow?.feature_coverage?.["15"]?.fraction;
  setText("modelStatus",cov==null?"NO SCORE":(cov>=SHADOW_MIN_COVERAGE?"RESEARCH SCORE READY":"GATED"));
  q("modelStatusCard").innerHTML=rows.map(function(r){return "<div class='status-cell'><span>"+r.site+" shadow</span><b>"+r.scored+" / "+r.total+" scored</b></div>"}).join("")+
    "<div class='status-cell'><span>15-min coverage</span><b>"+(cov==null?"—":(Number(cov)*100).toFixed(0)+"%")+"</b></div>"+
    "<div class='status-cell'><span>Release</span><b>Candidate only</b></div>";
  q("liveGate").style.display="flex";
  setText("liveGateText",cov==null?"Research shadow data are not attached to this object yet.":(Number(cov)*100).toFixed(0)+"% 15-min feature coverage; research candidate scoring is enabled at ≥"+(SHADOW_MIN_COVERAGE*100).toFixed(0)+"%. Operational release remains gated.");
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
    cursorGrid=await fetchOptional(LIVE_BASE+"radar_cursor.json?cb="+Date.now(),null);
    await loadRadarHistory();
    var detectedObjects=got.flatMap(function(x){var scan=x.state?.last_scan_time_utc||x.geo?.metadata?.scan_time_utc; var fresh=ageMinutes(scan)<=MAX_LIVE_OBJECT_AGE_MIN; return fresh?(x.geo.features||[]).map(function(f){return Object.assign({},f.properties,{radar_site:x.site,radar_geometry:f.geometry})}):[]});
    // Keep every valid detected radar object visible. Detection/tracking and
    // hazard ranking are separate concepts: a cell can be trackable before it
    // reaches the research probability/rank threshold.
    allObjects=detectedObjects.filter(function(p){
      var lat=Number(p.centroid_lat),lon=Number(p.centroid_lon),area=Number(p.area_km2);
      return Number.isFinite(lat)&&Number.isFinite(lon)&&Number.isFinite(area)&&area>0;
    });
    allObjects.sort(function(a,b){var d=riskScore(b)-riskScore(a);return d||Number(b.max_reflectivity_dbz||0)-Number(a.max_reflectivity_dbz||0)});
    selectDefault();
    alignRadarHistoryToObjects();
    await renderRadarMosaic();
    renderMap();renderInventory();renderObjectCard();renderProbability();renderKeyTrends();renderEnvironment();renderEvidence();renderHistory();renderModelStatus();
    var latest=got.map(function(x){return x.state?.last_scan_time_utc||x.geo?.metadata?.scan_time_utc}).filter(Boolean).sort().at(-1);
    setText("liveTime",latest?fmtTime(latest):"No scan time available");
    setText("mapScanLabel",latest?fmtTime(latest):"No live radar");
    setText("feedSummary",(allObjects.length)+" tracked objects • "+detectedObjects.length+" radar detections • "+got.map(function(x){return x.site+" "+(x.error?"OFFLINE":(ageMinutes(x.state?.last_scan_time_utc)<=15?"LIVE":(ageMinutes(x.state?.last_scan_time_utc)<=45?"AGING":"STALE")))}).join(" • "));
    var degraded=got.filter(function(x){return x.error||ageMinutes(x.state?.last_scan_time_utc)>30}).length>0;
    q("liveBadge").classList.toggle("gated",degraded);if(degraded)setText("liveBadge","DEGRADED");
  }catch(e){setText("feedSummary","Live feed error: "+e.message);q("liveBadge").classList.add("gated");setText("liveBadge","DEGRADED")}
}
document.querySelectorAll(".display-btn").forEach(function(b){b.onclick=function(){setRadarMode(b.dataset.radarMode)}});
document.querySelectorAll("[data-jump]").forEach(function(btn){btn.onclick=function(){var el=q(btn.dataset.jump);if(el)el.scrollIntoView({behavior:"smooth",block:"start"});document.querySelectorAll("[data-jump]").forEach(function(b){b.classList.toggle("active",b===btn)})}});
q("refreshBtn").onclick=refresh;q("refreshBtn2").onclick=refresh;
q("radarPlayBtn").onclick=playRadarAnimation;
q("radarTimelineSlider").oninput=function(){setRadarHistoryIndex(this.value)};
q("objectNumbersBtn").onclick=function(){objectNumbers=!objectNumbers;q("objectNumbersBtn").classList.toggle("active",objectNumbers);renderMap()};
document.addEventListener("keydown",function(e){
  if(e.defaultPrevented||e.ctrlKey||e.metaKey||e.altKey)return;
  var target=e.target;
  if(target&&(target.tagName==="INPUT"||target.tagName==="SELECT"||target.tagName==="TEXTAREA"||target.tagName==="BUTTON"||target.isContentEditable))return;
  if(e.key==="ArrowLeft"||e.key==="ArrowRight"){
    var frames=radarHistory.frames||[];
    if(!frames.length)return;
    e.preventDefault();
    e.stopPropagation();
    var step=e.key==="ArrowLeft"?-1:1;
    var next=radarHistoryIndex<0?frames.length-1:radarHistoryIndex+step;
    next=Math.max(0,Math.min(frames.length-1,next));
    setRadarHistoryIndex(next);
  }
});

map.on("click",function(e){
  if(Date.now()-lastObjectClickAt<300)return;
  var matches=[];
  allObjects.forEach(function(p){
    var lat=Number(p.centroid_lat),lon=Number(p.centroid_lon);
    if(!Number.isFinite(lat)||!Number.isFinite(lon))return;
    var feature=p.radar_geometry?{type:"Feature",geometry:p.radar_geometry,properties:{}}:null;
    var bounds=feature?L.geoJSON(feature).getBounds():null;
    if(bounds&&bounds.isValid()&&bounds.contains(e.latlng))matches.push(p);
    else{
      var km=haversineMi(lat,lon,e.latlng.lat,e.latlng.lng)*1.609344;
      var scale=Math.max(2.0,Math.min(8.0,Math.max(Number(p.length_km)||2,Number(p.width_km)||2)*0.6));
      if(km<=scale)matches.push(p);
    }
  });
  if(matches.length){
    matches.sort(function(a,b){return (Number(a.area_km2)||Infinity)-(Number(b.area_km2)||Infinity)});
    selectObject(matches[0]);
  }
});
bindCursorReadout();loadRadarHistory();refresh();refreshTimer=setInterval(refresh,60000);