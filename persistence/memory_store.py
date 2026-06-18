"""In-memory transaction store (Phase 0). Replaced by DB repository in Phase 6."""

from __future__ import annotations

from typing import Any


class MemoryTransactionStore:
    def __init__(self) -> None:
        self._by_id: dict[str, dict[str, Any]] = {}

    def save(self, verdict: dict[str, Any]) -> dict[str, Any]:
        tid = verdict["transaction_id"]
        self._by_id[tid] = verdict
        return verdict

    def list_all(
        self,
        *,
        human_review_only: bool = False,
        classification: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = list(self._by_id.values())
        if human_review_only:
            rows = [r for r in rows if r.get("human_review_required")]
        if classification:
            rows = [r for r in rows if r.get("classification") == classification]
        rows.sort(key=lambda r: r.get("validated_at", ""), reverse=True)
        return rows

    def get(self, transaction_id: str) -> dict[str, Any] | None:
        return self._by_id.get(transaction_id)

    def seed(self, verdicts: list[dict[str, Any]]) -> None:
        for v in verdicts:
            self.save(v)


transaction_store = MemoryTransactionStore()
