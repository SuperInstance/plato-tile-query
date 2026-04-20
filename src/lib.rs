//! # plato-tile-query
//!
//! Advanced tile query builder — filters, search, sort, pagination.
//!
//! Part of the PLATO framework.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Sort direction for query results.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum SortOrder {
    Asc,
    Desc,
}

/// Filter comparison operators.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum FilterOp {
    Eq,
    Neq,
    Gt,
    Gte,
    Lt,
    Lte,
    Contains,
    StartsWith,
    EndsWith,
    In,
    NotIn,
    Regex,
    Exists,
    TypeIs,
}

impl FilterOp {
    /// String representation matching the Python API.
    pub fn as_str(&self) -> &'static str {
        match self {
            FilterOp::Eq => "eq",
            FilterOp::Neq => "neq",
            FilterOp::Gt => "gt",
            FilterOp::Gte => "gte",
            FilterOp::Lt => "lt",
            FilterOp::Lte => "lte",
            FilterOp::Contains => "contains",
            FilterOp::StartsWith => "starts_with",
            FilterOp::EndsWith => "ends_with",
            FilterOp::In => "in",
            FilterOp::NotIn => "not_in",
            FilterOp::Regex => "regex",
            FilterOp::Exists => "exists",
            FilterOp::TypeIs => "type_is",
        }
    }
}

/// A single filter clause.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Filter {
    pub field: String,
    pub op: String,
    pub value: Option<serde_json::Value>,
}

/// Execution plan with cost estimates and optimization hints.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct QueryPlan {
    pub filters: Vec<Filter>,
    pub search_terms: Vec<String>,
    pub sort_field: String,
    pub sort_order: String,
    pub page: usize,
    pub page_size: usize,
    pub estimated_cost: f64,
    pub index_used: String,
    pub optimization_hints: Vec<String>,
}

/// Cached query entry.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryCache {
    pub key: String,
    pub result: Vec<HashMap<String, serde_json::Value>>,
    pub total: usize,
    pub created_at: f64,
    pub ttl: f64,
    pub hit_count: usize,
    pub query_plan_hash: String,
}

/// Result of executing a tile query.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryResult {
    pub tiles: Vec<HashMap<String, serde_json::Value>>,
    pub total: usize,
    pub page: usize,
    pub page_size: usize,
    pub query_time_ms: f64,
    pub facets: HashMap<String, HashMap<String, usize>>,
    pub cache_hit: bool,
    pub plan: Option<QueryPlan>,
    pub timed_out: bool,
}

impl Default for QueryResult {
    fn default() -> Self {
        Self {
            tiles: Vec::new(),
            total: 0,
            page: 1,
            page_size: 20,
            query_time_ms: 0.0,
            facets: HashMap::new(),
            cache_hit: false,
            plan: None,
            timed_out: false,
        }
    }
}

/// Fluent builder for tile queries.
pub struct TileQueryBuilder {
    filters: Vec<Filter>,
    domain: String,
    search: String,
    tags: Vec<String>,
    sort_by: String,
    sort_order: SortOrder,
    page: usize,
    page_size: usize,
    fields: Vec<String>,
    include_deleted: bool,
    explain: bool,
    cache_ttl: f64,
    timeout_ms: f64,
    facet_fields: Vec<String>,
    post_filter_fn: Option<Box<dyn Fn(&HashMap<String, serde_json::Value>) -> bool + Send + Sync>>,
}

impl Default for TileQueryBuilder {
    fn default() -> Self {
        Self::new()
    }
}

impl TileQueryBuilder {
    pub fn new() -> Self {
        Self {
            filters: Vec::new(),
            domain: String::new(),
            search: String::new(),
            tags: Vec::new(),
            sort_by: "created_at".to_string(),
            sort_order: SortOrder::Desc,
            page: 1,
            page_size: 20,
            fields: Vec::new(),
            include_deleted: false,
            explain: false,
            cache_ttl: 0.0,
            timeout_ms: 5000.0,
            facet_fields: Vec::new(),
            post_filter_fn: None,
        }
    }

    pub fn filter(mut self, field: &str, op: FilterOp, value: Option<serde_json::Value>) -> Self {
        self.filters.push(Filter {
            field: field.to_string(),
            op: op.as_str().to_string(),
            value,
        });
        self
    }

    pub fn search(mut self, query: &str) -> Self {
        self.search = query.to_string();
        self
    }

    pub fn in_domain(mut self, domain: &str) -> Self {
        self.domain = domain.to_string();
        self
    }

    pub fn with_tags(mut self, tags: &[&str]) -> Self {
        self.tags.extend(tags.iter().map(|t| t.to_string()));
        self
    }

    pub fn sort_by(mut self, field: &str, order: SortOrder) -> Self {
        self.sort_by = field.to_string();
        self.sort_order = order;
        self
    }

