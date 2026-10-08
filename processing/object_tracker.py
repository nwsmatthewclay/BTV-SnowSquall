"""Deterministic radar-object tracker with radar-motion guidance."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from math import hypot,log1p
import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass
class Track:
    object_id:int
    first_time:object
    last_time:object
    row:float
    column:float
    age_scans:int=1
    velocity_row:float=0.0
    velocity_column:float=0.0
    area_km2:float|None=None
    max_reflectivity_dbz:float|None=None
    missed_scans:int=0
    history:list|None=None
    bbox:tuple|None=None


@dataclass(frozen=True)
class TrackerConfig:
    max_pixel_distance:float=18.0
    grid_spacing_km:float=1.0
    max_motion_kt:float=90.0
    min_gate_distance_km:float=4.0
    max_time_gap_minutes:float=30.0
    max_missed_scans:int=2
    max_area_ratio:float=16.0
    prediction_weight:float=0.72
    size_weight:float=0.16
    intensity_weight:float=0.12
    radar_motion_weight:float=0.30


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
            return abs((self._as_datetime(timestamp)-self._as_datetime(previous)).total_seconds())/60.0
        except (AttributeError,TypeError,ValueError):
            return float("inf")

    def _dt_minutes(self,timestamp,previous):
        try:
            return max(0.1,(self._as_datetime(timestamp)-self._as_datetime(previous)).total_seconds()/60.0)
        except (AttributeError,TypeError,ValueError):
            return 1.0

    def _prune_stale(self,timestamp):
        stale=[tid for tid,track in self.tracks.items() if self._minutes_since(timestamp,track.last_time)>self.config.max_time_gap_minutes]
        for tid in stale: del self.tracks[tid]
        return stale


    @staticmethod
    def _bbox(obj):
        try:
            rows=np.asarray(obj.get("row_indices",[]),dtype=float)
            cols=np.asarray(obj.get("column_indices",[]),dtype=float)
            if rows.size==0 or cols.size==0:
                return None
            return (float(np.min(rows)), float(np.min(cols)),
                    float(np.max(rows)), float(np.max(cols)))
        except (TypeError,ValueError):
            return None

    @staticmethod
    def _bbox_iou(a,b):
        if a is None or b is None:
            return 0.0
        ay0,ax0,ay1,ax1=a
        by0,bx0,by1,bx1=b
        iy0=max(ay0,by0); ix0=max(ax0,bx0)
        iy1=min(ay1,by1); ix1=min(ax1,bx1)
        if iy1<iy0 or ix1<ix0:
            return 0.0
        inter=(iy1-iy0+1.0)*(ix1-ix0+1.0)
        area_a=max(1.0,(ay1-ay0+1.0)*(ax1-ax0+1.0))
        area_b=max(1.0,(by1-by0+1.0)*(bx1-bx0+1.0))
        return float(inter/max(1.0,area_a+area_b-inter))

    def _projected_bbox(self,track,timestamp,radar_motion=None):
        if track.bbox is None:
            return None
        pred_row,pred_col=self._predicted_position(track,timestamp,radar_motion)
        dr=pred_row-track.row
        dc=pred_col-track.column
        y0,x0,y1,x1=track.bbox
        return (y0+dr,x0+dc,y1+dr,x1+dc)

    @staticmethod
    def _area(obj):
        try: return max(0.0,float(obj.get("area_km2",obj.get("pixel_count"))))
        except (TypeError,ValueError): return 0.0

    @staticmethod
    def _z(obj):
        try: return float(obj.get("max_reflectivity_dbz"))
        except (TypeError,ValueError): return 0.0

    def _predicted_position(self,track,timestamp,radar_motion=None):
        dt=min(self.config.max_time_gap_minutes,self._dt_minutes(timestamp,track.last_time))
        vr,vc=track.velocity_row,track.velocity_column
        if radar_motion and np.isfinite(radar_motion.get("radar_motion_confidence",np.nan)):
            conf=float(np.clip(radar_motion.get("radar_motion_confidence",0.0),0.0,1.0))
            w=self.config.radar_motion_weight*conf
            vr=(1-w)*vr+w*float(radar_motion.get("radar_motion_row_per_min",vr))
            vc=(1-w)*vc+w*float(radar_motion.get("radar_motion_column_per_min",vc))
        return track.row+vr*dt,track.column+vc*dt

    def _radar_velocity(self,radar_motion):
        if not radar_motion:
            return None
        try:
            confidence=float(radar_motion.get("radar_motion_confidence",0.0))
            vr=float(radar_motion.get("radar_motion_row_per_min"))
            vc=float(radar_motion.get("radar_motion_column_per_min"))
        except (TypeError,ValueError):
            return None
        if not np.isfinite(confidence) or confidence <= 0 or not np.isfinite(vr) or not np.isfinite(vc):
            return None
        return vr,vc,float(np.clip(confidence,0.0,1.0))

    def _association_gate_pixels(self,timestamp,previous):
        dt=min(self.config.max_time_gap_minutes,max(0.1,self._dt_minutes(timestamp,previous)))
        max_distance_km=max(self.config.min_gate_distance_km,self.config.max_motion_kt*1.852*(dt/60.0))
        return max(self.config.max_pixel_distance*(dt/10.0),max_distance_km/max(self.config.grid_spacing_km,0.01))

    def _cost(self,track,obj,timestamp,radar_motion=None):
        pred_row,pred_col=self._predicted_position(track,timestamp,radar_motion)
        distance=hypot(obj["row_centroid"]-pred_row,obj["column_centroid"]-pred_col)
        gate_pixels=self._association_gate_pixels(timestamp,track.last_time)
        if distance>gate_pixels: return np.inf
        track_area=max(1.0,float(track.area_km2 or 1.0)); obj_area=max(1.0,self._area(obj))
        size_cost=abs(log1p(obj_area)-log1p(track_area))/3.0
        intensity_cost=0.0 if track.max_reflectivity_dbz is None else min(1.0,abs(self._z(obj)-track.max_reflectivity_dbz)/20.0)
        area_ratio=max(obj_area/track_area,track_area/obj_area)
        if area_ratio>self.config.max_area_ratio: return np.inf
        position_cost=distance/max(gate_pixels,1e-6)
        overlap_cost=1.0-self._bbox_iou(self._projected_bbox(track,timestamp,radar_motion),self._bbox(obj))
        return 0.58*position_cost+0.18*overlap_cost+0.14*size_cost+0.10*intensity_cost

    def update(self,timestamp,objects,radar_motion=None):
        self._prune_stale(timestamp)
        objects=list(objects)
        if not objects:
            for tid,track in list(self.tracks.items()):
                track.missed_scans += 1
                if track.missed_scans > self.config.max_missed_scans:
                    del self.tracks[tid]
            return []
        track_ids=sorted(self.tracks); assignments={}; used=set(); matched_track_ids=set()
        candidate_counts = np.zeros(len(objects), dtype=int)
        candidate_track_counts = np.zeros(len(track_ids), dtype=int) if track_ids else np.zeros(0, dtype=int)
        if track_ids:
            for ti, tid in enumerate(track_ids):
                for oi, obj in enumerate(objects):
                    value = self._cost(self.tracks[tid], obj, timestamp, radar_motion)
                    if np.isfinite(value):
                        candidate_counts[oi] += 1
                        candidate_track_counts[ti] += 1

        if track_ids:
            # First take unambiguous projected-centroid matches. This follows
            # the Lakshmanan tracking strategy and protects isolated storms
            # from unnecessary Hungarian reassignment.
            unique_pairs=[]
            for tid in track_ids:
                track=self.tracks[tid]
                pred_row,pred_col=self._predicted_position(track,timestamp,radar_motion)
                gate=min(5.0,self._association_gate_pixels(timestamp,track.last_time))
                candidates=[
                    oi for oi,obj in enumerate(objects)
                    if oi not in used
                    and hypot(obj["row_centroid"]-pred_row,obj["column_centroid"]-pred_col)<=gate
                    and np.isfinite(self._cost(track,obj,timestamp,radar_motion))
                ]
                if len(candidates)==1:
                    unique_pairs.append((tid,candidates[0]))
            for tid,oi in sorted(unique_pairs,key=lambda pair:(-self.tracks[pair[0]].age_scans,pair[0])):
                if oi in used or tid in matched_track_ids:
                    continue
                assignments[oi]=tid
                used.add(oi)
                matched_track_ids.add(tid)

            remaining_tracks=[tid for tid in track_ids if tid not in matched_track_ids]
            remaining_objects=[oi for oi in range(len(objects)) if oi not in used]
            if remaining_tracks and remaining_objects:
                cost=np.full((len(remaining_tracks),len(remaining_objects)),np.inf,dtype=float)
                for ti,tid in enumerate(remaining_tracks):
                    for oj,oi in enumerate(remaining_objects):
                        cost[ti,oj]=self._cost(self.tracks[tid],objects[oi],timestamp,radar_motion)
                finite=np.isfinite(cost)
                if finite.any():
                    ri,ci=linear_sum_assignment(np.where(finite,cost,1e6))
                    for r,cidx in zip(ri,ci):
                        if np.isfinite(cost[r,cidx]):
                            oi=remaining_objects[int(cidx)]
                            assignments[oi]=remaining_tracks[int(r)]
                            used.add(oi)
                            matched_track_ids.add(remaining_tracks[int(r)])
        for object_index,tid in assignments.items():
            obj=objects[object_index]; track=self.tracks[tid]
            dt=self._dt_minutes(timestamp,track.last_time)
            old_row,old_col=track.row,track.column
            measured_row=float(obj["row_centroid"]); measured_col=float(obj["column_centroid"])
            association_distance=hypot(measured_row-old_row,measured_col-old_col)
            gate=self._association_gate_pixels(timestamp,track.last_time)
            cost_value=self._cost(track,obj,timestamp,radar_motion)
            new_vr=(measured_row-old_row)/dt; new_vc=(measured_col-old_col)/dt
            alpha=0.55 if track.age_scans<3 else 0.35
            measured_track_vr=(1-alpha)*track.velocity_row+alpha*new_vr
            measured_track_vc=(1-alpha)*track.velocity_column+alpha*new_vc
            radar_velocity=self._radar_velocity(radar_motion)
            if radar_velocity is not None:
                radar_vr,radar_vc,radar_conf=radar_velocity
                motion_weight=self.config.radar_motion_weight*radar_conf
                track.velocity_row=(1-motion_weight)*measured_track_vr+motion_weight*radar_vr
                track.velocity_column=(1-motion_weight)*measured_track_vc+motion_weight*radar_vc
                obj["track_motion_source"]="object_radar_blend"
                obj["track_motion_radar_weight"]=float(motion_weight)
            else:
                track.velocity_row=measured_track_vr
                track.velocity_column=measured_track_vc
                obj["track_motion_source"]="object_only"
                obj["track_motion_radar_weight"]=0.0
            track.last_time=timestamp; track.row=measured_row; track.column=measured_col
            track.age_scans+=1; track.missed_scans=0; track.area_km2=self._area(obj); track.max_reflectivity_dbz=self._z(obj)
            track.bbox=self._bbox(obj)
            if track.history is None:
                track.history = []
            track.history.append({
                "timestamp": self._as_datetime(timestamp).isoformat().replace("+00:00", "Z"),
                "row": measured_row,
                "column": measured_col,
                "age_scans": int(track.age_scans),
            })
            track.history = track.history[-24:]
            obj["track_association_status"]="matched"
            obj["track_competing_track_count"] = int(candidate_counts[object_index])
            obj["track_competing_object_count"] = int(candidate_track_counts[track_ids.index(tid)]) if track_ids else 0
            obj["track_merge_candidate"] = bool(candidate_counts[object_index] > 1)
            obj["track_split_candidate"] = bool(candidate_track_counts[track_ids.index(tid)] > 1)
            obj["track_association_distance_px"]=float(association_distance)
            obj["track_association_gate_px"]=float(gate)
            obj["track_association_cost"]=float(cost_value)
            obj["track_age_scans"]=int(track.age_scans); obj["track_missed_scans"]=0
            obj["track_first_scan_utc"]=self._as_datetime(track.first_time).isoformat()
            obj["track_age_min"]=max(0.0,(self._as_datetime(timestamp)-self._as_datetime(track.first_time)).total_seconds()/60.0)
            obj["track_status"]="active"
            obj["track_velocity_row_per_min"]=float(track.velocity_row)
            obj["track_velocity_column_per_min"]=float(track.velocity_column)
            if radar_motion:
                obj["radar_motion_speed_kt"]=radar_motion.get("radar_motion_speed_kt")
                obj["radar_motion_direction_deg"]=radar_motion.get("radar_motion_direction_deg")
                obj["radar_motion_confidence"]=radar_motion.get("radar_motion_confidence")
        for tid,track in list(self.tracks.items()):
            if tid not in matched_track_ids and tid in self.tracks:
                track.missed_scans+=1
                if track.missed_scans>self.config.max_missed_scans: del self.tracks[tid]
        for oi,obj in enumerate(objects):
            if oi in used: continue
            tid=self.next_id; self.next_id+=1
            initial_vr=0.0
            initial_vc=0.0
            radar_velocity=self._radar_velocity(radar_motion)
            if radar_velocity is not None:
                initial_vr,initial_vc,_=radar_velocity
                motion_source="radar_prior"
                radar_weight=1.0
            else:
                motion_source="object_only"
                radar_weight=0.0
            self.tracks[tid]=Track(
                tid,timestamp,timestamp,
                float(obj["row_centroid"]),float(obj["column_centroid"]),
                velocity_row=initial_vr,velocity_column=initial_vc,
                area_km2=self._area(obj),max_reflectivity_dbz=self._z(obj),bbox=self._bbox(obj),
                history=[{
                    "timestamp": self._as_datetime(timestamp).isoformat().replace("+00:00", "Z"),
                    "row": float(obj["row_centroid"]),
                    "column": float(obj["column_centroid"]),
                    "age_scans": 1,
                }],
            )
            obj["track_association_status"]="new"; obj["track_association_distance_px"]=float("nan"); obj["track_association_gate_px"]=float("nan"); obj["track_association_cost"]=float("nan"); obj["track_age_scans"]=1; obj["track_missed_scans"]=0
            obj["track_first_scan_utc"]=self._as_datetime(timestamp).isoformat()
            obj["track_age_min"]=0.0
            obj["track_status"]="active"
            obj["track_motion_source"]=motion_source
            obj["track_motion_radar_weight"]=float(radar_weight)
            obj["track_velocity_row_per_min"]=float(initial_vr)
            obj["track_velocity_column_per_min"]=float(initial_vc)
            obj["track_competing_track_count"] = int(candidate_counts[oi]) if oi < len(candidate_counts) else 0
            obj["track_competing_object_count"] = 0
            obj["track_merge_candidate"] = bool(obj["track_competing_track_count"] > 1)
            obj["track_split_candidate"] = False
            if radar_motion:
                obj["radar_motion_speed_kt"]=radar_motion.get("radar_motion_speed_kt"); obj["radar_motion_direction_deg"]=radar_motion.get("radar_motion_direction_deg"); obj["radar_motion_confidence"]=radar_motion.get("radar_motion_confidence")
            assignments[oi]=tid
        output=[]
        for i,obj in enumerate(objects):
            row=dict(obj)
            # Detector object_id is scan-local. Promote the tracker-assigned
            # identity to object_id and preserve the original as a diagnostic.
            detector_id=row.get("object_id")
            row["detector_object_id"]=detector_id
            row["object_id"]=assignments[i]
            row["track_id"]=assignments[i]
            track = self.tracks.get(assignments[i])
            row["track_position_history"] = list(track.history or []) if track is not None else []
            row["track_current_row"] = float(track.row) if track is not None else row.get("row_centroid")
            row["track_current_column"] = float(track.column) if track is not None else row.get("column_centroid")
            row["track_velocity_row_per_min"] = float(track.velocity_row) if track is not None else row.get("track_velocity_row_per_min")
            row["track_velocity_column_per_min"] = float(track.velocity_column) if track is not None else row.get("track_velocity_column_per_min")
            output.append(row)
        return output

    def to_state(self):
        return {"next_id":self.next_id,"tracks":{str(tid):{"object_id":track.object_id,"first_time":self._as_datetime(track.first_time).isoformat(),"last_time":self._as_datetime(track.last_time).isoformat(),"row":track.row,"column":track.column,"age_scans":track.age_scans,"velocity_row":track.velocity_row,"velocity_column":track.velocity_column,"area_km2":track.area_km2,"max_reflectivity_dbz":track.max_reflectivity_dbz,"missed_scans":track.missed_scans,"history":track.history or [],"bbox":list(track.bbox) if track.bbox is not None else None} for tid,track in self.tracks.items()}}

    @classmethod
    def from_state(cls,state,config=TrackerConfig()):
        tracker=cls(config=config)
        if not state:return tracker
        tracker.next_id=int(state.get("next_id",1))
        for tid_text,raw in state.get("tracks",{}).items():
            tid=int(tid_text); tracker.tracks[tid]=Track(object_id=int(raw["object_id"]),first_time=raw.get("first_time",raw["last_time"]),last_time=raw["last_time"],row=float(raw["row"]),column=float(raw["column"]),age_scans=int(raw.get("age_scans",1)),velocity_row=float(raw.get("velocity_row",0.0)),velocity_column=float(raw.get("velocity_column",0.0)),area_km2=raw.get("area_km2"),max_reflectivity_dbz=raw.get("max_reflectivity_dbz"),missed_scans=int(raw.get("missed_scans",0)),history=list(raw.get("history",[]))[-24:],bbox=tuple(raw["bbox"]) if raw.get("bbox") is not None else None)
        return tracker
