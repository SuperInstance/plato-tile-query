"""Advanced tile query builder."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

class SortOrder(Enum):
    ASC = "asc"
    DESC = "desc"

@dataclass
class Filter:
    field: str
    operator: str  # eq, ne, gt, lt, gte, lte, contains, in
    value: any

@dataclass
class QueryResult:
    items: list[dict]
    total: int
    page: int
    per_page: int
    filtered_total: int

class QueryBuilder:
    def __init__(self, collection: list[dict] = None):
        self._collection = collection or []
        self._filters: list[Filter] = []
        self._sort_field: str = ""
        self._sort_order: SortOrder = SortOrder.DESC
        self._page: int = 1
        self._per_page: int = 20
        self._search: str = ""
        self._fields: list[str] = []

    def from_collection(self, collection: list[dict]) -> 'QueryBuilder':
        self._collection = collection
        return self

    def where(self, field: str, op: str, value: any) -> 'QueryBuilder':
        self._filters.append(Filter(field=field, operator=op, value=value))
        return self

    def domain(self, domain: str) -> 'QueryBuilder':
        return self.where("domain", "eq", domain)

    def confidence_min(self, min_conf: float) -> 'QueryBuilder':
        return self.where("confidence", "gte", min_conf)

    def confidence_max(self, max_conf: float) -> 'QueryBuilder':
        return self.where("confidence", "lte", max_conf)

    def priority(self, priority: str) -> 'QueryBuilder':
        return self.where("priority", "eq", priority)

    def search(self, query: str) -> 'QueryBuilder':
        self._search = query
        return self

    def sort_by(self, field: str, order: str = "desc") -> 'QueryBuilder':
        self._sort_field = field
        self._sort_order = SortOrder(order)
        return self

    def page(self, num: int) -> 'QueryBuilder':
        self._page = num
        return self

    def per_page(self, n: int) -> 'QueryBuilder':
        self._per_page = n
        return self

    def select(self, *fields: str) -> 'QueryBuilder':
        self._fields = list(fields)
        return self

    def execute(self) -> QueryResult:
        results = list(self._collection)
        # Apply filters
        for f in self._filters:
            results = [item for item in results if self._match(item, f)]
        # Apply search
        if self._search:
            q = self._search.lower()
            results = [item for item in results
                      if q in str(item.get("content", "")).lower()
                      or q in str(item.get("domain", "")).lower()
                      or q in str(item.get("id", "")).lower()]
        # Apply sort
        if self._sort_field:
            reverse = self._sort_order == SortOrder.DESC
            results.sort(key=lambda x: x.get(self._sort_field, 0), reverse=reverse)
        # Project fields
        if self._fields:
            results = [{k: item.get(k) for k in self._fields if k in item} for item in results]
        filtered_total = len(results)
        # Paginate
        start = (self._page - 1) * self._per_page
        end = start + self._per_page
        page_items = results[start:end]
        return QueryResult(items=page_items, total=len(self._collection),
                          page=self._page, per_page=self._per_page,
                          filtered_total=filtered_total)

    def _match(self, item: dict, f: Filter) -> bool:
        val = item.get(f.field)
        if val is None:
            return False
        ops = {"eq": lambda a, b: a == b, "ne": lambda a, b: a != b,
               "gt": lambda a, b: a > b, "lt": lambda a, b: a < b,
               "gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b,
               "contains": lambda a, b: b in str(a) if a else False,
               "in": lambda a, b: a in b}
        fn = ops.get(f.operator)
        if fn:
            try:
                return fn(val, f.value)
            except (TypeError, ValueError):
                return False
        return False

    def count(self) -> int:
        return len(self.execute().items)

class TileQuery:
    """High-level tile query interface."""
    def __init__(self, tiles: list[dict] = None):
        self._tiles = tiles or []
        self._builder = QueryBuilder(self._tiles)

    def find(self, query: str = "", domain: str = "", min_conf: float = 0.0,
             priority: str = "", sort: str = "confidence", limit: int = 20) -> list[dict]:
        b = QueryBuilder(self._tiles)
        if query:
            b.search(query)
        if domain:
            b.domain(domain)
        if min_conf > 0:
            b.confidence_min(min_conf)
        if priority:
            b.priority(priority)
        if sort:
            b.sort_by(sort, "desc")
        b.per_page(limit)
        result = b.execute()
        return result.items

    def top_n(self, n: int = 5, field: str = "confidence") -> list[dict]:
        return self.find(min_conf=0.0, sort=field, limit=n)