    pub fn page(mut self, num: usize, size: usize) -> Self {
        self.page = num.max(1);
        self.page_size = size.clamp(1, 100);
        self
    }

    pub fn select(mut self, fields: &[&str]) -> Self {
        self.fields = fields.iter().map(|f| f.to_string()).collect();
        self
    }

    pub fn include_deleted(mut self) -> Self {
        self.include_deleted = true;
        self
    }

    pub fn explain(mut self) -> Self {
        self.explain = true;
        self
    }

    pub fn cache(mut self, ttl: f64) -> Self {
        self.cache_ttl = ttl;
        self
    }

    pub fn timeout(mut self, ms: f64) -> Self {
        self.timeout_ms = ms;
        self
    }

    pub fn facet(mut self, fields: &[&str]) -> Self {
        self.facet_fields = fields.iter().map(|f| f.to_string()).collect();
        self
    }

    pub fn post_filter<F>(mut self, f: F) -> Self
    where
        F: Fn(&HashMap<String, serde_json::Value>) -> bool + Send + Sync + 'static,
    {
        self.post_filter_fn = Some(Box::new(f));
        self
    }

    pub fn reset(&mut self) -> &mut Self {
        self.filters.clear();
        self.domain.clear();
        self.search.clear();
        self.tags.clear();
        self.sort_by = "created_at".to_string();
        self.sort_order = SortOrder::Desc;
        self.page = 1;
        self.page_size = 20;
        self.fields.clear();
        self.include_deleted = false;
        self.explain = false;
        self.cache_ttl = 0.0;
        self.facet_fields.clear();
        self.post_filter_fn = None;
        self
    }

    pub fn build_plan(&self) -> QueryPlan {
        let mut plan = QueryPlan {
            filters: self.filters.clone(),
            search_terms: if self.search.is_empty() {
                Vec::new()
            } else {
                self.search
                    .split(|c: char| !c.is_alphanumeric())
                    .filter(|s| !s.is_empty())
                    .map(|s| s.to_string())
                    .collect()
            },
            sort_field: self.sort_by.clone(),
            sort_order: if self.sort_order == SortOrder::Asc {
                "asc".to_string()
            } else {
                "desc".to_string()
            },
            page: self.page,
            page_size: self.page_size,
            ..Default::default()
        };

        plan.estimated_cost = self.filters.len() as f64 * 0.1;
        if !self.search.is_empty() {
            plan.estimated_cost += 0.3;
        }
        if self.post_filter_fn.is_some() {
            plan.estimated_cost += 0.2;
        }
        plan.estimated_cost = plan.estimated_cost.min(1.0);

        if self.filters.is_empty() && self.search.is_empty() {
            plan.optimization_hints
                .push("Full table scan — add filters to reduce cost".to_string());
        }
        if self.page > 10 {
            plan.optimization_hints
                .push("Deep pagination — consider cursor-based approach".to_string());
        }
        if self.page_size > 50 {
            plan.optimization_hints
                .push("Large page size — may impact latency".to_string());
        }

        plan
    }

    pub fn to_dict(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert(
            "filters".to_string(),
            serde_json::to_value(&self.filters).unwrap_or_default(),
        );
        map.insert("domain".to_string(), self.domain.clone().into());
        map.insert("search".to_string(), self.search.clone().into());
        map.insert("tags".to_string(), self.tags.clone().into());
        map.insert("sort_by".to_string(), self.sort_by.clone().into());
        map.insert(
            "sort_order".to_string(),
            if self.sort_order == SortOrder::Asc {
                "asc"
            } else {
                "desc"
            }
            .into(),
        );
        map.insert("page".to_string(), self.page.into());
        map.insert("page_size".to_string(), self.page_size.into());
        map.insert("fields".to_string(), self.fields.clone().into());
        map.insert("include_deleted".to_string(), self.include_deleted.into());
        map.insert("facet_fields".to_string(), self.facet_fields.clone().into());
        map
    }

    pub fn filter_count(&self) -> usize {
        self.filters.len()
    }

    pub fn has_search(&self) -> bool {
        !self.search.trim().is_empty()
    }

    pub fn complexity(&self) -> &'static str {
        let n = self.filters.len()
            + if self.search.is_empty() { 0 } else { 1 }
            + self.tags.len();
        if n == 0 {
            "simple"
        } else if n <= 3 {
            "moderate"
        } else {
            "complex"
        }
    }
}

/// Simple in-memory cache for query results.
pub struct QueryCacheManager {
    cache: HashMap<String, QueryCache>,
    max_size: usize,
    default_ttl: f64,
    hits: usize,
    misses: usize,
}

impl Default for QueryCacheManager {
    fn default() -> Self {
        Self::new(100, 60.0)
    }
}

impl QueryCacheManager {
    pub fn new(max_size: usize, default_ttl: f64) -> Self {
        Self {
            cache: HashMap::new(),
            max_size,
            default_ttl,
            hits: 0,
            misses: 0,
        }
    }

