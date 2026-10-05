// Snow Squall live viewer v15: probability cells + robust click + canonical MetPy environment

var map=L.map("liveMap",{zoomControl:true,preferCanvas:true}).setView([44.15,-73.65],8);
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
function lifecycleObjectId(p){
  if(p&&p.object_id)return String(p.object_id);
  var stamp=p?.track_first_scan_utc||p?.timestamp;
  var d=new Date(stamp||Date.now());
  if(!Number.isFinite(d.getTime()))d=new Date();
  var date=d.toISOString().slice(2,10).replace(/-/g,"");
  var n=String(p?.track_id??"").replace(/\\D/g,"");
  return date+(n?n.padStart(3,"0").slice(-3):"000");
}
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
    radarHistory.frames.sort(function(a,b){return String(a.timestamp).localeCompare(String(b.timestamp))});
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
      var wmsTime=histFrameForWms?histFrameForWms.timestamp:new Date().toISOString();
      var iem=L.tileLayer.wms("https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0r-t.cgi",{
        layers:"nexrad-n0r-wmst",format:"image/png",transparent:true,version:"1.1.1",
        opacity:.72,time:wmsTime
      });
      iem.addTo(radarLayer);
      setText("radarStatus",histFrameForWms?"IEM radar fallback • "+fmtTime(histFrameForWms.timestamp):"IEM live radar fallback • 5-minute NEXRAD mosaic");
      setText("legendTitle","REFLECTIVITY • dBZ");
      setText("legendNote","External fallback: IEM NEXRAD mosaic. Local KCXX/KTYX products resume automatically when published.");
      return;
    }
    var histFrame=radarHistoryFrame();
    if(histFrame&&radarMode==="reflectivity"){
      var histBounds=histFrame.bounds||[[41.90,-76.78],[46.40,-70.52]];
      var histName=histFrame.image.split("/").pop();
      L.imageOverlay(LIVE_BASE+"radar_history/"+histName+"?cb="+Date.now(),histBounds,{pane:"liveRadarPane",opacity:.96,interactive:false,crossOrigin:true}).addTo(radarLayer);
      setText("radarStatus","Historical radar frame • "+fmtTime(histFrame.timestamp)+" • live acquisition unavailable");
      setText("legendTitle","REFLECTIVITY • dBZ");
      setText("legendNote","Historical frame retained locally while the live radar publisher recovers.");
      if(!map._sqExtent){map.fitBounds(histBounds,{padding:[25,25],maxZoom:8});map._sqExtent=true}
      return;
    }
    if(radarMode==="velocity"){setText("radarStatus","Local velocity unavailable • waiting for Level-II volume");setText("legendTitle","RADIAL VELOCITY • kt");setText("legendNote","No retained KCXX/KTYX velocity image is currently published.");}else{setText("radarStatus","Local mosaic unavailable • NOAA QC fallback");setText("legendTitle","REFLECTIVITY • dBZ");setText("legendNote","NOAA fallback is display-only; local object analysis remains independent.");addNoaaFallback();}return}
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
    var isLatestHistoryFrame=!!(frame&&radarHistory.frames&&radarHistory.frames.length&&radarHistoryIndex===radarHistory.frames.length-1);
    var useStoredFrame=!!(frame&&frame.image&&frame.image!=="iem-wms"&&!isLatestHistoryFrame);
    var imageName=useStoredFrame?frame.image.split("/").pop():"";
    // Use the current raw reflectivity product for the newest frame. The clean
    // product intentionally removes weak echo and can look blank when the
    // precipitation is light. Historical frames remain the retained mosaic.
    var imageUrl=useStoredFrame?(LIVE_BASE+"radar_history/"+imageName+"?cb="+Date.now()):mosaicImageUrl("raw");
    var ov=L.imageOverlay(imageUrl,radarMosaic.bounds,{pane:"liveRadarPane",opacity:.96,interactive:false,crossOrigin:true});
    ov.addTo(radarLayer);
    setText("radarStatus","Reflectivity "+(isLatestHistoryFrame?"current raw mosaic":"historical mosaic")+" • "+(radarMosaic.status==="stale"?"RETAINED":"READY")+" • KCXX + KTYX");
    setText("legendTitle","REFLECTIVITY • dBZ");
    setText("legendNote","KCXX + KTYX reflectivity mosaic. Object footprints are clickable and expose full attributes.");
  }
  if(!map._sqExtent){map.fitBounds(radarMosaic.bounds,{padding:[25,25],maxZoom:8});map._sqExtent=true}
}
function setRadarMode(mode){if(mode!=="reflectivity"&&mode!=="velocity")mode="reflectivity";radarMode=mode;document.querySelectorAll(".display-btn").forEach(function(b){b.classList.toggle("active",b.dataset.radarMode===mode)});renderRadarMosaic()}
function cellPoints(p){
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

    // Display the meteorological cell shape, colored by Snow Squall probability.
    // Keep the published radar footprint as the larger click target so selection
    // remains easy even when the rendered cell shape is small.
    var visual;
    if(pts.length){
      visual=L.polygon(pts,{
        color:sel?"#fff":c,
        weight:sel?3.5:2,
        fillColor:c,
        fillOpacity:sel?.52:.24,
        opacity:sel?1:.96,
        interactive:true,
        lineJoin:"round"
      }).addTo(layers[p.radar_site]);
    }else{
      visual=L.geoJSON(feature,{
        style:{color:sel?"#fff":c,weight:sel?3.5:2,fillColor:c,fillOpacity:sel?.52:.24,opacity:sel?1:.96,interactive:true}
      }).addTo(layers[p.radar_site]);
    }
    visual.bindTooltip(tooltip,{sticky:true});
    visual.on("click",function(e){if(e&&e.originalEvent)L.DomEvent.stopPropagation(e.originalEvent);selectObject(p)});

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
  setText("objectSubtitle",p.radar_site+" • Object "+lifecycleObjectId(p)+" • Track "+p.track_id);
  setText("objectTime",fmtTime(p.timestamp)+" • "+fmtUTC(p.timestamp));
  var z=Number(p.max_reflectivity_dbz);setText("objectBadge",riskScore(p)>=.70?"ELEVATED":riskScore(p)>=.45?"WATCH":"CANDIDATE");
  setText("objectTrack",lifecycleObjectId(p)+" • "+p.radar_site+" • "+p.track_id);
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
  var shadow=shadowRecord(p.radar_site,p.track_id),hist=shadowRows(p.radar_site,p.track_id);
  var current=probValue(shadow,15),prev=hist.length>1?probValue(hist.at(-2),15):null;
  if(current==null){
    q("probabilityValue").classList.add("na");setText("probabilityValue","—");setText("probabilityDelta","GATED • waiting for coverage");q("probabilityDelta").className="prob-delta flat";
    setText("probabilityNote","Waiting for a research score. The timeline will show observed history and forward guidance when available.");
  }else{
    q("probabilityValue").classList.remove("na");setText("probabilityValue",(Number(current)*100).toFixed(1)+"%");
    var d=prev==null?null:Number(current)-Number(prev);
    setText("probabilityDelta",d==null?"Current research score":(d>=0?"▲ +":"▼ ")+(Math.abs(d)*100).toFixed(1)+" pp");
    q("probabilityDelta").className="prob-delta "+(d==null?"flat":d>=0?"up":"down");
    setText("probabilityNote","Current research score • forward guidance shown below • research/candidate only.");
  }
  var vals=[["RADAR",p.radar_component_score,"#ff5648"],["ENVIRONMENT",p.environment_component_score,"#62ce73"],["ANALOG",p.analog_component_score,"#f0c54c"]];
  if(!vals[0][1]&&!vals[1][1]&&!vals[2][1]){
    vals=[["RADAR",shadow?.radar_probability,"#ff5648"],["ENVIRONMENT",shadow?.environment_signal,"#62ce73"],["ANALOG",shadow?.analog_probability,"#f0c54c"]];
  }
  q("probComponents").innerHTML=vals.map(function(x){return "<div class='prob-component'><span><i class='comp-dot' style='background:"+x[2]+"'></i>"+x[0]+"</span><b>"+(x[1]==null?"—":(Number(x[1])*100).toFixed(1)+"%")+"</b></div>"}).join("")+"<div style='margin-top:5px;font-size:8px;color:#748a9b'>NOW/current score is shown above. +15/+30/+45/+60 are forward guidance.</div>";
  renderProbabilityChart(hist,shadow);
}
function renderProbabilityChart(hist,currentRecord){
  var svg=q("probChart");if(!svg)return;svg.innerHTML="";
  var rows=(hist||[]).filter(function(r){var v=probValue(r,15);return Number.isFinite(Number(v))}).sort(function(a,b){return String(a.timestamp).localeCompare(String(b.timestamp))});
  var currentNow=Number(currentRecord?.research_probability_now ?? currentRecord?.probability_now);
  var probs=currentRecord?.research_probabilities||{};
  var forward=[
    [0,Number.isFinite(currentNow)?currentNow:Number(probValue(currentRecord,15))],
    [15,Number(probs["15"]??probs["15min"])],
    [30,Number(probs["30"]??probs["30min"])],
    [45,Number(probs["45"]??probs["45min"])],
    [60,Number(probs["60"]??probs["60min"])]
  ].filter(function(pt){return Number.isFinite(pt[1])});
  if(!rows.length && !forward.length){
    svg.innerHTML="<text x='260' y='68' text-anchor='middle' class='chart-text'>No probability observations for this object yet</text><text x='260' y='86' text-anchor='middle' class='chart-text'>The timeline will populate as the object receives additional scans.</text>";
    setText("probabilityChartState","WAITING FOR OBJECT SCANS");return;
  }
  var W=520,H=160,P=34,TOP=16,BOTTOM=34;
  var latestT=rows.length?new Date(rows.at(-1).timestamp).getTime():Date.now();
  var observed=rows.map(function(r){return {x:(new Date(r.timestamp).getTime()-latestT)/60000,v:Number(probValue(r,15)),t:r.timestamp}}).filter(function(pt){return Number.isFinite(pt.x)&&Number.isFinite(pt.v)});
  var minObserved=observed.length?Math.min.apply(null,observed.map(function(pt){return pt.x})):-15;
  var minX=Math.min(-60,minObserved),maxX=60;
  var x=function(v){return P+(v-minX)/(maxX-minX)*(W-2*P)},y=function(v){return H-BOTTOM-Math.max(0,Math.min(1,v))*(H-TOP-BOTTOM)};
  [0,.25,.5,.75,1].forEach(function(v){var yy=y(v);svg.innerHTML+="<line x1='"+P+"' y1='"+yy+"' x2='"+(W-P)+"' y2='"+yy+"' class='chart-gridline'/><text x='"+(P-5)+"' y='"+(yy+3)+"' text-anchor='end' class='chart-text'>"+Math.round(v*100)+"</text>"});
  svg.innerHTML+="<line x1='"+P+"' y1='"+(H-BOTTOM)+"' x2='"+(W-P)+"' y2='"+(H-BOTTOM)+"' class='chart-axis'/><text x='"+x(minX)+"' y='"+(H-8)+"' text-anchor='start' class='chart-text'>"+Math.round(minX)+"m</text><text x='"+x(0)+"' y='"+(H-8)+"' text-anchor='middle' class='chart-text'>NOW</text><text x='"+x(60)+"' y='"+(H-8)+"' text-anchor='end' class='chart-text'>+60m</text>";
  if(observed.length){
    var path=observed.map(function(pt,n){return(n?"L":"M")+x(pt.x).toFixed(1)+" "+y(pt.v).toFixed(1)}).join(" ");
    svg.innerHTML+="<path d='"+path+"' class='prob-observed'/>";
    observed.forEach(function(pt){svg.innerHTML+="<circle cx='"+x(pt.x).toFixed(1)+"' cy='"+y(pt.v).toFixed(1)+"' r='2.7' class='prob-observed-dot'><title>"+fmtTime(pt.t)+" • "+(pt.v*100).toFixed(1)+"%</title></circle>"});
  }
  if(forward.length){
    var path2=forward.map(function(pt,n){return(n?"L":"M")+x(pt[0]).toFixed(1)+" "+y(pt[1]).toFixed(1)}).join(" ");
    svg.innerHTML+="<path d='"+path2+"' class='prob-forecast'/>";
    forward.forEach(function(pt){svg.innerHTML+="<circle cx='"+x(pt[0]).toFixed(1)+"' cy='"+y(pt[1]).toFixed(1)+"' r='2.4' class='prob-forecast-dot'><title>"+(pt[0]===0?"NOW":"+"+pt[0]+" min")+" • "+(pt[1]*100).toFixed(1)+"%</title></circle>"});
  }
  svg.innerHTML+="<line x1='"+x(0)+"' y1='"+TOP+"' x2='"+x(0)+"' y2='"+(H-BOTTOM)+"' class='prob-now'/>";
  setText("probabilityChartState",observed.length+" observed scan"+(observed.length===1?"":"s")+" • current + forecast");
}

