#!/usr/bin/env python3
"""Generate a compact JSON shoe catalog from SQLite for Vercel deployment."""

import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, List

from webapp.services import safe_json_loads, display_name

def main() -> None:
    db_path = Path("data/runrepeat_lab_tests.sqlite")
    output_path = Path("data/shoes.catalog.json")
    
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    print(f"Loading shoes from {db_path}...")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT shoe_id, brand, shoe_name, source_url, audience_verdict,
                   lab_test_results, crawled_at
            FROM shoes
            ORDER BY brand, shoe_name
            """
        )
        rows = cursor.fetchall()
    
    catalog: List[Dict[str, Any]] = []
    
    for row in rows:
        shoe_id, brand, shoe_name, source_url, audience_verdict, lab_json, crawled_at = row
        lab_results = safe_json_loads(lab_json)
        
        # Build compact shoe record
        catalog.append({
            "shoe_id": str(shoe_id),
            "brand": str(brand),
            "shoe_name": str(shoe_name),
            "display_name": display_name(str(brand), str(shoe_name)),
            "terrain": lab_results.get("Terrain"),
            "source_url": str(source_url),
            "crawled_at": str(crawled_at),
            "audience_verdict": None if audience_verdict is None else int(audience_verdict),
            # Keep full lab results for statistics endpoint
            "lab_test_results": lab_results,
        })
    
    # Write catalog
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, separators=(",", ":"), ensure_ascii=False)
    
    print(f"Generated {output_path} with {len(catalog)} shoes")
    print(f"Size: {output_path.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    main()
