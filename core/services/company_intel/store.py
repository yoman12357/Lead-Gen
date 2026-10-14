from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class CompanyIntelRunStore:
    """Lightweight JSON run store for deterministic company-intel PDF downloads."""

    def __init__(self, path: str | Path = "data/company_intel_runs.json") -> None:
        self.path = Path(path)

    def save_run(self, payload: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        runs = self.list_runs()
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("run_id is required")
        updated = False
        for index, existing in enumerate(runs):
            if existing.get("run_id") == run_id:
                runs[index] = payload
                updated = True
                break
        if not updated:
            runs.append(payload)
        self.path.write_text(json.dumps(runs[-500:], indent=2, ensure_ascii=False), encoding="utf-8")

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        selected = str(run_id or "").strip()
        if not selected:
            return None
        for run in self.list_runs():
            if run.get("run_id") == selected:
                return run
        return None

    def list_runs(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]

