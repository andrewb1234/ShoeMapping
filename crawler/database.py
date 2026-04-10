"""SQLite database operations for shoe datastore."""

import json
import sqlite3
from pathlib import Path
from typing import Dict, Set

from crawler.runrepeat_crawler import ShoeRecord


def init_database(db_path: Path) -> None:
    """Initialize the SQLite database with the shoes table."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shoes (
                shoe_id TEXT PRIMARY KEY,
                brand TEXT NOT NULL,
                shoe_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                audience_verdict INTEGER,
                lab_test_results TEXT,  -- JSON string
                crawled_at TEXT NOT NULL
            )
        """)
        conn.commit()


def get_existing_shoe_ids(db_path: Path) -> Set[str]:
    """Get set of already crawled shoe IDs for duplicate detection."""
    if not db_path.exists():
        return set()
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT shoe_id FROM shoes")
        return {row[0] for row in cursor.fetchall()}


def save_shoe_records(db_path: Path, records: Dict[str, ShoeRecord]) -> None:
    """Save shoe records to SQLite database using INSERT OR REPLACE."""
    init_database(db_path)
    
    with sqlite3.connect(db_path) as conn:
        for shoe_record in records.values():
            conn.execute("""
                INSERT OR REPLACE INTO shoes 
                (shoe_id, brand, shoe_name, source_url, audience_verdict, lab_test_results, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                shoe_record.shoe_id,
                shoe_record.brand,
                shoe_record.shoe_name,
                shoe_record.source_url,
                shoe_record.audience_verdict,
                json.dumps(shoe_record.lab_test_results),
                shoe_record.crawled_at
            ))
        conn.commit()


def load_shoe_record(db_path: Path, shoe_id: str) -> Dict[str, object]:
    """Load a single shoe record from database."""
    if not db_path.exists():
        return {}
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("""
            SELECT shoe_id, brand, shoe_name, source_url, audience_verdict, 
                   lab_test_results, crawled_at 
            FROM shoes WHERE shoe_id = ?
        """, (shoe_id,))
        
        row = cursor.fetchone()
        if not row:
            return {}
        
        result = {
            "shoe_id": row[0],
            "brand": row[1],
            "shoe_name": row[2],
            "source_url": row[3],
            "lab_test_results": json.loads(row[5]) if row[5] else {},
            "crawled_at": row[6],
        }
        
        if row[4] is not None:
            result["audience_verdict"] = row[4]
            
        return result
