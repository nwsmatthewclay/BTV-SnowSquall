"""
BTV Snow Squall Project - resilient real-time NEXRAD Level II acquisition.
"""
from __future__ import annotations
import argparse, logging, re, time
from datetime import datetime, timezone
from pathlib import Path
import boto3
from botocore import UNSIGNED
from botocore.config import Config, Config

BUCKET="unidata-nexrad-level2"; REGION="us-east-1"
PROJECT_ROOT=Path(__file__).resolve().parents[1]; RAW_ROOT=PROJECT_ROOT/"data"/"raw"; LOG_ROOT=PROJECT_ROOT/"logs"
RADARS=("KCXX","KTYX"); POLL_SECONDS=10; LOOKBACK_HOURS=2; DOWNLOAD_TIMEOUT=60; MAX_RETRIES=3
VOLUME_TIME_RE=re.compile(r"(?P<radar>[A-Z0-9]{4})(?P<date>\d{8})[_-]?(?P<time>\d{6})",re.I)

def setup_logging(radar):
    LOG_ROOT.mkdir(parents=True,exist_ok=True); logger=logging.getLogger(); logger.setLevel(logging.INFO)
    if logger.handlers:return
    fmt=logging.Formatter("%(asctime)s UTC | %(levelname)s | %(message)s"); c=logging.StreamHandler();c.setFormatter(fmt);logger.addHandler(c)
    f=logging.FileHandler(LOG_ROOT/f"{radar.lower()}_watcher.log");f.setFormatter(fmt);logger.addHandler(f)

def utc_now(): return datetime.now(timezone.utc)

def parse_volume_time(key,radar):
    m=VOLUME_TIME_RE.search(Path(key).name)
    if not m or m.group("radar").upper()!=radar.upper(): return None
    try:return datetime.strptime(m.group("date")+m.group("time"),"%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:return None

def make_s3_client():
    return boto3.client("s3",region_name=REGION,config=Config(signature_version=UNSIGNED,connect_timeout=15,read_timeout=DOWNLOAD_TIMEOUT,retries={"max_attempts":3,"mode":"standard"}))

def archive_prefix(radar,when): return f"{when:%Y}/{when:%m}/{when:%d}/{radar}/{radar}{when:%Y%m%d_%H}"

def find_newest_volume(s3,radar):
    now=utc_now(); candidates=[]
    for off in range(LOOKBACK_HOURS):
        hour_dt=now.replace(minute=0,second=0,microsecond=0)-__import__("datetime").timedelta(hours=off)
        resp=s3.list_objects_v2(Bucket=BUCKET,Prefix=archive_prefix(radar,hour_dt))
        for item in resp.get("Contents",[]):
            vt=parse_volume_time(item["Key"],radar)
            if vt:candidates.append((item["Key"],vt))
    return max(candidates,key=lambda x:x[1]) if candidates else None

def download_volume(s3,radar,key,volume_time):
    d=RAW_ROOT/radar;d.mkdir(parents=True,exist_ok=True);local=d/Path(key).name
    if local.exists() and local.stat().st_size>0:
        logging.info("Already have %s",local.name);return local
    for attempt in range(1,MAX_RETRIES+1):
        tmp=local.with_suffix(local.suffix+".part")
        try:
            logging.info("Downloading %s -> %s (attempt %d/%d)",key,local,attempt,MAX_RETRIES)
            if tmp.exists():tmp.unlink()
            s3.download_file(BUCKET,key,str(tmp))
            if not tmp.exists() or tmp.stat().st_size==0: raise IOError("empty download")
            tmp.replace(local);return local
        except Exception as exc:
            if tmp.exists():tmp.unlink()
            logging.exception("Download failed for %s on attempt %d/%d",key,attempt,MAX_RETRIES)
            if attempt<MAX_RETRIES:time.sleep(2**attempt)
            else:raise
    raise RuntimeError("unreachable")

def run(radar,poll_seconds):
    setup_logging(radar);logging.info("="*72);logging.info("BTV SNOW SQUALL - %s REAL-TIME ACQUISITION TEST",radar);logging.info("Bucket: %s",BUCKET);logging.info("Poll interval: %s seconds",poll_seconds);logging.info("Started: %s",utc_now().isoformat());logging.info("="*72)
    s3=make_s3_client();last_key=None
    while True:
        try:
            newest=find_newest_volume(s3,radar)
            if newest is None:logging.warning("No recent %s volumes found.",radar)
            else:
                key,volume_time=newest
                if key!=last_key:
                    discovered=utc_now();logging.info("New %s volume found: %s | radar time=%s",radar,key,volume_time.isoformat())
                    path=download_volume(s3,radar,key,volume_time);done=utc_now();logging.info("%s volume=%s | acquired=%s | age=%s",radar,volume_time.isoformat(),done.isoformat(),done-volume_time);logging.info("Local file ready: %s | download_time=%s",path,done-discovered);last_key=key
            time.sleep(poll_seconds)
        except KeyboardInterrupt:logging.info("Stopped by user.");break
        except Exception:logging.exception("Watcher error; retrying after 5 seconds.");time.sleep(5)

def parse_args():
    p=argparse.ArgumentParser();p.add_argument("--radar",required=True,choices=RADARS);p.add_argument("--poll-seconds",type=int,default=POLL_SECONDS);return p.parse_args()
if __name__=="__main__": args=parse_args();run(args.radar,max(2,args.poll_seconds))
