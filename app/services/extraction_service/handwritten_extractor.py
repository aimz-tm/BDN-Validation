"""
Handwritten extractor — Phase 2.
Lower fuzzy threshold. Anchor-date inheritance for timestamps.
SB number optional (FLAG_010). Time-no-colon patterns.
"""

from __future__ import annotations

import re
from app.services.extraction_service.base_extractor import BaseExtractor
from app.core.config_loader import get_config


class HandwrittenExtractor(BaseExtractor):
    fuzzy_threshold: float = 65.0

    def __init__(self, text: str, ocr_confidence: float = 0.0):
        thr = get_config().get("extraction", {}).get("handwritten_fuzzy_threshold", 65.0)
        self.fuzzy_threshold = float(thr)
        super().__init__(text, ocr_confidence)

    def _find_anchor_date(self) -> str | None:
        """Extract most prominent date on document to use as anchor."""
        m = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", self.text)
        if m:
            return m.group(0)
        return None

    def _inherit_date(self, time_only: str | None, anchor: str | None) -> str | None:
        """Combine anchor date + time-only to produce a full timestamp."""
        if not time_only or not anchor:
            return time_only
        # time_only looks like "1430" or "14:30"
        if re.fullmatch(r"\d{4}", time_only):
            t = f"{time_only[:2]}:{time_only[2:]}"
        else:
            t = time_only
        return f"{anchor} {t}"

    def extract(self) -> dict:
        """Extract all fields from handwritten BDN, inheriting anchor date for times."""
        from app.services.extraction_service.extractor import _extract_common
        fields = _extract_common(self)
        anchor = self._find_anchor_date()
        fields["anchor_date_used"] = anchor
        # For handwritten, if start/end only have time (4 digits), build full timestamps
        for key in ("start_time", "end_time"):
            val = fields.get(key)
            if val and re.fullmatch(r"\d{4}", val.strip()):
                fields[key] = self._inherit_date(val.strip(), anchor)
        return fields
