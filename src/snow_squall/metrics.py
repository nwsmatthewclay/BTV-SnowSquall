"""Verification metrics for probabilistic snow-squall guidance."""
from __future__ import annotations
import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

def probabilistic_metrics(y_true, probability):
    y=np.asarray(y_true)
    p=np.asarray(probability)
    result={"brier_score":float(brier_score_loss(y,p))}
    if len(np.unique(y))>1:
        result["roc_auc"]=float(roc_auc_score(y,p))
        result["pr_auc"]=float(average_precision_score(y,p))
    else:
        result["roc_auc"]=None
        result["pr_auc"]=None
    return result

def reliability_table(y_true, probability, bins=10):
    df=__import__("pandas").DataFrame({"y":y_true,"p":probability})
    df["bin"]=__import__("pandas").cut(df["p"],bins=np.linspace(0,1,bins+1),include_lowest=True)
    return df.groupby("bin",observed=False).agg(count=("y","size"),observed_frequency=("y","mean"),mean_probability=("p","mean")).reset_index()