function renderKeyTrends(){
  var p=latestForSelected();if(!p){q("keyTrends").innerHTML="";return}var rows=trackHistory(p),first=rows[0]||p;
  var delta=function(a,b){var x=Number(a),y=Number(b);return Number.isFinite(x)&&Number.isFinite(y)?x-y:null}
  var items=[["MAX REFLECTIVITY",num(p.max_reflectivity_dbz,0)+" dBZ",delta(p.max_reflectivity_dbz,first.max_reflectivity_dbz),"dBZ"],["OBJECT AREA",num(p.area_km2,0)+" km²",delta(p.area_km2,first.area_km2),"km²"],["MOTION SPEED",num(p.motion_speed_kt,0)+" kt",delta(p.motion_speed_kt,first.motion_speed_kt),"kt"],["FEATURE COVERAGE",shadowRecord(p.radar_site,p.track_id)?.feature_coverage?.["15"]?.fraction==null?"—":(Number(shadowRecord(p.radar_site,p.track_id).feature_coverage["15"].fraction)*100).toFixed(0)+"%",null,""]];
  q("keyTrends").innerHTML=items.map(function(x){var d=x[2];return "<div class='trend-tile'><div class='label'>"+x[0]+"</div><div class='value'>"+x[1]+"</div><div class='delta "+(d==null?"neutral":"")+"'>"+(d==null?"Live snapshot":(d>=0?"▲ +":"▼ ")+Math.abs(d).toFixed(0)+" "+x[3])+"</div></div>"}).join("");
}
function fmtLiveEnv(v,key){if(v==null)return "—";if(key.indexOf("cape")>=0||key.indexOf("cin")>=0||key==="dcape_jkg")return num(v,0);if(key==="srh01_m2s2"||key.indexOf("shear")>=0&&key!=="shear_0_6km_ms")return num(v,0);return num(v,1)}
function envRiskClass(key,val){
  if(val==null||!Number.isFinite(Number(val)))return "env-risk-na";
  var v=Number(val),y=null,r=null,hi=true;
  // Research-informed ingredient thresholds. These are display bins, not
  // calibrated probabilities; the BTV training set will eventually replace
  // them with local percentile/skill-based thresholds.
  if(key==="cape_jkg"||key==="mlcape_jkg"||key==="mucape_jkg"){y=25;r=75}
  else if(key==="dcape_jkg"){y=50;r=150}
  else if(key==="sbcin_jkg"||key==="mlcin_jkg"||key==="mucin_jkg"){y=-50;r=-10;hi=false}
  else if(key==="mean_rh_0_2km_pct"){y=60;r=75}
  else if(key==="thetae_delta_0_2km_k"){y=4;r=0;hi=false}
  else if(key==="mean_wind_0_2km_ms"){y=9;r=13.1}
  else if(key==="snsq"){y=.6;r=1}
  else if(key==="lapse_rate_0_3km_c_km"){y=6;r=7}
  else if(key==="shear_0_1km_kt"){y=10;r=20}
  else if(key==="shear_0_3km_kt"){y=15;r=25}
  else if(key==="shear_0_6km_kt"){y=25;r=35}
  else if(key==="srh01_m2s2"){y=25;r=75}
  else return "env-risk-neutral";
  var s=hi?(v<=y?0:v>=r?1:(v-y)/(r-y)):(v>=y?0:v<=r?1:(y-v)/(y-r));
  return s>=1?"env-risk-red":s>0?"env-risk-yellow":"env-risk-green";
}
function renderEnvironment(){
  var p=latestForSelected();if(!p){q("environmentTable").innerHTML="";return}
  var fields=[
    ["SBCAPE","cape_jkg"],["MLCAPE","mlcape_jkg"],["MUCAPE","mucape_jkg"],["DCAPE","dcape_jkg"],
    ["SBCIN","sbcin_jkg"],["MLCIN","mlcin_jkg"],["MUCIN","mucin_jkg"],
    ["0–1 km shear","shear_0_1km_kt"],["0–3 km shear","shear_0_3km_kt"],["0–6 km shear","shear_0_6km_kt"],["0–1 km SRH","srh01_m2s2"],
    ["0–3 km lapse","lapse_rate_0_3km_c_km"],
    ["SNSQ","snsq"],["SNSQ 0–2 km RH","mean_rh_0_2km_pct"],["SNSQ Δθe 0–2 km","thetae_delta_0_2km_k"],["SNSQ 0–2 km wind","mean_wind_0_2km_ms"]
  ];
  var rows=trackHistory(p),current=p,prev=rows.length>1?rows[Math.max(0,rows.length-2)]:null;
  var forecast=p.environment_forecast_30min||{},forecastFields=forecast.fields||{},forecastReady=p.environment_forecast_30min_model_ready;
  var format=function(val,key){
    if(val==null)return "—";
    if(key==="gust_ms"||key==="mean_wind_0_2km_ms")return num(msToKt(val),0)+" kt";
    if(key==="shear_0_1km_kt"||key==="shear_0_3km_kt"||key==="shear_0_6km_kt")return num(val,0)+" kt";
    if(key==="srh01_m2s2")return num(val,0)+" m²/s²";
    if(key==="lapse_rate_0_3km_c_km")return num(val,2)+" °C/km";
    return fmtLiveEnv(val,key);
  };
  var html="<div class='env-grid-row env-grid-head' role='row'><div role='columnheader'>Ingredient</div><div role='columnheader'>−30 min</div><div role='columnheader'>Current</div><div role='columnheader'>Expected +30 min</div></div>";
  html+=fields.map(function(x){
    var pv=prev?envField(prev,x[1]):null,cv=envField(current,x[1]),nv=forecastFields[x[1]];
    var pc=envRiskClass(x[1],pv),cc=envRiskClass(x[1],cv),nc=envRiskClass(x[1],nv);
    if(!forecastReady&&nv==null)nc="env-risk-na";
    return "<div class='env-grid-row' role='row'><div class='env-grid-name' role='rowheader'>"+x[0]+"</div><div class='"+pc+"' role='cell'>"+format(pv,x[1])+"</div><div class='"+cc+"' role='cell'>"+format(cv,x[1])+"</div><div class='"+nc+"' role='cell'>"+format(nv,x[1])+"</div></div>";
  }).join("");
  q("environmentTable").innerHTML=html;
  var e=p.environment||{},forecastLabel=forecast.valid_time_utc||forecast.forecast_valid_time_utc,derivedCount=(e.metpy_derived_fields||[]).length;
  setText("envSource",(e.source||p.environment_source||"RAP")+(e.age_minutes==null?"":" • "+num(e.age_minutes,0)+" min")+(derivedCount?" • MetPy "+derivedCount+" derived":"")+" • research bins");
}
function evidenceItem(icon,cls,title,body){return "<div class='evidence-card'><div class='evidence-icon "+(cls||"")+"'>"+icon+"</div><div><b>"+title+"</b><span>"+body+"</span></div></div>"}
function renderEvidence(){
  var p=latestForSelected();if(!p){q("evidenceGrid").innerHTML="";return}
  var e=p.environment||{},f=e.fields||{},vis=fieldValue(f,"visibility_m")??fieldValue(e,"visibility_m")??p.visibility_m,gust=fieldValue(f,"gust_ms")??fieldValue(e,"gust_ms")??p.gust_ms,geo=datasets[p.radar_site]?.geo,fields=geo?.metadata?.fields||{};
  var mping=p.mping_reports||p.mping_count||p.mping_support,shadow=shadowRecord(p.radar_site,p.track_id),cov=shadow?.feature_coverage?.["15"]?.fraction;
  q("evidenceGrid").innerHTML=
    evidenceItem(vis!=null?"✓":"—",vis!=null?"":"warn","METAR / ASOS context",vis!=null?"Visibility "+num(vis/1609.344,1)+" mi"+(gust!=null?" • gust "+num(msToKt(gust),0)+" kt":""):"Surface observation not attached to this object")+
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
    var detectedObjects=got.flatMap(function(x){return (x.geo.features||[]).map(function(f){return Object.assign({},f.properties,{radar_site:x.site,radar_geometry:f.geometry})})});
    allObjects=detectedObjects.filter(function(p){
      var score=Number(p.candidate_rank_score);
      var z=Number(p.max_reflectivity_dbz);
      return (Number.isFinite(score)&&score>=DISPLAY_MIN_SCORE) || (Number.isFinite(z)&&z>=40);
    });
    allObjects.sort(function(a,b){var d=riskScore(b)-riskScore(a);return d||Number(b.max_reflectivity_dbz||0)-Number(a.max_reflectivity_dbz||0)});
    selectDefault();
    await renderRadarMosaic();
    renderMap();renderInventory();renderObjectCard();renderProbability();renderKeyTrends();renderEnvironment();renderEvidence();renderHistory();renderModelStatus();
    var latest=got.map(function(x){return x.state?.last_scan_time_utc||x.geo?.metadata?.scan_time_utc}).filter(Boolean).sort().at(-1);
    setText("liveTime",latest?fmtTime(latest)+" • "+fmtUTC(latest):"No scan time available");
    setText("mapScanLabel",latest?fmtTime(latest):"No live radar");
    setText("feedSummary",(allObjects.length)+" focused objects • "+detectedObjects.length+" radar detections • "+got.map(function(x){return x.site+" "+(x.error?"OFFLINE":(ageMinutes(x.state?.last_scan_time_utc)<=30?"LIVE":"STALE"))}).join(" • "));
    var degraded=got.filter(function(x){return x.error||ageMinutes(x.state?.last_scan_time_utc)>30}).length>0;
    q("liveBadge").classList.toggle("gated",degraded);if(degraded)setText("liveBadge","DEGRADED");
  }catch(e){setText("feedSummary","Live feed error: "+e.message);q("liveBadge").classList.add("gated");setText("liveBadge","DEGRADED")}
}
document.querySelectorAll(".display-btn").forEach(function(b){b.onclick=function(){setRadarMode(b.dataset.radarMode)}});
document.querySelectorAll("[data-jump]").forEach(function(btn){btn.onclick=function(){var el=q(btn.dataset.jump);if(el)el.scrollIntoView({behavior:"smooth",block:"start"});document.querySelectorAll("[data-jump]").forEach(function(b){b.classList.toggle("active",b===btn)})}});
q("refreshBtn").onclick=refresh;q("refreshBtn2").onclick=refresh;
q("radarPlayBtn").onclick=playRadarAnimation;
function stepRadar(delta){var frames=radarHistory.frames||[];if(!frames.length)return;setRadarHistoryIndex((radarHistoryIndex<0?frames.length-1:radarHistoryIndex)+delta)}
q("radarPrevBtn").onclick=function(){stepRadar(-1)};
q("radarNextBtn").onclick=function(){stepRadar(1)};
document.addEventListener("keydown",function(e){if(e.target&&(/input|textarea|select/i.test(e.target.tagName)))return;if(e.key==="ArrowLeft"){e.preventDefault();stepRadar(-1)}else if(e.key==="ArrowRight"){e.preventDefault();stepRadar(1)}});
q("radarLiveBtn").onclick=function(){stopRadarAnimation();radarHistoryIndex=(radarHistory.frames||[]).length-1;updateRadarTimelineUI();renderRadarMosaic()};
q("radarTimelineSlider").oninput=function(){setRadarHistoryIndex(this.value)};
q("objectNumbersBtn").onclick=function(){objectNumbers=!objectNumbers;q("objectNumbersBtn").classList.toggle("active",objectNumbers);renderMap()};
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