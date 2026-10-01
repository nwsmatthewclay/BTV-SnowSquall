"""Train research-only analog-enhanced snow-squall candidate models."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import joblib,numpy as np,pandas as pd
from sklearn.ensemble import ExtraTreesClassifier,HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score,brier_score_loss,roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from src.snow_squall.analogs import AnalogLibrary
from src.snow_squall.training import case_scan_balanced_weights,case_weighted_metrics
HORIZONS=(15,30,45,60)
BLOCKED_PREFIXES=("case_","label_","squall_","track_event_","association_","truth_","surface_")
BLOCKED_EXACT={"scan_time_utc","source_file","radar_site","object_id","population","population_id","future_information_policy","lead_time_min","sqw_intersection","environment_status","environment_source"}
def binary(s):
    if pd.api.types.is_bool_dtype(s): return s.astype(float)
    if pd.api.types.is_numeric_dtype(s): return pd.to_numeric(s,errors="coerce")
    return s.astype(str).str.strip().str.lower().map({"true":1,"false":0,"yes":1,"no":0,"1":1,"0":0})
def predictors(df,target):
    return [c for c in df.columns if c!=target and c not in BLOCKED_EXACT and not any(c.startswith(p) for p in BLOCKED_PREFIXES) and pd.api.types.is_numeric_dtype(df[c])]
def specs():
    return {"logistic":Pipeline([("impute",SimpleImputer(strategy="median",add_indicator=True)),("scale",StandardScaler()),("model",LogisticRegression(max_iter=3000,class_weight="balanced",solver="liblinear",random_state=42))]),"hgb":Pipeline([("impute",SimpleImputer(strategy="median",add_indicator=True)),("model",HistGradientBoostingClassifier(learning_rate=.06,max_iter=260,max_leaf_nodes=15,l2_regularization=1.5,random_state=42))]),"extra_trees":Pipeline([("impute",SimpleImputer(strategy="median",add_indicator=True)),("model",ExtraTreesClassifier(n_estimators=350,min_samples_leaf=3,max_features="sqrt",class_weight="balanced",random_state=43,n_jobs=-1))])}
def folds(groups,n=5):
    u=np.asarray(sorted(set(groups))); rng=np.random.default_rng(42); rng.shuffle(u); n=min(n,len(u)); return [u[i::n] for i in range(n)]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("features_csv"); ap.add_argument("--output-dir",required=True); args=ap.parse_args()
    df=pd.read_csv(args.features_csv); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    report={"model_version":"analog_enhanced_candidate_v1","operational_release_status":"candidate_only","future_information_policy":"causal_historical_analogs_only","horizons":{}}
    for h in HORIZONS:
        target=f"squall_onset_within_{h}m"
        if target not in df.columns: report["horizons"][str(h)]={"status":"target_missing"}; continue
        y=binary(df[target]); valid=y.notna(); data=df.loc[valid].copy().reset_index(drop=True); yi=y.loc[valid].astype(int).to_numpy(); groups=data["case_id"].astype(str).to_numpy(); weights=case_scan_balanced_weights(data)
        oof={name:np.full(len(data),np.nan) for name in specs()}; fold_rows=[]
        for fold,held in enumerate(folds(groups),1):
            test=np.isin(groups,held); train=~test
            if len(np.unique(yi[train]))<2 or len(np.unique(yi[test]))<2: continue
            tr=data.loc[train].copy(); te=data.loc[test].copy(); lib=AnalogLibrary.fit(tr); ta=lib.query(tr,top_k=15,max_age_days=3650); va=lib.query(te,top_k=15,max_age_days=3650)
            for c in ta.columns: tr[c]=ta[c].to_numpy(); te[c]=va[c].to_numpy()
            cols=[c for c in predictors(tr,target) if tr[c].notna().any() and tr[c].nunique(dropna=True)>=2]
            for name,model in specs().items(): model.fit(tr[cols],yi[train],model__sample_weight=weights[train]); oof[name][test]=model.predict_proba(te[cols])[:,1]
            fold_rows.append({"fold":fold,"held_out_cases":sorted(set(groups[test])),"n_train":int(train.sum()),"n_test":int(test.sum()),"predictor_count":len(cols)})
        metrics={}
        for name,p in oof.items():
            ok=np.isfinite(p)
            if not ok.any(): metrics[name]={"status":"no_valid_predictions"}; continue
            yy=yi[ok]; pp=p[ok]; bal=case_weighted_metrics(yy,pp,weights[ok]); metrics[name]={"status":"ok","evaluated_rows":int(ok.sum()),"roc_auc":float(roc_auc_score(yy,pp)) if len(np.unique(yy))==2 else None,"pr_auc":float(average_precision_score(yy,pp)) if yy.sum() else None,"brier":float(brier_score_loss(yy,pp)),**{f"case_balanced_{k}":v for k,v in bal.items()}}
        library=AnalogLibrary.fit(data); analogs=library.query(data,top_k=15,max_age_days=3650); enriched=data.copy()
        for c in analogs.columns: enriched[c]=analogs[c].to_numpy()
        cols=[c for c in predictors(enriched,target) if enriched[c].notna().any() and enriched[c].nunique(dropna=True)>=2]; final={}; w=case_scan_balanced_weights(enriched)
        for name,model in specs().items(): model.fit(enriched[cols],yi,model__sample_weight=w); final[name]={"model":model,"predictors":cols}
        joblib.dump({"target":target,"models":final,"analog_library":library},out/f"candidate_{h}min.joblib")
        report["horizons"][str(h)]={"status":"ok" if fold_rows else "no_valid_folds","records":int(len(data)),"cases":int(data["case_id"].nunique()),"positive":int(yi.sum()),"folds":fold_rows,"models":metrics}
    (out/"metrics.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"); print(json.dumps(report,indent=2))
if __name__=="__main__": main()