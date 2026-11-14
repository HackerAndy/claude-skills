//! Random-enough hex ids for traces and spans, without a dependency.

use std::collections::hash_map::RandomState;
use std::hash::{BuildHasher, Hasher};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static COUNTER: AtomicU64 = AtomicU64::new(0);

/// `length` hex characters (at most 16).
pub(crate) fn random_hex(length: usize) -> String {
    let mut hasher = RandomState::new().build_hasher();
    hasher.write_u64(COUNTER.fetch_add(1, Ordering::Relaxed));
    hasher.write_u128(SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |since| since.as_nanos()));
    let mut hex = format!("{:016x}", hasher.finish());
    hex.truncate(length);
    hex
}
