"""Runtime helper for the research-only analog candidate bundle."""
from __future__ import annotations
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

class AnalogCandidateRuntime:
    def __init__(self,bundle):
        self.bundle=bundle
        self.target=bundle.get("target")
        self.models=bundle.get("models") or {}
        self.analog_library=bundle.get("analog_library")

    @classmethod
    def load(cls,path):
        return cls(joblib.load(path))

    @property
    def model_names(self):
        return sorted(self.models)

    @property
    def feature_columns(self):
        cols={}
        for name,entry in self.models.items():
            cols[name]=list(entry.get("predictors") or [])
        return cols

    def enrich(self,frame,top_k=15,max_age_days=3650):
        if self.analog_library is None:
            return frame.copy()
        query=frame.copy()
        if "timestamp" in query.columns and "scan_time_utc" not in query.columns:
            query["scan_time_utc"]=query["timestamp"]
        if "case_id" not in query.columns:
            query["case_id"]=""
        analogs=self.analog_library.query(query,top_k=top_k,max_age_days=max_age_days)
        out=query.copy()
        for col in analogs.columns:
            out[col]=analogs[col].to_numpy()
        return out

    def score(self,frame,top_k=15,max_age_days=3650):
        enriched=self.enrich(frame,top_k=top_k,max_age_days=max_age_days)
        result={}
        for name,entry in self.models.items():
            model=entry["model"]
            cols=list(entry.get("predictors") or [])
            work=enriched.copy()
            for col in cols:
                if col not in work.columns:
                    work[col]=np.nan
            result[name]=model.predict_proba(work[cols])[:,1].tolist()
        return result