    fn make_key(&self, query_dict: &HashMap<String, serde_json::Value>) -> String {
        let raw = serde_json::to_string(query_dict).unwrap_or_default();
        md5::compute(raw.as_bytes())
            .iter()
            .map(|b| format!("{:02x}", b))
            .collect::<String>()[..16]
            .to_string()
    }

    pub fn get(&mut self, query_dict: &HashMap<String, serde_json::Value>) -> Option<&QueryCache> {
        let key = self.make_key(query_dict);
        let now = current_time();
        if let Some(entry) = self.cache.get(&key) {
            if now - entry.created_at < entry.ttl {
                // We can't increment hit_count on an immutable reference,
                // so we do a second mutable lookup for stats.
                if let Some(e) = self.cache.get_mut(&key) {
                    e.hit_count += 1;
                }
                self.hits += 1;
                return self.cache.get(&key);
            }
        }
        self.misses += 1;
        None
    }

    pub fn put(
        &mut self,
        query_dict: &HashMap<String, serde_json::Value>,
        tiles: Vec<HashMap<String, serde_json::Value>>,
        total: usize,
        ttl: f64,
    ) {
        if self.cache.len() >= self.max_size {
            self.evict();
        }
        let key = self.make_key(query_dict);
        self.cache.insert(
            key.clone(),
            QueryCache {
                key,
                result: tiles,
                total,
                created_at: current_time(),
                ttl: if ttl > 0.0 { ttl } else { self.default_ttl },
                hit_count: 0,
                query_plan_hash: self.make_key(query_dict),
            },
        );
    }

    fn evict(&mut self) {
        if self.cache.is_empty() {
            return;
        }
        let oldest = self
            .cache
            .iter()
            .min_by(|a, b| a.1.created_at.partial_cmp(&b.1.created_at).unwrap())
            .map(|(k, _)| k.clone());
        if let Some(k) = oldest {
            self.cache.remove(&k);
        }
    }

    pub fn invalidate(&mut self, query_dict: Option<&HashMap<String, serde_json::Value>>) {
        if let Some(qd) = query_dict {
            let key = self.make_key(qd);
            self.cache.remove(&key);
        } else {
            self.cache.clear();
        }
    }

    pub fn clear(&mut self) {
        self.cache.clear();
    }

    pub fn stats(&self) -> HashMap<String, serde_json::Value> {
        let total = self.hits + self.misses;
        let mut map = HashMap::new();
        map.insert("size".to_string(), self.cache.len().into());
        map.insert("max_size".to_string(), self.max_size.into());
        map.insert("hits".to_string(), self.hits.into());
        map.insert("misses".to_string(), self.misses.into());
        map.insert(
            "hit_rate".to_string(),
            if total > 0 {
                (self.hits as f64) / (total as f64)
            } else {
                0.0
            }
            .into(),
        );
        map
    }
}

fn current_time() -> f64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

// Simple md5 implementation to avoid adding a dependency
mod md5 {
    pub fn compute(input: &[u8]) -> [u8; 16] {
        // FNV-1a based fallback for deterministic hashing
        let mut hash: u64 = 0xcbf29ce484222325;
        for &byte in input {
            hash ^= byte as u64;
            hash = hash.wrapping_mul(0x100000001b3);
        }
        let mut out = [0u8; 16];
        out[..8].copy_from_slice(&hash.to_le_bytes());
        out[8..].copy_from_slice(&hash.to_le_bytes());
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_builder_chain() {
        let builder = TileQueryBuilder::new()
            .filter("status", FilterOp::Eq, Some("active".into()))
            .search("hello world")
            .in_domain("main")
            .with_tags(&["a", "b"])
            .sort_by("name", SortOrder::Asc)
            .page(2, 50)
            .select(&["id", "name"]);

        assert_eq!(builder.filter_count(), 1);
        assert!(builder.has_search());
        assert_eq!(builder.complexity(), "complex");
    }

    #[test]
    fn test_build_plan() {
        let builder = TileQueryBuilder::new()
            .filter("x", FilterOp::Gt, Some(10.into()))
            .search("term");
        let plan = builder.build_plan();
        assert_eq!(plan.filters.len(), 1);
        assert_eq!(plan.search_terms, vec!["term"]);
        assert!(plan.estimated_cost > 0.0);
    }

    #[test]
    fn test_cache_manager() {
        let mut cm = QueryCacheManager::new(10, 60.0);
        let mut qd = HashMap::new();
        qd.insert("x".to_string(), serde_json::Value::from(1));
        cm.put(&qd, vec![HashMap::new()], 1, 0.0);
        assert!(cm.get(&qd).is_some());
        assert_eq!(cm.stats()["hits"], serde_json::Value::from(1));
    }
}
