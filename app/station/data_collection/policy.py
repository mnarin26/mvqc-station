"""Data collection save policy.

Thresholds live in the ``settings`` table (editable from the HMI), so changes
take effect without redeploying:
- always save FAIL inspections,
- save PASS whose overall confidence < low_conf_threshold,
- save a random pass_sample_rate fraction of remaining PASS.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class SaveDecision:
    save: bool
    reason: Optional[str]              # FAIL | LOW_CONF | RANDOM | None
    save_full_image: bool


class DataCollectionPolicy:
    def __init__(self, db) -> None:
        self.db = db

    def _read(self) -> dict:
        from ..db.repositories import SettingsRepository

        with self.db.session() as s:
            raw = SettingsRepository(s).all()
        return {
            "low_conf_threshold": float(
                raw.get("data_collection.low_conf_threshold", raw.get("low_conf_threshold", 0.85))
            ),
            "pass_sample_rate": float(
                raw.get("data_collection.pass_sample_rate", raw.get("pass_sample_rate", 0.02))
            ),
            "save_full_image_on_pass": json.loads(
                raw.get(
                    "data_collection.save_full_image_on_pass",
                    raw.get("save_full_image_on_pass", "false"),
                )
            ),
        }

    def decide(self, result: str, overall_confidence: float) -> SaveDecision:
        cfg = self._read()
        if result == "FAIL":
            return SaveDecision(True, "FAIL", save_full_image=True)

        # PASS branch.
        if overall_confidence < cfg["low_conf_threshold"]:
            return SaveDecision(True, "LOW_CONF", save_full_image=cfg["save_full_image_on_pass"])
        if random.random() < cfg["pass_sample_rate"]:
            return SaveDecision(True, "RANDOM", save_full_image=cfg["save_full_image_on_pass"])
        return SaveDecision(False, None, save_full_image=False)
