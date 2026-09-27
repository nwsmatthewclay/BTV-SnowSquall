"""Score candidate radar objects into a model-ready feature table.

This module intentionally accepts a normalized object table. The Level II
decoder/object detector can evolve independently of the feature/model code.
"""
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from snow_squall.features import add_derived_features

def main(input_csv,output_csv):
    df=pd.read_csv(input_csv)
    df=add_derived_features(df)
    Path(output_csv).parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(output_csv,index=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("input_csv")
    p.add_argument("output_csv")
    a=p.parse_args()
    main(a.input_csv,a.output_csv)
