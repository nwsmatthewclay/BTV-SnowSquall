let catalog=null;
const num=(v,d=1)=>v==null||Number.isNaN(Number(v))?"—":Number(v).toFixed(d);
const fmt=t=>t?new Date(t).toLocaleString(undefined,{month:"short",day:"numeric",year:"numeric",hour:"numeric",minute:"2-digit"}):"—";
const set=(id,v)=>document.getElementById(id).textContent=v??"—";
function render(c){
  set("subtitle", c ? c.case_id+" • "+c.radar_site+" • independent candidate" : "Validation evidence unavailable");
  document.getElementById("caseCard").innerHTML=c?[
    "<div class='case-title'>"+c.case_id+"</div>",
    "<div class='case-meta'>"+c.evidence_source+" • "+c.evidence_type+"</div>",
    "<div class='case-grid'>",
    "<div><span>Analysis window</span><b>"+fmt(c.analysis_window_start_utc)+" → "+fmt(c.analysis_window_end_utc)+"</b></div>",
    "<div><span>Source</span><b>"+(c.source_url?"Documented":"—")+"</b></div>",
    "</div>"
  ].join(""):"<div class='case-title'>No validation package loaded</div>";
  document.getElementById("metrics").innerHTML=c?[
    ["Radar scans",c.replay_scans],["Failed scans",c.replay_failed_scans],
    ["Radar object-timesteps",c.replay_object_scan_count],["Surface observations",c.surface_rows],
    ["MRMS records compared",c.mrms_object_records_compared],["Max MRMS age",num(c.mrms_max_age_minutes)+" min"]
  ].map(x=>"<div class='metric'><span>"+x[0]+"</span><b>"+x[1]+"</b></div>").join(""):"";
  document.getElementById("surface").innerHTML=c?[
    ["Minimum visibility",c.minimum_visibility_mi==null?"—":num(c.minimum_visibility_mi,2)+" SM"],
    ["Minimum visibility time",fmt(c.minimum_visibility_time_utc)],
    ["First ≤0.5 SM",fmt(c.first_visibility_le_0p5_utc)],
    ["Radar distance at ≤0.5 SM",c.radar_distance_km_at_first_visibility_le_0p5==null?"—":num(c.radar_distance_km_at_first_visibility_le_0p5,1)+" km"],
    ["Maximum gust",c.maximum_gust_kt==null?"—":num(c.maximum_gust_kt,1)+" kt"]
  ].map(x=>"<div class='metric'><span>"+x[0]+"</span><b>"+x[1]+"</b></div>").join(""):"";
  document.getElementById("mrms").innerHTML=c?[
    ["Paired records",c.mrms_paired_records],["Pearson r",c.mrms_neighborhood_pearson_r==null?"—":num(c.mrms_neighborhood_pearson_r,2)],
    ["Mean absolute difference",c.mrms_mean_absolute_difference_dbz==null?"—":num(c.mrms_mean_absolute_difference_dbz,1)+" dBZ"],
    ["Median absolute difference",c.mrms_median_absolute_difference_dbz==null?"—":num(c.mrms_median_absolute_difference_dbz,1)+" dBZ"],
    ["Mean signed difference",c.mrms_mean_signed_difference_dbz==null?"—":num(c.mrms_mean_signed_difference_dbz,1)+" dBZ"]
  ].map(x=>"<div class='metric'><span>"+x[0]+"</span><b>"+x[1]+"</b></div>").join(""):"";
  document.getElementById("review").innerHTML=c?(
    "<b>Truth status: not established.</b><br>"+
    "Training eligible: <b>false</b> • Probability scoring: <b>disabled</b>.<br>"+
    "Use the evidence above for human case review; do not promote the case automatically."
  ):"Validation evidence package unavailable.";
}
function init(){
  fetch("data/validation/catalog.json").then(r=>{if(!r.ok)throw new Error(r.status);return r.json()}).then(c=>{
    catalog=c;
    const cases=c.cases||[];
    const sel=document.getElementById("caseSelect");
    sel.innerHTML=cases.map((x,i)=>"<option value='"+i+"'>"+x.case_id+" • "+x.radar_site+"</option>").join("");
    sel.onchange=()=>render(cases[Number(sel.value)]);
    render(cases[0]);
  }).catch(err=>{
    set("subtitle","Validation package unavailable");
    document.getElementById("caseCard").innerHTML="<div class='case-title'>No validation catalog is currently published.</div><div class='case-meta'>"+String(err)+"</div>";
  });
}
init();
