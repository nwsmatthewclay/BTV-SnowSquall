"""Simple deterministic centroid tracker for radar candidate objects.

The tracker is intentionally lightweight. It prunes stale tracks so an
indefinitely running worker does not accumulate historical state forever.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from math import hypot


@dataclass
class Track:
    object_id:int
    last_time:object
    row:float
    column:float
    age_scans:int=1


@dataclass(frozen=True)
class TrackerConfig:
    max_pixel_distance:float=35.0
    max_time_gap_minutes:float=10.0


class CentroidTracker:
    def __init__(self,config=TrackerConfig()):
        self.config=config
        self.tracks={}
        self.next_id=1

    def _as_datetime(self,value):
        if isinstance(value,str):
            return datetime.fromisoformat(value.replace("Z","+00:00"))
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _minutes_since(self,timestamp,previous):
        try:
            t=self._as_datetime(timestamp)
            p=self._as_datetime(previous)
            return abs((t-p).total_seconds())/60.0
        except (AttributeError,TypeError,ValueError):
            return float("inf")

    def _prune_stale(self,timestamp):
        stale=[
            tid for tid,track in self.tracks.items()
            if self._minutes_since(timestamp,track.last_time)>self.config.max_time_gap_minutes
        ]
        for tid in stale:
            del self.tracks[tid]
        return stale

    def update(self,timestamp,objects):
        self._prune_stale(timestamp)
        assignments=[]
        unused=set(self.tracks)

        for obj in objects:
            best=None
            best_distance=float("inf")
            for tid in unused:
                track=self.tracks[tid]
                distance=hypot(
                    obj["row_centroid"]-track.row,
                    obj["column_centroid"]-track.column,
                )
                if distance<best_distance and distance<=self.config.max_pixel_distance:
                    best,best_distance=tid,distance

            if best is None:
                object_id=self.next_id
                self.next_id+=1
                self.tracks[object_id]=Track(
                    object_id,timestamp,
                    obj["row_centroid"],obj["column_centroid"]
                )
            else:
                object_id=best
                unused.remove(object_id)
                track=self.tracks[object_id]
                track.last_time=timestamp
                track.row=obj["row_centroid"]
                track.column=obj["column_centroid"]
                track.age_scans+=1

            assignments.append((object_id,obj))

        return [{"object_id":object_id,**obj} for object_id,obj in assignments]

    def to_state(self):
        return {
            "next_id":self.next_id,
            "tracks":{
                str(tid):{
                    "object_id":track.object_id,
                    "last_time":self._as_datetime(track.last_time).isoformat(),
                    "row":track.row,
                    "column":track.column,
                    "age_scans":track.age_scans,
                }
                for tid,track in self.tracks.items()
            },
        }

    @classmethod
    def from_state(cls,state,config=TrackerConfig()):
        tracker=cls(config=config)
        if not state:
            return tracker

        tracker.next_id=int(state.get("next_id",1))
        for tid_text,raw in state.get("tracks",{}).items():
            tid=int(tid_text)
            tracker.tracks[tid]=Track(
                object_id=int(raw["object_id"]),
                last_time=raw["last_time"],
                row=float(raw["row"]),
                column=float(raw["column"]),
                age_scans=int(raw.get("age_scans",1)),
            )
        return tracker
