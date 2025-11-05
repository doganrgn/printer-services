# stores.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional
import json, uuid, time

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS_FILE = DATA_DIR / "print_jobs.jsonl"

class JobStore:
    """
    Çok basit bir JSONL store.
    Her satır: {"id": str, "type": "text"|"file", "payload": {...}, "ts": float, "meta": {...}}
    """
    def __init__(self, path: Path = JOBS_FILE):
        self.path = path
        self.path.touch(exist_ok=True)

    def add(self, job_type: str, payload: Dict, meta: Optional[Dict] = None) -> str:
        job_id = str(uuid.uuid4())
        rec = {
            "id": job_id,
            "type": job_type,
            "payload": payload,
            "ts": time.time(),
            "meta": meta or {}
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return job_id

    def list_recent(self, limit: int = 50) -> List[Dict]:
        rows = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return rows[:limit]

    def get(self, job_id: str) -> Optional[Dict]:
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("id") == job_id:
                        return rec
                except Exception:
                    pass
        return None

job_store = JobStore()
