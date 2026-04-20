"""Fluent tile query builder with filtering, sorting, and pagination."""
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class SortOrder(Enum):
    ASC = "asc"
    DESC = "desc"

@dataclass
class QueryResult:
    tiles: list[dict]
    total: int
    page: int
    page_size: int
    query_time_ms: float = 0.0
    facets: dict = field(default_factory=dict)

class TileQueryBuilder:
    def __init__(self, tile_store=None):
        self._store = tile_store
        self._filters: list[dict] = []
        self._domain: str = ""
        self._search: str = ""
        self._tags: list[str] = []
        self._sort_by: str = "created_at"
        self._sort_order: SortOrder = SortOrder.DESC
        self._page: int = 1
        self._page_size: int = 20
        self._min_confidence: float = 0.0
        self._max_confidence: float = 1.0
        self._include_metadata: bool = False

    def domain(self, domain: str) -> "TileQueryBuilder":
        self._domain = domain
        return self

    def search(self, query: str) -> "TileQueryBuilder":
        self._search = query
        return self

    def tags(self, *tags: str) -> "TileQueryBuilder":
        self._tags = list(tags)
        return self

    def confidence(self, min_c: float = 0.0, max_c: float = 1.0) -> "TileQueryBuilder":
        self._min_confidence = min_c
        self._max_confidence = max_c
        return self

    def sort(self, by: str, order: str = "desc") -> "TileQueryBuilder":
        self._sort_by = by
        self._sort_order = SortOrder(order.lower())
        return self

    def page(self, num: int, size: int = 20) -> "TileQueryBuilder":
        self._page = max(1, num)
        self._page_size = max(1, min(100, size))
        return self

    def with_metadata(self) -> "TileQueryBuilder":
        self._include_metadata = True
        return self

    def filter(self, field_name: str, operator: str, value) -> "TileQueryBuilder":
        """Add arbitrary filter: field_name, op (eq/ne/gt/lt/in/contains), value"""
        self._filters.append({"field": field_name, "op": operator, "value": value})
        return self

    def execute(self, tiles: list[dict] = None) -> QueryResult:
        start = time.time()
        source = tiles or (list(self._store._tiles.values()) if self._store and hasattr(self._store, "_tiles") else [])
        results = self._apply_filters(source)
        results = self._apply_sort(results)
        total = len(results)
        results = self._apply_pagination(results)
        elapsed = (time.time() - start) * 1000
        facets = self._compute_facets(source)
        return QueryResult(tiles=results, total=total, page=self._page,
                          page_size=self._page_size, query_time_ms=round(elapsed, 2),
                          facets=facets)

    def _apply_filters(self, tiles: list[dict]) -> list[dict]:
        results = []
        for tile in tiles:
            if self._domain and tile.get("domain") != self._domain:
                continue
            conf = tile.get("confidence", 0.5)
            if conf < self._min_confidence or conf > self._max_confidence:
                continue
            if self._tags:
                tile_tags = set(tile.get("tags", []))
                if not tile_tags.issuperset(set(self._tags)):
                    continue
            if self._search:
                q_words = set(self._search.lower().split())
                content_words = set(tile.get("content", "").lower().split())
                if not q_words & content_words:
                    continue
            # Apply custom filters
            skip = False
            for f in self._filters:
                val = tile.get(f["field"])
                op = f["op"]
                target = f["value"]
                if op == "eq" and val != target: skip = True
                elif op == "ne" and val == target: skip = True
                elif op == "gt" and (val is None or val <= target): skip = True
                elif op == "lt" and (val is None or val >= target): skip = True
                elif op == "in" and val not in target: skip = True
                elif op == "contains" and (val is None or target not in str(val)): skip = True
                if skip: break
            if skip:
                continue
            if not self._include_metadata:
                tile = {k: v for k, v in tile.items() if not k.startswith("_")}
            results.append(tile)
        return results

    def _apply_sort(self, tiles: list[dict]) -> list[dict]:
        if not self._sort_by:
            return tiles
        reverse = self._sort_order == SortOrder.DESC
        return sorted(tiles, key=lambda t: t.get(self._sort_by, 0), reverse=reverse)

    def _apply_pagination(self, tiles: list[dict]) -> list[dict]:
        start = (self._page - 1) * self._page_size
        return tiles[start:start + self._page_size]

    def _compute_facets(self, tiles: list[dict]) -> dict:
        facets = {}
        domains: dict[str, int] = {}
        for t in tiles:
            d = t.get("domain", "unknown")
            domains[d] = domains.get(d, 0) + 1
        if domains:
            facets["domains"] = dict(sorted(domains.items(), key=lambda x: x[1], reverse=True)[:20])
        return facets

    def count(self, tiles: list[dict] = None) -> int:
        """Count matching tiles without fetching them all."""
        return self.execute(tiles).total

    def reset(self) -> "TileQueryBuilder":
        self.__init__(self._store)
        return self

    @property
    def stats(self) -> dict:
        return {"filters": len(self._filters), "domain": self._domain,
                "search": bool(self._search), "tags": len(self._tags),
                "sort": f"{self._sort_by} {self._sort_order.value}",
                "page": f"{self._page}/{self._page_size}"}
