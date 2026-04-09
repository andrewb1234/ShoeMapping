from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List


NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
WEIGHT_GRAMS_PATTERN = re.compile(r"\(([-\d.]+)\s*g\)", re.IGNORECASE)


def extract_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = NUMBER_PATTERN.search(str(value))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def extract_weight_grams(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    grams_match = WEIGHT_GRAMS_PATTERN.search(text)
    if grams_match:
        try:
            return float(grams_match.group(1))
        except ValueError:
            return None
    number = extract_float(text)
    if number is None:
        return None
    if "oz" in text.lower():
        return number * 28.3495
    return number


def split_values(value: Any) -> List[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [part.strip().lower() for part in text.split("|") if part.strip()]


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def percentile(values: List[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_weight_thresholds(shoes: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    grouped: Dict[str, List[float]] = {}
    for shoe in shoes:
        lab = shoe.get("lab_test_results") or {}
        terrain = str(lab.get("Terrain") or shoe.get("terrain") or "Unknown")
        grouped.setdefault(terrain, [])
        weight = extract_weight_grams(lab.get("Weight"))
        if weight is not None:
            grouped[terrain].append(weight)

    thresholds: Dict[str, Dict[str, float]] = {}
    for terrain, weights in grouped.items():
        if not weights:
            thresholds[terrain] = {"q1": 240.0, "q2": 290.0}
            continue
        thresholds[terrain] = {
            "q1": percentile(weights, 1 / 3),
            "q2": percentile(weights, 2 / 3),
        }
    return thresholds


def _midsole_softness(lab: Dict[str, Any]) -> float | None:
    for key in (
        "Midsole softness (new method)",
        "Midsole softness (old method)",
        "Midsole softness heel",
        "Midsole softness forefoot",
    ):
        value = extract_float(lab.get(key))
        if value is not None:
            return value
    return None


def _torsional_rigidity(lab: Dict[str, Any]) -> float | None:
    for key in ("Torsional rigidity", "Torsional rigidity (old method)"):
        value = extract_float(lab.get(key))
        if value is not None:
            return value
    return None


def metric_snapshot(lab: Dict[str, Any]) -> Dict[str, float | None]:
    return {
        "weight_g": extract_weight_grams(lab.get("Weight")),
        "drop_mm": extract_float(lab.get("Drop")),
        "heel_stack_mm": extract_float(lab.get("Heel stack")),
        "forefoot_stack_mm": extract_float(lab.get("Forefoot stack")),
        "energy_return_pct": extract_float(lab.get("Energy return heel")),
        "outsole_durability_mm": extract_float(lab.get("Outsole durability")),
        "heel_counter_stiffness": extract_float(lab.get("Heel counter stiffness")),
        "torsional_rigidity": _torsional_rigidity(lab),
        "softness_ha": _midsole_softness(lab),
        "forefoot_traction": extract_float(lab.get("Forefoot traction")),
        "lug_depth_mm": extract_float(lab.get("Lug depth")),
    }


def classify_weight(weight_g: float | None, thresholds: Dict[str, float]) -> str:
    if weight_g is None:
        return "unknown"
    if weight_g <= thresholds["q1"]:
        return "light"
    if weight_g <= thresholds["q2"]:
        return "moderate"
    return "heavy"


def classify_cushion(snapshot: Dict[str, float | None]) -> tuple[str, float]:
    heel_stack = snapshot.get("heel_stack_mm")
    softness = snapshot.get("softness_ha")
    stack_score = clamp(((heel_stack or 30.0) - 22.0) / 20.0)
    soft_score = 0.5 if softness is None else clamp((35.0 - softness) / 18.0)
    cushion_score = (stack_score * 0.75) + (soft_score * 0.25)
    if cushion_score >= 0.82:
        return "max", cushion_score
    if cushion_score >= 0.62:
        return "high", cushion_score
    if cushion_score >= 0.42:
        return "balanced", cushion_score
    return "low", cushion_score


def classify_stability(lab: Dict[str, Any], snapshot: Dict[str, float | None]) -> str:
    torsional = snapshot.get("torsional_rigidity")
    heel_counter = snapshot.get("heel_counter_stiffness")
    support_bonus = 0.0
    support_text = " ".join(
        split_values(lab.get("Arch Support")) + split_values(lab.get("Pronation"))
    )
    if any(token in support_text for token in ("stability", "support", "overpronation")):
        support_bonus += 0.2
    if "neutral" not in support_text and support_text:
        support_bonus += 0.1
    torsional_score = clamp(((torsional or 3.0) - 1.0) / 4.0)
    heel_counter_score = clamp(((heel_counter or 3.0) - 1.0) / 4.0)
    score = ((torsional_score + heel_counter_score) / 2.0) + support_bonus
    if score >= 0.78:
        return "high"
    if score >= 0.5:
        return "moderate"
    return "neutral"


def classify_ride_role(
    lab: Dict[str, Any],
    snapshot: Dict[str, float | None],
    cushion_level: str,
    weight_class: str,
) -> str:
    terrain = str(lab.get("Terrain") or "").lower()
    pace_values = " ".join(split_values(lab.get("Pace")))
    use_values = " ".join(split_values(lab.get("Use")))
    energy_return = snapshot.get("energy_return_pct") or 0.0

    if "trail" in terrain:
        if any(token in use_values for token in ("hiking", "hike", "walking")):
            return "hike"
        return "trail"
    if any(token in pace_values for token in ("race", "competition")):
        return "race"
    if any(token in pace_values for token in ("tempo", "speed", "interval")):
        return "uptempo"
    if weight_class == "light" and energy_return >= 60:
        return "race"
    if weight_class in {"light", "moderate"} and energy_return >= 50:
        return "uptempo"
    if cushion_level in {"high", "max"} and weight_class != "light":
        return "easy"
    return "daily"


def classify_durability(snapshot: Dict[str, float | None], ride_role: str) -> str:
    outsole_durability = snapshot.get("outsole_durability_mm")
    torsional = snapshot.get("torsional_rigidity") or 3.0
    durability_score = 0.5
    if outsole_durability is not None:
        durability_score = clamp((1.5 - outsole_durability) / 1.2)
    durability_score = (durability_score * 0.7) + clamp((torsional - 1.0) / 4.0) * 0.3
    if ride_role in {"trail", "hike"}:
        durability_score += 0.1
    if durability_score >= 0.72:
        return "high"
    if durability_score >= 0.42:
        return "medium"
    return "low"


def classify_drop(drop_mm: float | None) -> str:
    if drop_mm is None:
        return "unknown"
    if drop_mm <= 4.0:
        return "low"
    if drop_mm <= 8.0:
        return "mid"
    return "high"


def build_shoe_facets(
    shoes: Iterable[Dict[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    shoe_list = list(shoes)
    thresholds = build_weight_thresholds(shoe_list)
    enriched: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for shoe in shoe_list:
        lab = shoe.get("lab_test_results") or {}
        terrain = str(lab.get("Terrain") or shoe.get("terrain") or "Unknown")
        snapshot = metric_snapshot(lab)
        weight_class = classify_weight(
            snapshot.get("weight_g"),
            thresholds.get(terrain, {"q1": 240.0, "q2": 290.0}),
        )
        cushion_level, _ = classify_cushion(snapshot)
        ride_role = classify_ride_role(lab, snapshot, cushion_level, weight_class)
        facets = {
            "cushion_level": cushion_level,
            "stability_level": classify_stability(lab, snapshot),
            "weight_class": weight_class,
            "ride_role": ride_role,
            "durability_proxy": classify_durability(snapshot, ride_role),
            "drop_band": classify_drop(snapshot.get("drop_mm")),
        }
        enriched[str(shoe["shoe_id"])] = {
            "facets": facets,
            "metric_snapshot": snapshot,
        }
    return enriched
