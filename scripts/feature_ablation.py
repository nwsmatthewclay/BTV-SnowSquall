"""Case-held-out feature ablation for the SnowSquallProbSevere predictor stack."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline

HORIZONS=(15,30,45,60)
BLOCKED_PREFIXES=("case_","label_","squall_","track_event_","association_","truth_","surface_")
BLOCKED_EXACT={"lead_time_min","lead_time_to_warning_min","warning_issue_utc","warning_distance_km",
"warning_verifying_lsr_count","warning_supervision_class","sqw_intersection","scan_time_utc",
"source_file","radar_site","object_id","population","future_information_policy","environment_status",
"environment_source","label_status","label_reason"}
ENV_TOKENS=("cape","cin","dcape","pwat","srh","shear","snsq","rh_","wind_","thetae","wetbulb",
"temperature","dewpoint","frontogenesis","dcva","omega","epv","mucin","lcl","environment","cloud_layer")
RADAR_TOKENS=("reflectivity","area_km2","length_km","width_km","aspect_ratio","core_","pixel_count",
"echo_top","vertical_","zdr_","rhohv_","kdp_","velocity_")

def as_binary(s):
    if pd.api.types.is_bool_dtype(s): return s.astype(float)
    if pd.api.types.is_numeric_dtype(s): return pd.to_numeric(s,errors="coerce")
    return s.astype(str).str.strip().str.lower().map({"true":1,"false":0,"yes":1,"no":0,"1":1,"0":0}).astype(float)

def predictors(df,target):
    return [c for c in df.columns if c!=target and c not in BLOCKED_EXACT and not any(c.startswith(p) for p in BLOCKED_PREFIXES) and pd.api.types.is_numeric_dtype(df[c])]

def has_any(c,tokens): return any(t in c.lower() for t in tokens)

def family(name,cols):
    if name=="radar_only": return [c for c in cols if has_any(c,RADAR_TOKENS)]
    if name=="environment_only": return [c for c in cols if has_any(c,ENV_TOKENS)]
    if name=="radar_environment": return [c for c in cols if has_any(c,RADAR_TOKENS) or has_any(c,ENV_TOKENS)]
    if name=="radar_environment_motion": return cols
    raise ValueError(name)

def fit_model():
    return Pipeline([("impute",SimpleImputer(strategy="median",add_indicator=True)),
                     ("model",HistGradientBoostingClassifier(learning_rate=0.08,max_iter=220,max_leaf_nodes=15,l2_regularization=1.0,random_state=42))])

def fold_groups(groups):
    unique=np.asarray(sorted(set(groups))); rng=np.random.default_rng(42); shuffled=unique.copy(); rng.shuffle(shuffled)
    n=min(5,len(unique)); return [shuffled[i::n] for i in range(n)]

def evaluate(df,target):
    ys=as_binary(df[target]); valid=ys.notna(); data=df.loc[valid].copy(); y=ys.loc[valid].astype(int).to_numpy()
    groups=data["case_id"].astype(str).to_numpy(); cols=predictors(data,target)
    families=("radar_only","environment_only","radar_environment","radar_environment_motion")
    oof={f:np.full(len(data),np.nan) for f in families}; folds=[]
    for fold,held in enumerate(fold_groups(groups),1):
        test=np.isin(groups,held); train=~test
        if len(np.unique(y[train]))<2 or len(np.unique(y[test]))<2: continue
        info={"fold":fold,"held_out_cases":sorted(set(groups[test])),"n_train":int(train.sum()),"n_test":int(test.sum())}
        for fam in families:
            fam_cols=[c for c in family(fam,cols) if data.iloc[train][c].notna().any() and data.iloc[train][c].nunique(dropna=True)>=2]
            if not fam_cols: continue
            m=fit_model(); m.fit(data.iloc[train][fam_cols],y[train]); oof[fam][test]=m.predict_proba(data.iloc[test][fam_cols])[:,1]
        folds.append(info)
    results={}
    for fam,p in oof.items():
        ok=np.isfinite(p)
        if not ok.any(): results[fam]={"status":"no_valid_predictions"}; continue
        yy,pp=y[ok],p[ok]
        results[fam]={"status":"ok","evaluated_rows":int(ok.sum()),"predictor_family_count":int(len(family(fam,cols))),
                      "roc_auc":float(roc_auc_score(yy,pp)) if len(np.unique(yy))==2 else None,
                      "pr_auc":float(average_precision_score(yy,pp)) if yy.sum() else None,
                      "brier":float(brier_score_loss(yy,pp))}
    return {"status":"ok" if folds else "no_valid_folds","records":len(data),"cases":len(set(groups)),
            "positive":int(y.sum()),"negative":int((1-y).sum()),"candidate_predictors":len(cols),"folds":folds,"families":results}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("features_csv"); ap.add_argument("--output-dir",required=True); args=ap.parse_args()
    df=pd.read_csv(args.features_csv); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    policy="unknown"
    if "future_information_policy" in df.columns and df["future_information_policy"].notna().any(): policy=str(df["future_information_policy"].dropna().iloc[0])
    report={"version":"feature-ablation-v1","future_information_policy":policy,"horizons":{}}
    for h in HORIZONS:
        t=f"squall_onset_within_{h}m"; report["horizons"][str(h)]=evaluate(df,t) if t in df.columns else {"status":"target_missing"}
    (out/"metrics.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"); print(json.dumps(report,indent=2))
if __name__=="__main__": main()
