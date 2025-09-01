from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict
import json


@dataclass
class Metrics:
    """Lightweight counters for effective-date enrichment.

    Single responsibility: collect counters and emit a summary.
    """

    processed: int = 0
    definitive: int = 0
    estimated: int = 0
    promoted: int = 0
    followup_used: int = 0

    def record(self, *, effective_date: bool, had_estimate: bool, promoted: bool, followup_used: bool) -> None:
        self.processed += 1
        if effective_date:
            self.definitive += 1
        if had_estimate and not effective_date:
            self.estimated += 1
        if promoted:
            self.promoted += 1
        if followup_used:
            self.followup_used += 1

    def summary(self) -> Dict[str, float]:
        p = max(self.processed, 1)
        return {
            "processed": self.processed,
            "definitive": self.definitive,
            "estimated": self.estimated,
            "promoted": self.promoted,
            "followup_used": self.followup_used,
            "fill_rate": round(self.definitive / p, 4),
            "est_or_def_rate": round((self.definitive + self.estimated) / p, 4),
        }

    def print_summary(self) -> None:
        s = self.summary()
        print("\n[Metrics] Effective-date enrichment summary:")
        print(json.dumps(s, indent=2))

    def save_jsonl(self, file_path: str) -> None:
        payload = {
            **asdict(self),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **{k: v for k, v in self.summary().items() if k not in {"processed", "definitive", "estimated", "promoted", "followup_used"}},
        }
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
