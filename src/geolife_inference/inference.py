"""Transparent evidence scoring and abstention, without ground-truth claims."""
from .config import Config

EVIDENCE_WEIGHTS = {"recurrence": .30, "duration": .25, "temporal_consistency": .20,
                    "coverage": .15, "relative_strength": .10}
AMBIGUITY_MARGIN = .05


def role_candidates(locations: list[dict], coverage: dict, config: Config, role: str) -> list[dict]:
    """All candidates with the same transparent components used by rank_role."""
    if role not in ("home", "office"):
        raise ValueError("role must be home or office")
    dwell_key = "night_dwell_minutes" if role == "home" else "weekday_daytime_dwell_minutes"
    days_key = "night_visit_days" if role == "home" else "weekday_daytime_visit_days"
    observed_days = coverage["night_observed_days" if role == "home" else "work_observed_days"]
    total = sum(loc[dwell_key] for loc in locations)
    ranked = []
    for loc in locations:
        dwell, days = loc[dwell_key], loc[days_key]
        share = dwell / total if total else 0.0
        components = {"recurrence": min(days / 5, 1.0), "duration": min(dwell / 600, 1.0),
                      "temporal_consistency": min(days / max(1, observed_days), 1.0),
                      "coverage": min(coverage["observed_minutes"] / 1440, 1.0), "relative_strength": share}
        score = sum(components[k] * w for k, w in EVIDENCE_WEIGHTS.items())
        eligible = (days >= config.min_role_days and dwell >= config.min_role_dwell_minutes
                    and (role == "home" or loc["weekday_daytime_weeks"] >= config.min_office_weeks))
        ranked.append({"cluster_id": loc["cluster_id"], "latitude": loc["latitude"], "longitude": loc["longitude"],
                       "evidence_score": score, "evidence_components": components,
                       "role_dwell_minutes": dwell, "role_visit_days": days,
                       "relative_share": share, "eligible": eligible})
    ranked.sort(key=lambda c: (-c["evidence_score"], -c["role_dwell_minutes"], c["cluster_id"]))
    return ranked


def rank_role(locations: list[dict], coverage: dict, config: Config, role: str) -> dict:
    ranked = role_candidates(locations, coverage, config, role)
    eligible = [c for c in ranked if c["eligible"]]
    best = eligible[0] if eligible else None
    reason = "insufficient_evidence"
    if best:
        # Compare all candidates, even those that fail recurrence, to expose ambiguity.
        competitors = [c for c in ranked if c["cluster_id"] != best["cluster_id"]]
        ambiguous = bool(competitors and best["evidence_score"] - competitors[0]["evidence_score"] < AMBIGUITY_MARGIN)
        if best["evidence_score"] < config.min_evidence_score:
            reason = "low_evidence_score"
        elif best["relative_share"] < config.min_candidate_share or ambiguous:
            reason = "ambiguous_candidates"
        else:
            return {"status": "predicted", "reason": "sufficient_heuristic_evidence", "candidate": best,
                    "alternatives": [c for c in ranked if c != best][:3]}
    return {"status": "unknown", "reason": reason, "candidate": None, "alternatives": ranked[:3]}


def infer_locations(locations: list[dict], coverage: dict, config: Config) -> dict:
    home = rank_role(locations, coverage, config, "home")
    office = rank_role(locations, coverage, config, "office")
    selected = {role["candidate"]["cluster_id"] for role in (home, office) if role["candidate"]}
    pois = [loc for loc in locations if loc["cluster_id"] not in selected
            and loc["unique_visit_days"] >= config.min_poi_days]
    pois.sort(key=lambda c: (-c["unique_visit_days"], -c["total_dwell_minutes"], c["cluster_id"]))
    return {"home": home, "office": office, "pois": pois[:config.max_pois]}
