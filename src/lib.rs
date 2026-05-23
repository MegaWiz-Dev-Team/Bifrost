//! Bifrost library crate. The binary in `main.rs` is the production entry
//! point; this lib exists so integration tests in `tests/` can reach the
//! HTTP-layer modules (`auth_jwt`, `middleware`, `agents`) without going
//! through the swarm-engine / overseer init path.

pub mod auth_jwt;
pub mod middleware;
pub mod agents;
