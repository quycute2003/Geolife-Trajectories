"""CP1 B2: detector-independent synthetic trajectories; no detector imports.

Preparation and corpus generation are explicit jobs. Never overwrite a run.
Source GPS polylines are treated as constructed latent movement, not real truth.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import ctypes
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .geo import EARTH_RADIUS_M, haversine_m

REVISION = "b2-synthetic-v1"
SEED = 20261104


def memory_usage():
    class Counters(ctypes.Structure):
        _fields_ = [("cb",ctypes.c_ulong),("faults",ctypes.c_ulong)] + [(k,ctypes.c_size_t) for k in
            ["peak_ws","ws","peak_paged","paged","peak_nonpaged","nonpaged","pagefile","peak_pagefile"]]
    counters= Counters(); counters.cb=ctypes.sizeof(counters)
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    api=ctypes.WinDLL("psapi",use_last_error=True)
    api.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
    if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.ws),int(counters.peak_ws)


def available_memory():
    class Status(ctypes.Structure):
        _fields_=[("length",ctypes.c_ulong),("load",ctypes.c_ulong)]+[(k,ctypes.c_ulonglong) for k in
            ["total","available","totalpage","availablepage","totalvirtual","availablevirtual","extended"]]
    status=Status(); status.length=ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError()
    return int(status.available)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def rng_for(*parts):
    return np.random.default_rng(int(digest(parts)[:16], 16))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class Budget:
    def __init__(self, used_seconds, memory, available, limit=12 * 3600):
        if not 0 <= used_seconds < 86400:
            raise ValueError("Điền compute đã dùng thực tế; phải còn quỹ trong 24 giờ")
        self.start = time.perf_counter()
        self.limit = min(limit, 86400 - used_seconds)
        self.used = used_seconds
        self.memory = memory
        self.cap = min(8 * 1024**3, available() // 2)
        self.peak = 0

    def check(self):
        ws, _ = self.memory()
        self.peak = max(self.peak, ws)
        if ws > self.cap:
            raise MemoryError(f"Working set {ws} > RAM budget {self.cap}")
        if time.perf_counter() - self.start > self.limit:
            raise TimeoutError("B2 vượt ngân sách job/compute còn lại")

    def summary(self):
        elapsed = time.perf_counter() - self.start
        return dict(elapsed_seconds=elapsed, compute_used_after_seconds=self.used + elapsed,
                    sampled_peak_working_set_bytes=self.peak, ram_cap_bytes=self.cap)


def iter_trajectories(path, chunksize=100_000):
    carry = None
    cols = ["user_id", "trajectory_id", "timestamp", "latitude", "longitude", "observation_segment"]
    for chunk in pd.read_csv(path, usecols=cols, chunksize=chunksize,
                             dtype={"user_id": str, "trajectory_id": str}):
        if carry is not None:
            chunk = pd.concat([carry, chunk], ignore_index=True)
        cuts = np.flatnonzero((chunk.user_id.ne(chunk.user_id.shift()) |
                              chunk.trajectory_id.ne(chunk.trajectory_id.shift())).to_numpy())
        for a, b in zip(cuts[:-1], cuts[1:]):
            yield chunk.iloc[a:b].reset_index(drop=True)
        carry = chunk.iloc[cuts[-1]:].copy()
    if carry is not None and len(carry):
        yield carry.reset_index(drop=True)


def local_xy(coords):
    origin = coords[0].copy()
    lat = np.radians(coords[:, 0] - origin[0]) * EARTH_RADIUS_M
    lon = np.unwrap(np.radians(coords[:, 1]))
    east = (lon - lon[0]) * EARTH_RADIUS_M * np.cos(np.radians(origin[0]))
    return np.column_stack([east, lat]), origin


def to_coordinates(xy, origin):
    lat = origin[0] + np.degrees(xy[:, 1] / EARTH_RADIUS_M)
    lon = origin[1] + np.degrees(xy[:, 0] / (EARTH_RADIUS_M * np.cos(np.radians(origin[0]))))
    return np.column_stack([lat, (lon + 180) % 360 - 180])


def label_exposure(root, stays):
    """Exclude every overlap with contradictory modes, union same-mode coverage."""
    result = {}
    motor = {"car", "taxi", "bus", "train", "subway"}
    for path in sorted((root / "data/Geolife Trajectories 1.3/Data").glob("*/labels.txt")):
        df = pd.read_csv(path, sep="\t")
        intervals = []
        for row in df.itertuples(index=False, name=None):
            a, b = pd.to_datetime(row[0], utc=True), pd.to_datetime(row[1], utc=True)
            if pd.notna(a) and pd.notna(b) and b > a:
                intervals.append((a.value / 1e9, b.value / 1e9, str(row[2]).strip().lower()))
        edges = sorted({x for a, b, _ in intervals for x in (a, b)})
        valid = []
        for a, b in zip(edges[:-1], edges[1:]):
            modes = {m for x, y, m in intervals if x < b and y > a}
            if len(modes) == 1:
                valid.append((a, b, next(iter(modes))))
        denom = motor_seconds = 0.
        own = stays.loc[stays.user_id == path.parent.name]
        for s in own.itertuples():
            a, b = pd.Timestamp(s.start_time).value / 1e9, pd.Timestamp(s.end_time).value / 1e9
            for x, y, mode in valid:
                overlap = max(0., min(b, y) - max(a, x))
                denom += overlap
                motor_seconds += overlap if mode in motor else 0.
        result[path.parent.name] = dict(valid_label_seconds=sum(b-a for a,b,_ in valid),
            baseline_labeled_stay_seconds=denom, baseline_motor_overlap_seconds=motor_seconds)
    return result


def prepare(root, output, budget):
    """One full cleaned-input scan. Cache five deterministic sources per eligible user.

    All B1 source windows are audited and fingerprinted for cross-user copies.
    Extreme-speed windows are quarantined for generator only, never deleted from GPS.
    """
    root, output = Path(root), Path(output)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    (output / "sources").mkdir()
    audit = {"revision": REVISION, "status": "running", "scope": "all_B1_source_windows"}
    write_json(output / "preparation_audit.json", audit)
    try:
        b1 = root / "artifacts/benchmark/b1/profiles_v1"
        pa = json.loads((b1 / "profile_audit.json").read_text(encoding="utf-8"))
        clean = root / "artifacts/preprocessing/cleaned_points.csv.gz"
        stat = clean.stat()
        if pa["status"] != "completed" or (stat.st_size, stat.st_mtime_ns) != (pa["cleaned_bytes"], pa["cleaned_mtime_ns"]):
            raise ValueError("B1 chưa completed hoặc cleaned input đã đổi")
        sources = pd.read_csv(b1 / "moving_segments.csv", dtype={"user_id": str, "trajectory_id": str})
        wanted = {k: v for k,v in sources.groupby(["user_id", "trajectory_id"], sort=False)}
        records, cached, owners = [], {}, {}
        scanned_points = scanned_trajectories = 0
        for frame in iter_trajectories(clean):
            budget.check()
            scanned_points += len(frame)
            scanned_trajectories += 1
            key = (frame.user_id.iloc[0], frame.trajectory_id.iloc[0])
            if key not in wanted:
                continue
            for row in wanted.pop(key).itertuples():
                part = frame.iloc[row.start_point_index:row.end_point_index+1]
                t = pd.to_datetime(part.timestamp, utc=True).astype("int64").to_numpy() / 1e9
                coords = part[["latitude", "longitude"]].to_numpy(float)
                dt = np.diff(t)
                speed = haversine_m(coords[:-1,0], coords[:-1,1], coords[1:,0], coords[1:,1]) / dt
                valid = (len(part) >= 3 and np.all(dt > 0) and np.all(dt <= 300)
                         and part.observation_segment.nunique() == 1 and np.all(np.isfinite(coords))
                         and np.max(np.abs(coords[:,0])) < 85 and np.max(speed) <= 100)
                if (pd.Timestamp(row.start_utc).value / 1e9 != t[0] or
                        pd.Timestamp(row.end_utc).value / 1e9 != t[-1]):
                    raise ValueError("Source index/timestamp mismatch với B1")
                sid = f"{key[0]}_{key[1]}_{row.start_point_index}_{row.end_point_index}"
                sig = hashlib.sha256((t-t[0]).astype("<f8").tobytes() + coords.astype("<f8").tobytes()).hexdigest()
                rec = dict(source_id=sid, user_id=key[0], trajectory_id=key[1],
                           start_point_index=int(row.start_point_index), end_point_index=int(row.end_point_index),
                           signature=sig, eligible=bool(valid), reason="eligible" if valid else "invalid_or_extreme_speed_source")
                records.append(rec)
                if not valid:
                    continue
                owners.setdefault(sig, set()).add(key[0])
                rank = digest([SEED, sid])
                slots = cached.setdefault(key[0], [])
                slots.append((rank, sid, t, coords))
                slots.sort(key=lambda x: x[0])
                del slots[5:]
        if wanted or scanned_points != pa["processed_points"] or scanned_trajectories != pa["processed_trajectories"]:
            raise ValueError("Input/source coverage không đủ")
        if (clean.stat().st_size, clean.stat().st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
            raise ValueError("Input đổi trong khi chuẩn bị")
        parent = {u: u for u in cached}
        def find(u):
            while parent[u] != u:
                parent[u] = parent[parent[u]]; u = parent[u]
            return u
        for users in owners.values():
            group = sorted(users)
            for u in group[1:]:
                parent[find(u)] = find(group[0])
        groups = {}
        for u in sorted(cached):
            groups.setdefault(find(u), []).append(u)
        independence = {u: digest(sorted(group))[:16] for group in groups.values() for u in group}
        halves = {"selection": [], "final": []}
        for group in sorted(groups.values(), key=lambda x: digest([SEED, x])):
            split = min(halves, key=lambda s: (len(halves[s]), s != "selection"))
            halves[split].extend(group)
        split_map = {u: s for s, us in halves.items() for u in us}
        stays = pd.read_csv(root / "artifacts/stays/stays.csv", dtype={"user_id": str})
        exposure = label_exposure(root, stays)
        counts = stays.groupby("user_id").size()
        all_users = sorted(pa["expected_users"])
        cohort = []
        for u in all_users:
            ex = exposure.get(u, {})
            cohort.append(dict(user_id=u, split=split_map.get(u, "excluded_no_eligible_source"),
                independence_group=independence.get(u, ""),
                cached_sources=len(cached.get(u, [])), baseline_stays=int(counts.get(u, 0)),
                baseline_at_least_5=int(counts.get(u, 0)) >= 5,
                negative_denominator_positive=ex.get("baseline_labeled_stay_seconds",0) > 0, **ex))
        pd.DataFrame(cohort).to_csv(output / "cohort.csv", index=False)
        pd.DataFrame(records).to_csv(output / "source_audit.csv", index=False)
        for u, slots in cached.items():
            for j, (_, sid, t, coords) in enumerate(slots):
                np.savez_compressed(output / "sources" / f"{u}_{j}.npz", t=t, coords=coords, source_id=sid)
        profiles = pd.read_csv(b1 / "profiles_per_user.csv", dtype={"user_id": str}).set_index("user_id")
        selection_p95 = profiles.loc[halves["selection"], "noise_proxy_m_p95"].dropna()
        stress = math.ceil(max(100., float(selection_p95.max()) if len(selection_p95) else 100.) / 10) * 10
        dist = pd.read_csv(b1 / "sampling_distribution.csv", dtype={"user_id": str})
        gaps = {u: g.loc[(g.dt_seconds > 300) & (g.pair_kind == "unobserved_or_segment_break"),
                         ["dt_seconds", "count"]].astype(int).values.tolist() for u,g in dist.groupby("user_id")}
        write_json(output / "gap_blocks.json", gaps)
        table = pd.DataFrame(cohort)
        feasibility = {}
        for s in halves:
            own = table[table.split == s]
            feasibility[s] = dict(source_users=len(own), baseline_at_least_5=int(own.baseline_at_least_5.sum()),
                independent_source_groups=int(own.independence_group.nunique()),
                negative_denominator_users=int(own.negative_denominator_positive.sum()),
                common=int((own.baseline_at_least_5 & own.negative_denominator_positive).sum()),
                radius_edge_cohort="unknown: per-user radius outputs not saved")
        descriptive = any(x["baseline_at_least_5"] < 15 or x["negative_denominator_users"] == 0 for x in feasibility.values())
        protocol = dict(revision=REVISION, split_seed=SEED, split=split_map, feasibility=feasibility,
            independence_groups=independence,
            mode="descriptive" if descriptive else "selection_confirmation_cohort_pending",
            stress_rms_m=stress, source_files={u: len(v) for u,v in cached.items()},
            source_cache_hashes={p.name:file_hash(p) for p in sorted((output/"sources").glob("*.npz"))},
            seeds={"selection":list(range(100000,100005)), "final":list(range(200000,200005))},
            matching=dict(temporal_iou_min=.5, center_distance_max_m=100, one_to_one=True),
            stdbscan=dict(eps_spatial_m=100, eps_time_seconds=300, min_points=3, min_dwell_seconds=600,
                note="Project exploratory configuration, not paper default; per observation segment; min/max timestamps, median center"),
            b1_hashes={p.name:file_hash(p) for p in b1.glob("*.csv*")},
            clean_stat=dict(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns),
            protocol_document_sha256=file_hash(root / "reports/cp1/benchmark_protocol.md"),
            gap_blocks_sha256=file_hash(output / "gap_blocks.json"),
            implementation_sha256=file_hash(Path(__file__)))
        protocol["volume_plan"]={}
        durations=[[180,299,300,301,599],[600,601,900,1199,600],
                   [1200,1201,2400,3600,1200],[3601,5400,7200,10800,3601]]
        for split, users in halves.items():
            upper=0
            for u in users:
                for cell in cells(stress):
                    for i in range(5):
                        _,_,clock,_=cached[u][i%len(cached[u])]
                        dwell=durations[cell["duration_group"]][i]
                        span=clock[-1]-clock[0]+dwell
                        if cell["group"]=="two_stops": span+=dwell+cell["connector_seconds"]
                        if cell["group"]=="negative":
                            seed=(100000 if split=="selection" else 200000)+i
                            actual_seed=int(digest([u,seed])[:12],16)*5+i
                            span=3600+([60,120,180][actual_seed%3] if cell["negative_kind"]=="red_light" else 0)
                        upper+=int(span/np.diff(clock).min())+1
            protocol["volume_plan"][split]=dict(cases=len(users)*len(cells(stress))*5,
                sampled_fixes_upper_bound=upper, runtime="unmeasured")
        plan_text=(root/"PLAN.md").read_text(encoding="utf-8")
        plan_cp1=plan_text.split("## Bổ sung CP1",1)[1].split("## Lộ trình 6 tuần",1)[0]
        (output/"plan_cp1.md").write_text("## Bổ sung CP1"+plan_cp1,encoding="utf-8")
        protocol["plan_cp1_sha256"]=file_hash(output/"plan_cp1.md")
        protocol["protocol_hash"] = digest(protocol)
        (output / "benchmark_protocol.md").write_bytes((root / "reports/cp1/benchmark_protocol.md").read_bytes())
        write_json(output / "protocol.json", protocol)
        budget.check()
        audit.update(status="completed", processed_points=scanned_points, processed_trajectories=scanned_trajectories,
                     audited_source_windows=len(records), eligible_source_users=len(cached), **budget.summary())
        write_json(output / "preparation_audit.json", audit)
        return protocol
    except BaseException as error:
        audit.update(status="failed", error=f"{type(error).__name__}: {error}", **budget.summary())
        write_json(output / "preparation_audit.json", audit)
        raise


def cells(stress):
    rows = []
    def add(group, **kw):
        row = dict(group=group, duration_group=2, rms=15, family="drift", modifier="none")
        row.update(kw)
        row["cell_id"] = f"{group}_{digest(row)[:12]}"
        rows.append(row)
    for d in range(4):
        for rms in [5,15,30,stress]:
            for family in ["gaussian", "drift", "outlier"]:
                row = dict(group="main" if rms != stress else "stress", duration_group=d,
                           rms=rms, family=family, modifier="none")
                row["cell_id"] = f"{row['group']}_{digest(row)[:12]}"; rows.append(row)
        for modifier in ["drop_empirical", "drop25", "drop50"]:
            row=dict(group="dropout", duration_group=d,rms=15,family="drift",modifier=modifier)
            row["cell_id"]="dropout_"+digest(row)[:12]; rows.append(row)
    add("unobservable", modifier="drop_all")
    for distance in [25,75,150]:
        for travel in [120,600]:
            add("two_stops", separation_m=distance, connector_seconds=travel)
    for kind in ["pure_move", "slow", "creeping", "red_light"]:
        add("negative", negative_kind=kind)
    return rows


def _noise(t, rms, family, rng, seed_index):
    n = len(t)
    if family == "gaussian":
        return rng.normal(size=(n,2)) * rms / math.sqrt(2)
    if family == "drift":
        out = np.empty((n,2)); out[0] = rng.normal(size=2) * rms / math.sqrt(2)
        for i in range(1,n):
            rho = math.exp(-(t[i]-t[i-1])/120)
            out[i] = rho*out[i-1] + math.sqrt(1-rho*rho)*rng.normal(size=2)*rms/math.sqrt(2)
        return out
    p = .01 if seed_index % 2 == 0 else .05
    multiplier = np.where(rng.random(n) < p, rng.uniform(3,10,n), 1.)
    expected_m2 = (1-p) + p*(3**2+3*10+10**2)/3
    return rng.normal(size=(n,2))*multiplier[:,None]*rms/math.sqrt(2*expected_m2)


def make_case(t, coords, cell, seed, gap_pool=()):
    """Build latent state first, sample clock, then add noise/dropout. No radius logic."""
    rng = rng_for(REVISION, cell["cell_id"], seed)
    xy, origin = local_xy(coords)
    dt = np.diff(t)
    progress = np.r_[True, np.linalg.norm(np.diff(xy,axis=0),axis=1)>1e-9]
    xy = xy[progress]; path_t = (t-t[0])[progress]
    if len(xy)<2: raise ValueError("Source has no positive movement")
    midpoint = float(path_t[-1]/2)
    center = np.array([np.interp(midpoint,path_t,xy[:,k]) for k in range(2)])
    before = path_t < midpoint; after = path_t > midpoint
    duration_choices = [[180,299,300,301,599], [600,601,900,1199], [1200,1201,2400,3600], [3601,5400,7200,10800]]
    duration = duration_choices[cell["duration_group"]][(seed % 5) % len(duration_choices[cell["duration_group"]])]
    knots_t = np.r_[path_t[before], midpoint, midpoint+duration, path_t[after]+duration]
    knots_xy = np.vstack([xy[before],center,center,xy[after]])
    events = [(midpoint,midpoint+duration,center.copy())]
    if cell["group"] == "two_stops":
        direction = xy[-1]-xy[0]
        if np.linalg.norm(direction) < 1e-9:
            direction = np.diff(xy,axis=0)[0].copy()
        direction /= np.linalg.norm(direction)
        center2 = center + direction*cell["separation_m"]
        end2 = midpoint+2*duration+cell["connector_seconds"]
        knots_t = np.r_[path_t[before], midpoint,midpoint+duration,
                        midpoint+duration+cell["connector_seconds"],end2,path_t[after]+end2-midpoint]
        knots_xy = np.vstack([xy[before],center,center,center2,center2,xy[after]+center2-center])
        events.append((midpoint+duration+cell["connector_seconds"],end2,center2.copy()))
    nonvisit_hold = 0.
    if cell["group"] == "negative":
        kind=cell["negative_kind"]; events=[]
        knots_t=path_t/path_t[-1]*3600; knots_xy=xy.copy()
        arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
        if kind in {"slow","creeping"}:
            knots_xy=xy*(1800 if kind=="slow" else 300)/arc[-1]
        if kind=="red_light":
            hold=[60,120,180][seed%3]
            nonvisit_hold=float(hold)
            mid=knots_t[-1]/2; c=np.array([np.interp(mid,knots_t,knots_xy[:,k]) for k in range(2)])
            lo=knots_t<mid; hi=knots_t>mid
            knots_xy=np.vstack([knots_xy[lo],c,c,knots_xy[hi]])
            knots_t=np.r_[knots_t[lo],mid,mid+hold,knots_t[hi]+hold]
    # A contiguous cadence sequence from this user's source window, cyclically extended.
    offset=int(rng.integers(len(dt))); cadence=np.roll(dt,-offset)
    repetitions=int(math.ceil(knots_t[-1]/cadence.sum()))+1
    clock=np.r_[0,np.cumsum(np.tile(cadence,repetitions))]
    clock=clock[clock<=knots_t[-1]]  # do not force truth endpoints into observations
    latent=np.column_stack([np.interp(clock,knots_t,knots_xy[:,k]) for k in range(2)])
    error=_noise(clock,cell["rms"],cell["family"],rng,seed%5)
    observed=to_coordinates(latent+error,origin)
    keep=np.ones(len(clock),bool); drop_interval=None
    if cell["modifier"] != "none":
        a,b,_=events[0]; length=b-a
        if cell["modifier"]=="drop_empirical":
            if gap_pool:
                values=np.array(gap_pool,float); width=float(rng.choice(values[:,0],p=values[:,1]/values[:,1].sum()))
            else: width=0.
        else: width=length*{"drop25":.25,"drop50":.5,"drop_all":1.}[cell["modifier"]]
        left=(a+b-width)/2; right=left+width
        keep &= ~((clock>=left)&(clock<right)); drop_interval=[left,right]
    # Independent cases must be run independently; source-user identity is for aggregation only.
    times=t[0]+clock[keep]
    segments=np.zeros(len(times),dtype=int)
    if len(times)>1: segments[1:]=np.cumsum(np.diff(times)>300)
    truth=[dict(start_epoch_seconds=float(t[0]+a),end_epoch_seconds=float(t[0]+b),
                latitude=float(to_coordinates(c[None,:],origin)[0,0]),
                longitude=float(to_coordinates(c[None,:],origin)[0,1]),
                observed_fixes=int(((clock>=a)&(clock<b)&keep).sum())) for a,b,c in events]
    metrics=dict(empirical_rms_m=float(np.sqrt(np.mean((error**2).sum(axis=1)))),
        empirical_p95_m=float(np.quantile(np.linalg.norm(error,axis=1),.95)),
        empirical_p99_m=float(np.quantile(np.linalg.norm(error,axis=1),.99)),
        empirical_lag1_x=(float(np.corrcoef(error[:-1,0],error[1:,0])[0,1])
            if len(error)>2 and np.std(error[:-1,0])>0 and np.std(error[1:,0])>0 else None),
        latent_moving_seconds=float(knots_t[-1]-sum(b-a for a,b,_ in events)-nonvisit_hold),
        nonvisit_stationary_seconds=nonvisit_hold,
        drop_interval=drop_interval, generated_fixes=len(clock), observed_fixes=int(keep.sum()))
    if (np.any(np.diff(times)<=0) or not np.isfinite(observed).all()
            or np.any(np.abs(observed[:,0])>90) or np.any(np.abs(observed[:,1])>180)
            or np.any(np.diff(knots_t)<=0)):
        raise ValueError("Generator invariant: timeline/coordinates")
    for a,b,c in events:
        if not 0<=a<b<=knots_t[-1]:
            raise ValueError("Generator invariant: truth bounds")
        inside=(knots_t>=a)&(knots_t<=b)
        if not np.allclose(knots_xy[inside],c,rtol=0,atol=1e-7):
            raise ValueError("Generator invariant: latent stop is not stationary")
    if cell["group"]=="two_stops" and not np.isclose(
            np.linalg.norm(events[1][2]-events[0][2]),cell["separation_m"]):
        raise ValueError("Generator invariant: stop separation")
    return dict(times=times,coords=observed[keep],segments=segments,truth=truth,metrics=metrics,
                latent_knots_t=knots_t+t[0],latent_knots_xy=knots_xy,origin=origin)


def generate(prepared, output, split, budget):
    prepared, output = Path(prepared), Path(output)
    protocol=json.loads((prepared/"protocol.json").read_text(encoding="utf-8"))
    if digest({k:v for k,v in protocol.items() if k != "protocol_hash"}) != protocol["protocol_hash"]:
        raise ValueError("Protocol đã đổi sau khi khóa")
    if file_hash(prepared/"gap_blocks.json") != protocol["gap_blocks_sha256"]:
        raise ValueError("Gap profile đã đổi")
    if file_hash(prepared/"benchmark_protocol.md") != protocol["protocol_document_sha256"]:
        raise ValueError("Protocol document đã đổi")
    if file_hash(prepared/"plan_cp1.md") != protocol["plan_cp1_sha256"]:
        raise ValueError("Frozen B4 decision rules đã đổi")
    if protocol["implementation_sha256"] != file_hash(Path(__file__)):
        raise ValueError("Code đổi sau chuẩn bị; tạo namespace protocol mới")
    if split not in {"selection","final"}: raise ValueError(split)
    if split=="final" and protocol["mode"]=="descriptive":
        raise ValueError("Cohort thiếu: chế độ mô tả không sinh/chạy xác nhận cuối")
    if protocol["feasibility"][split]["independent_source_groups"] < 10:
        raise ValueError("Không đủ quota 10 user nguồn độc lập/phần")
    if output.exists(): raise FileExistsError(output)
    output.mkdir(parents=True); (output/"observations").mkdir(); (output/"truth").mkdir()
    audit=dict(status="running",revision=REVISION,split=split,protocol_hash=protocol["protocol_hash"],completed_users=[],cases=0,points=0)
    write_json(output/"generation_audit.json",audit)
    gaps=json.loads((prepared/"gap_blocks.json").read_text(encoding="utf-8"))
    matrix=cells(protocol["stress_rms_m"])
    write_json(output/"matrix.json",matrix)
    try:
        for user in sorted(u for u,s in protocol["split"].items() if s==split):
            budget.check()
            with gzip.open(output/"observations"/f"{user}.csv.gz","wt",encoding="utf-8",newline="") as obs, gzip.open(output/"truth"/f"{user}.jsonl.gz","wt",encoding="utf-8") as truth:
                writer=csv.writer(obs);writer.writerow(["case_id","source_user_id","timestamp","latitude","longitude","observation_segment"])
                for cell in matrix:
                    for seed in protocol["seeds"][split]:
                        budget.check()
                        slot=(seed%5)%protocol["source_files"][user]
                        path=prepared/"sources"/f"{user}_{slot}.npz"
                        if file_hash(path)!=protocol["source_cache_hashes"][path.name]: raise ValueError("Source cache đổi")
                        with np.load(path) as source:
                            case=make_case(source["t"],source["coords"],cell,int(digest([user,seed])[:12],16)*5+seed%5,gaps.get(user,[]))
                            source_id=str(source["source_id"])
                        cid=f"{user}_{cell['cell_id']}_{seed}"
                        record=dict(case_id=cid,source_user_id=user,source_id=source_id,seed=seed,**cell,
                            events=case["truth"],diagnostics=case["metrics"],
                            latent_knots_epoch=case["latent_knots_t"].tolist(),latent_knots_xy_m=case["latent_knots_xy"].tolist(),origin=case["origin"].tolist())
                        # Truth is serialized before observations, independently of any detector result.
                        truth.write(json.dumps(record,allow_nan=False)+"\n")
                        writer.writerows((cid,user,pd.Timestamp(t,unit="s",tz="UTC").isoformat(),float(c[0]),float(c[1]),int(s)) for t,c,s in zip(case["times"],case["coords"],case["segments"]))
                        audit["cases"]+=1; audit["points"]+=len(case["times"])
            audit["completed_users"].append(user)
            audit.update(budget.summary());write_json(output/"generation_audit.json",audit)
        expected_users=sorted(u for u,s in protocol["split"].items() if s==split)
        if audit["completed_users"] != expected_users or audit["cases"] != len(expected_users)*len(matrix)*5:
            raise ValueError("Corpus thiếu user/cell/seed")
        audit["output_sha256"]={str(p.relative_to(output)):file_hash(p)
            for sub in ["observations","truth"] for p in sorted((output/sub).iterdir())}
        audit["invariant_cases_passed"]=audit["cases"]
        budget.check()
        audit.update(status="completed",**budget.summary());write_json(output/"generation_audit.json",audit)
        return audit
    except BaseException as error:
        audit.update(status="failed",error=f"{type(error).__name__}: {error}",**budget.summary())
        write_json(output/"generation_audit.json",audit); raise
