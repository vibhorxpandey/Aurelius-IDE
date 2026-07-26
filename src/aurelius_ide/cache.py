"""Content-addressed result cache.

This is the component that makes live analysis viable. Verifying a citation costs one to
four HTTP round trips against OpenAlex/Crossref/arXiv — perhaps 400ms. A paper with 60
references would take half a minute to check, and re-checking on every keystroke is
obviously impossible.

The insight is that a citation's verdict depends only on the *citation*, not on the
document containing it. So we key results on a hash of the semantic content of the unit
being analyzed. Editing the introduction cannot invalidate a bibliography entry's verdict,
because that entry's hash didn't change. In practice a warm cache means only genuinely
new or edited references hit the network.

Entries are held in memory and mirrored to disk, so restarting the editor doesn't throw
away a session's worth of verification work.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .config import get_cache_dir

# Verification verdicts are stable but not eternal: papers get retracted, and a
# 'not_found' can become 'verified' once an index catches up. A week balances freshness
# against the cost of re-verifying an entire bibliography.
DEFAULT_TTL_SECONDS = 7 * 24 * 3600


class ResultCache:
    """Thread-safe TTL cache with optional disk persistence."""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        path: Optional[Path] = None,
        persist: bool = True,
    ) -> None:
        self.ttl = ttl_seconds
        self._lock = threading.RLock()
        self._mem: Dict[str, Dict[str, Any]] = {}
        self._persist = persist
        self._path = path or (get_cache_dir() / "analysis_cache.json")
        self._dirty = False
        if persist:
            self._load()

    @staticmethod
    def key(analyzer: str, content_hash: str) -> str:
        return f"{analyzer}:{content_hash}"

    def get(self, analyzer: str, content_hash: str) -> Optional[Any]:
        k = self.key(analyzer, content_hash)
        with self._lock:
            record = self._mem.get(k)
            if record is None:
                return None
            if time.time() - record["at"] > self.ttl:
                self._mem.pop(k, None)
                self._dirty = True
                return None
            return record["value"]

    def set(self, analyzer: str, content_hash: str, value: Any) -> None:
        with self._lock:
            self._mem[self.key(analyzer, content_hash)] = {"at": time.time(), "value": value}
            self._dirty = True

    def invalidate(self, analyzer: str, content_hash: str) -> None:
        with self._lock:
            if self._mem.pop(self.key(analyzer, content_hash), None) is not None:
                self._dirty = True

    def clear(self) -> None:
        with self._lock:
            self._mem.clear()
            self._dirty = True
            self.flush()

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"entries": len(self._mem)}

    # -- persistence --------------------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        now = time.time()
        with self._lock:
            self._mem = {
                k: v
                for k, v in raw.items()
                if isinstance(v, dict) and now - v.get("at", 0) <= self.ttl
            }

    def flush(self) -> None:
        """Best-effort write-through. Cache loss is never worth crashing an editor over."""
        if not self._persist or not self._dirty:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                self._path.write_text(json.dumps(self._mem), encoding="utf-8")
                self._dirty = False
        except (OSError, TypeError, ValueError):
            pass
