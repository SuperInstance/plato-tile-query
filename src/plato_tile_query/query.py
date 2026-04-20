"""Tile query builder — filtering, sorting, pagination, caching, explain plan, and facet counts."""
import time
import re
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from collections import defaultdict
from enum import Enum

class SortOrder(Enum):
    ASC = "asc"
    DESC = "desc"

class FilterOp(Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN = "in"
    NOT_IN = "not_in"
    REGEX = "regex"
    EXISTS = "exists"
    TYPE_IS = "type_is"

@dataclass
class QueryPlan:
    filters: list[dict] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)
    sort_field: str = ""
    sort_order: str = ""
    page: int = 1
    page_size: int = 20
    estimated_cost: float = 0.0  # 0.0-1.0, relative cost
    index_used: str = ""
    optimization_hints: list[str] = field(default_factory=list)

@dataclass
class QueryCache:
    key: str
    result: list[dict]
    total: int
    created_at: float
    ttl: float = 60.0
    hit_count: int = 0
    query_plan_hash: str = ""

@dataclass
class QueryResult:
    tiles: list[dict]
    total: int
    page: int
    page_size: int
    query_time_ms: float = 0.0
    facets: dict = field(default_factory=dict)
    cache_hit: bool = False
    plan: Optional[QueryPlan] = None
    timed_out: bool = False

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
        self._fields: list[str] = []
        self._include_deleted: bool = False
        self._explain: bool = False
        self._cache_ttl: float = 0.0
        self._timeout_ms: float = 5000.0
        self._facet_fields: list[str] = []
        self._post_filter_fn: Optional[Callable] = None

    def where(self, field: str, op: str, value: Any = None) -> 'TileQueryBuilder':
        op_enum = FilterOp(op) if isinstance(op, str) else op
        self._filters.append({"field": field, "op": op_enum.value, "value": value})
        return self

    def search(self, query: str) -> 'TileQueryBuilder':
        self._search = query
        return self

    def in_domain(self, domain: str) -> 'TileQueryBuilder':
        self._domain = domain
        return self

    def with_tags(self, *tags: str) -> 'TileQueryBuilder':
        self._tags.extend(tags)
        return self

    def sort_by(self, field: str, order: SortOrder = SortOrder.DESC) -> 'TileQueryBuilder':
        self._sort_by = field
        self._sort_order = order
        return self

    def page(self, num: int, size: int = 20) -> 'TileQueryBuilder':
        self._page = max(1, num)
        self._page_size = max(1, min(100, size))
        return self

    def select(self, *fields: str) -> 'TileQueryBuilder':
        self._fields = list(fields)
        return self

    def include_deleted(self) -> 'TileQueryBuilder':
        self._include_deleted = True
        return self

    def explain(self) -> 'TileQueryBuilder':
        self._explain = True
        return self

    def cache(self, ttl: float = 60.0) -> 'TileQueryBuilder':
        self._cache_ttl = ttl
        return self

    def timeout(self, ms: float) -> 'TileQueryBuilder':
        self._timeout_ms = ms
        return self

    def facet(self, *fields: str) -> 'TileQueryBuilder':
        self._facet_fields = list(fields)
        return self

    def post_filter(self, fn: Callable) -> 'TileQueryBuilder':
        self._post_filter_fn = fn
        return self

    def reset(self) -> 'TileQueryBuilder':
        self._filters.clear()
        self._domain = ""
        self._search = ""
        self._tags.clear()
        self._sort_by = "created_at"
        self._sort_order = SortOrder.DESC
        self._page = 1
        self._page_size = 20
        self._fields.clear()
        self._include_deleted = False
        self._explain = False
        self._cache_ttl = 0.0
        self._facet_fields.clear()
        self._post_filter_fn = None
        return self

    def build_plan(self) -> QueryPlan:
        plan = QueryPlan()
        plan.filters = [dict(f) for f in self._filters]
        plan.search_terms = re.findall(r'\b\w+\b', self._search) if self._search else []
        plan.sort_field = self._sort_by
        plan.sort_order = self._sort_order.value
        plan.page = self._page
        plan.page_size = self._page_size
        # Cost estimation
        plan.estimated_cost = len(self._filters) * 0.1
        if self._search:
            plan.estimated_cost += 0.3  # search is expensive
        if self._post_filter_fn:
            plan.estimated_cost += 0.2
        plan.estimated_cost = min(1.0, plan.estimated_cost)
        # Optimization hints
        if not self._filters and not self._search:
            plan.optimization_hints.append("Full table scan — add filters to reduce cost")
        if self._page > 10:
            plan.optimization_hints.append("Deep pagination — consider cursor-based approach")
        if self._page_size > 50:
            plan.optimization_hints.append("Large page size — may impact latency")
        return plan

    def to_dict(self) -> dict:
        return {
            "filters": self._filters,
            "domain": self._domain,
            "search": self._search,
            "tags": self._tags,
            "sort_by": self._sort_by,
            "sort_order": self._sort_order.value,
            "page": self._page,
            "page_size": self._page_size,
            "fields": self._fields,
            "include_deleted": self._include_deleted,
            "facet_fields": self._facet_fields,
        }

    @property
    def filter_count(self) -> int:
        return len(self._filters)

    @property
    def has_search(self) -> bool:
        return bool(self._search.strip())

    @property
    def complexity(self) -> str:
        n = len(self._filters) + (1 if self._search else 0) + len(self._tags)
        if n == 0: return "simple"
        if n <= 3: return "moderate"
        return "complex"

class QueryCacheManager:
    def __init__(self, max_size: int = 100, default_ttl: float = 60.0):
        self._cache: dict[str, QueryCache] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def _make_key(self, query_dict: dict) -> str:
        raw = str(sorted(query_dict.items()))
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def get(self, query_dict: dict) -> Optional[QueryCache]:
        key = self._make_key(query_dict)
        entry = self._cache.get(key)
        if entry and time.time() - entry.created_at < entry.ttl:
            entry.hit_count += 1
            self._hits += 1
            return entry
        self._misses += 1
        return None

    def put(self, query_dict: dict, tiles: list[dict], total: int, ttl: float = 0.0):
        if len(self._cache) >= self.max_size:
            self._evict()
        key = self._make_key(query_dict)
        self._cache[key] = QueryCache(
            key=key, result=tiles, total=total,
            created_at=time.time(), ttl=ttl or self.default_ttl,
            query_plan_hash=key)

    def _evict(self):
        if not self._cache:
            return
        oldest = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
        del self._cache[oldest]

    def invalidate(self, query_dict: dict = None):
        if query_dict:
            key = self._make_key(query_dict)
            self._cache.pop(key, None)
        else:
            self._cache.clear()

    def clear(self):
        self._cache.clear()

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {"size": len(self._cache), "max_size": self.max_size,
                "hits": self._hits, "misses": self._misses,
                "hit_rate": self._hits / total if total > 0 else 0.0}
