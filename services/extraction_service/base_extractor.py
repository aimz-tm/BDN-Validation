"""
Base extractor — Phase 2 (improved).
Fixes:
  - Value capping: extracted values truncated at first junk boundary
  - Reject single-word non-name values that are clearly column headers
  - Faster Tesseract: image_to_data only once, extract both text + confidences in one call
  - Broader date/time regex: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, HH:MM
  - Port / supplier / barge value truncation (max ~4 words for proper nouns)
All synonym lists read from config.yaml field_synonyms.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from rapidfuzz import fuzz  # type: ignore
except ImportError:
    from difflib import SequenceMatcher

    class _FuzzFallback:
        @staticmethod
        def token_sort_ratio(a: str, b: str) -> float:
            a_s = " ".join(sorted(a.split()))
            b_s = " ".join(sorted(b.split()))
            return SequenceMatcher(None, a_s, b_s).ratio() * 100.0

    fuzz = _FuzzFallback()  # type: ignore

from core.config_loader import get_config


def _synonyms(field: str) -> list[str]:
    """Return synonym list for a field from config, or empty list."""
    synonyms_cfg = get_config().get("field_synonyms", {})
    return list(synonyms_cfg.get(field, []))


# ── Value sanitation helpers ──────────────────────────────────────────────

# Words that signal we've accidentally grabbed a column header or label instead
# of an actual value — these are valid label words, NOT valid values.
# NOTE: 'port', 'grade', 'type', 'product', 'supplier' are intentionally excluded
# because they appear as legitimate single-word field values on many BDN forms
# (e.g. port="Singapore", fuel_type="VLSFO", supplier="Equatorial").
_HEADER_WORDS = frozenset({
    "name", "no", "no.", "number", "date", "time", "note",
    "quantity", "volume", "mass", "total", "amount",
    "ref", "reference",
    "vessel", "barge", "ship", "tanker",
    "buyer", "receiver", "n/a", "-", "/",
})

# Characters that are never valid in any BDN field value
_GARBAGE_CHARS_RE = re.compile(r'[@<>=\\]|\[\s*\]?')


def _is_garbage(val: str) -> bool:
    """Return True if the value looks like OCR noise rather than real text."""
    if not val:
        return True
    # 2+ garbage-class characters → almost certainly OCR noise
    if len(_GARBAGE_CHARS_RE.findall(val)) >= 2:
        return True
    # Single lowercase letter + space prefix → OCR artifact (e.g. "j Date", "m IMO")
    if re.match(r'^[a-z]\s', val):
        return True
    # Meaningful-char ratio: alphanumeric + common punctuation should be ≥70%
    meaningful = sum(1 for c in val if c.isalnum() or c in " -./,':;()")
    if len(val) > 3 and meaningful / len(val) < 0.70:
        return True
    return False


# Punctuation / noise that marks the end of a useful value
_VALUE_STOP = re.compile(
    r"\s*(?:"
    r"Next\s+Port"           # "Next Port: OP BRAZIL" → stop
    r"|Ticketing\s+Number"   # "Metering Ticketing Number" → stop
    r"|Metering"             # "Bunker Metering" → stop
    r"|Bunker\s+Metering"
    r"|[;|]{2}"              # double delimiter
    r"|\d{2}:\d{2}\s+(?!$)"  # time followed by more text (take the time, stop after)
    r")",
    re.IGNORECASE,
)


def _cap_value(val: str | None, max_words: int = 8) -> str | None:
    """
    Trim extracted value:
    - Stop at known noise phrases
    - Limit to max_words (default 8)
    - Strip trailing punctuation
    - Return None if the resulting value is a known header word
    """
    if val is None:
        return None
    # Stop at noise markers
    m = _VALUE_STOP.search(val)
    if m:
        val = val[: m.start()].strip()
    # Limit words
    words = val.split()
    if len(words) > max_words:
        val = " ".join(words[:max_words])
    val = val.strip(" ,;:|/\\")
    if not val:
        return None
    # Reject single-word values that are clearly column headers
    if val.lower() in _HEADER_WORDS:
        return None
    # Reject OCR garbage
    if _is_garbage(val):
        return None
    return val


def _cap_proper_noun(val: str | None, max_words: int = 5) -> str | None:
    """Tighter cap for port / supplier / barge names."""
    return _cap_value(val, max_words=max_words)


def _cap_vessel_name(val: str | None) -> str | None:
    """Vessel names: allow up to 6 words, stop at digit-heavy tails."""
    if val is None:
        return None
    val = _cap_value(val, max_words=6)
    if val is None:
        return None
    # Trim trailing numbers that look like unrelated data
    val = re.sub(r"\s+\d{4,}$", "", val).strip()
    return val or None


class BaseExtractor:
    """
    Shared extraction logic.
    Subclasses set fuzzy_threshold and may override field extraction methods.
    """

    fuzzy_threshold: float = 75.0

    def __init__(self, text: str, ocr_confidence: float = 0.0):
        self.text = text
        self.ocr_confidence = ocr_confidence

    def find_fuzzy(self, labels: list[str], threshold: float | None = None) -> str | None:
        """
        Fuzzy-match any of the given labels against line content.
        Two passes:
          Pass 1 — same-line: 'Label: Value' (colon-separated)
          Pass 2 — next-line: 'Label:\n(empty lines)\nValue'
        Returns raw value (caller applies _cap_value).
        """
        thr = threshold if threshold is not None else self.fuzzy_threshold
        lines = [l.strip() for l in self.text.split("\n")]
        best_val: str | None = None
        best_score: float = 0.0

        for idx, line in enumerate(lines):
            if not line:
                continue

            # ── Pass 1: colon-separated on same line ──
            parts = re.split(r"[:;|\t]+", line, maxsplit=1)
            if len(parts) == 2:
                key, val = parts[0].strip(), parts[1].strip()
                # Same-line value
                if val:
                    for label in labels:
                        score = fuzz.token_sort_ratio(label.lower(), key.lower())
                        if score >= thr and score > best_score:
                            best_score = score
                            best_val = val
                # Label-only line (no value after colon) — look at next non-empty line
                else:
                    for label in labels:
                        score = fuzz.token_sort_ratio(label.lower(), key.lower())
                        if score >= thr and score > best_score:
                            # Find next non-empty line that isn't itself a label
                            for nidx in range(idx + 1, min(idx + 4, len(lines))):
                                candidate = lines[nidx].strip()
                                if not candidate:
                                    continue
                                # Skip if the candidate itself looks like a label (contains colon)
                                c_parts = re.split(r"[:;|\t]+", candidate, maxsplit=1)
                                if len(c_parts) == 2 and not c_parts[1].strip():
                                    # It's another label-only line, skip
                                    break
                                best_score = score
                                best_val = candidate
                                break

            else:
                # ── Pass 2: positional split (first N words as label) ──
                for label in labels:
                    label_words = label.split()
                    line_words = line.split()
                    n = len(label_words)
                    if len(line_words) > n:
                        potential_key = " ".join(line_words[:n])
                        potential_val = " ".join(line_words[n:])
                        score = fuzz.token_sort_ratio(label.lower(), potential_key.lower())
                        if score >= thr and score > best_score:
                            best_score = score
                            best_val = potential_val

        # ── Pass 3: whitespace-aligned (label + 2+ spaces + value, no colon) ──
        # Handles tabular BDN layouts like:
        #   Port of Delivery    Singapore
        #   Quantity Delivered  1175.25 MT
        if not best_val:
            for label in labels:
                # Match label at start of line, then 2+ spaces, then value
                pattern = rf"(?i)^\s*{re.escape(label)}\s{{2,}}(.+?)\s*$"
                for line in lines:
                    m = re.search(pattern, line)
                    if m:
                        candidate = m.group(1).strip()
                        if candidate:
                            best_val = candidate
                            break
                if best_val:
                    break

        return best_val

    def find(
        self,
        patterns: list[str],
        field: str | None = None,
        extra_labels: list[str] | None = None,
        max_words: int = 8,
    ) -> str | None:
        """
        Regex primary, fuzzy fallback.
        patterns: list of regex strings with one capture group.
        field: config key to look up synonyms.
        extra_labels: additional label strings for fuzzy matching.
        max_words: cap on extracted value length.
        """
        for pattern in patterns:
            m = re.search(pattern, self.text, re.IGNORECASE)
            if m:
                return _cap_value(m.group(1).strip(), max_words=max_words)

        labels: list[str] = []
        if field:
            labels.extend(_synonyms(field))
        if extra_labels:
            labels.extend(extra_labels)
        if labels:
            raw = self.find_fuzzy(labels)
            return _cap_value(raw, max_words=max_words)
        return None

    def find_proper_noun(
        self,
        patterns: list[str],
        field: str | None = None,
        extra_labels: list[str] | None = None,
    ) -> str | None:
        """Like find() but limited to 5 words — for port/supplier/barge names."""
        return self.find(patterns, field, extra_labels, max_words=5)

    def find_number(
        self,
        patterns: list[str],
        field: str | None = None,
        extra_labels: list[str] | None = None,
    ) -> float | None:
        """Extract a numeric value; strip units."""
        val = self.find(patterns, field, extra_labels, max_words=4)
        if val:
            cleaned = re.sub(r"[^\d.]", "", val.split()[0])
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None
