"""
Digital extractor — Phase 2.
High fuzzy threshold. Expects explicit fields in printed BDNs.
"""

from __future__ import annotations

from services.extraction_service.base_extractor import BaseExtractor
from core.config_loader import get_config


class DigitalExtractor(BaseExtractor):
    fuzzy_threshold: float = 80.0

    def __init__(self, text: str, ocr_confidence: float = 0.0):
        thr = get_config().get("extraction", {}).get("digital_fuzzy_threshold", 80.0)
        self.fuzzy_threshold = float(thr)
        super().__init__(text, ocr_confidence)

    def extract(self) -> dict:
        """Extract all fields from digital (printed) BDN text."""
        from services.extraction_service.extractor import _extract_common
        return _extract_common(self)
