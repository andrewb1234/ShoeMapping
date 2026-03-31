#!/usr/bin/env python3
"""
Pre-compute top-N recommendations for every shoe in the catalog.

Generates data/precomputed_recommendations.json which the webapp reads
at runtime on Vercel instead of running ML inference live.

Usage:
    source env/bin/activate
    python precompute_recommendations.py

Re-run whenever shoes are added (after running generate_catalog.py).
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Import existing services
from webapp.services import ShoeCatalogService
from supervised_matching_service import get_matching_service

TOP_K = 15  # recommendations stored per shoe (extra for reject/replace)
OUTPUT_PATH = Path("data/precomputed_recommendations.json")


def precompute() -> Dict[str, Any]:
    """Return a dict keyed by shoe_id with top-K recommendations."""

    catalog = ShoeCatalogService()
    shoes = catalog.list_shoes()
    supervised = get_matching_service()

    print(f"Computing recommendations for {len(shoes)} shoes (top {TOP_K} each)...")

    results: Dict[str, List[Dict[str, Any]]] = {}
    errors: List[str] = []
    t0 = time.time()

    for i, shoe in enumerate(shoes):
        shoe_id = shoe["shoe_id"]
        query = f"{shoe['brand']} {shoe['shoe_name']}"

        try:
            recs = supervised.get_recommendations(
                shoe_name=query,
                top_k=TOP_K,
                exclude_same_brand=False,
            )
        except Exception as exc:
            errors.append(f"{shoe_id}: {exc}")
            continue

        if "error" in recs:
            errors.append(f"{shoe_id}: {recs['error']}")
            continue

        top_recs: List[Dict[str, Any]] = []
        for rec in recs.get("recommendations", [])[:TOP_K]:
            other = catalog.get_shoe_by_id(rec["shoe_id"])
            if not other:
                continue
            top_recs.append({
                "shoe_id": rec["shoe_id"],
                "brand": other["brand"],
                "shoe_name": other["shoe_name"],
                "display_name": other["display_name"],
                "terrain": other.get("terrain"),
                "audience_verdict": other.get("audience_verdict"),
                "similarity_score": rec["similarity_score"],
                "source_url": other["source_url"],
            })

        results[shoe_id] = top_recs

        if (i + 1) % 50 == 0 or (i + 1) == len(shoes):
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(shoes) - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{len(shoes)}] {rate:.1f} shoes/sec  ETA {eta:.0f}s")

    if errors:
        print(f"\n⚠  {len(errors)} shoes had errors (skipped):")
        for e in errors[:10]:
            print(f"   • {e}")
        if len(errors) > 10:
            print(f"   ... and {len(errors) - 10} more")

    return results


def main() -> None:
    results = precompute()

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, separators=(",", ":"), ensure_ascii=False)

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    size_mb = size_kb / 1024

    print(f"\n✅  Wrote {OUTPUT_PATH}")
    print(f"   Shoes with recs: {len(results)}")
    print(f"   File size:       {size_kb:.0f} KB ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
