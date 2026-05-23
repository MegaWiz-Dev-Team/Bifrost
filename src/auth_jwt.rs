//! JWT validation middleware for Yggdrasil/Zitadel-issued tokens (Sprint 52).
//!
//! Heimdall accepts either static `API_KEYS` (legacy) or RS256-signed JWTs
//! issued by a configured OIDC issuer. Set `YGGDRASIL_ISSUER` and
//! `JWT_AUDIENCE` to enable JWT mode; both auth modes can coexist on the
//! same gateway (heuristic: bearer tokens starting with `ey` are routed
//! to JWT validation, others to static-key compare).
//!
//! JWKS and OIDC discovery responses are cached with a 1h TTL via moka.
//! Audit events emit on `tracing` at INFO/WARN — Tyr's filebeat tail picks
//! them up (see [feedback_include_tyr_in_pii_designs]).

use jsonwebtoken::{decode, decode_header, jwk::JwkSet, Algorithm, DecodingKey, Validation};
use moka::future::Cache;
use serde::Deserialize;
use std::sync::Arc;
use std::time::Duration;

#[derive(Debug, Clone, Deserialize)]
pub struct Claims {
    pub sub: String,
    pub iss: String,
    pub exp: usize,
    #[serde(default)]
    pub aud: Option<serde_json::Value>,
    #[serde(default)]
    pub scope: Option<String>,
    /// Zitadel tenant org id — maps to Asgard tenant via Yggdrasil SDK.
    #[serde(default, rename = "urn:zitadel:iam:org:id")]
    pub tenant_id: Option<String>,
    #[serde(default)]
    pub roles: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Deserialize)]
struct OidcDiscovery {
    jwks_uri: String,
}

#[derive(Debug)]
pub enum JwtError {
    InvalidHeader(String),
    MissingKid,
    KeyNotFound(String),
    Discovery(String),
    Jwks(String),
    Decode(String),
}

impl std::fmt::Display for JwtError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidHeader(e) => write!(f, "invalid jwt header: {e}"),
            Self::MissingKid => write!(f, "jwt header missing kid"),
            Self::KeyNotFound(kid) => write!(f, "jwks has no key for kid={kid}"),
            Self::Discovery(e) => write!(f, "oidc discovery failed: {e}"),
            Self::Jwks(e) => write!(f, "jwks fetch failed: {e}"),
            Self::Decode(e) => write!(f, "jwt decode/verify failed: {e}"),
        }
    }
}

impl std::error::Error for JwtError {}

pub struct JwtValidator {
    issuer: String,
    audience: String,
    http_client: reqwest::Client,
    jwks_cache: Cache<String, Arc<JwkSet>>,
    discovery_cache: Cache<String, Arc<OidcDiscovery>>,
}

impl JwtValidator {
    pub fn new(issuer: String, audience: String) -> Self {
        let http_client = reqwest::Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .expect("reqwest client builder");
        Self {
            issuer,
            audience,
            http_client,
            jwks_cache: Cache::builder()
                .time_to_live(Duration::from_secs(3600))
                .max_capacity(8)
                .build(),
            discovery_cache: Cache::builder()
                .time_to_live(Duration::from_secs(3600))
                .max_capacity(8)
                .build(),
        }
    }

    pub async fn validate(&self, token: &str) -> Result<Claims, JwtError> {
        let header = decode_header(token).map_err(|e| JwtError::InvalidHeader(e.to_string()))?;
        let kid = header.kid.ok_or(JwtError::MissingKid)?;

        let jwks_uri = self.resolve_jwks_uri().await?;
        let jwks = self.fetch_jwks(&jwks_uri).await?;

        let jwk = jwks
            .find(&kid)
            .ok_or_else(|| JwtError::KeyNotFound(kid.clone()))?;
        let key = DecodingKey::from_jwk(jwk).map_err(|e| JwtError::Decode(e.to_string()))?;

        let mut validation = Validation::new(Algorithm::RS256);
        validation.set_issuer(&[&self.issuer]);
        validation.set_audience(&[&self.audience]);

        let data = decode::<Claims>(token, &key, &validation)
            .map_err(|e| JwtError::Decode(e.to_string()))?;

        Ok(data.claims)
    }

    async fn resolve_jwks_uri(&self) -> Result<String, JwtError> {
        if let Some(d) = self.discovery_cache.get(&self.issuer).await {
            return Ok(d.jwks_uri.clone());
        }
        let url = format!(
            "{}/.well-known/openid-configuration",
            self.issuer.trim_end_matches('/')
        );
        let discovery: OidcDiscovery = self
            .http_client
            .get(&url)
            .send()
            .await
            .map_err(|e| JwtError::Discovery(e.to_string()))?
            .error_for_status()
            .map_err(|e| JwtError::Discovery(e.to_string()))?
            .json()
            .await
            .map_err(|e| JwtError::Discovery(e.to_string()))?;
        let jwks_uri = discovery.jwks_uri.clone();
        self.discovery_cache
            .insert(self.issuer.clone(), Arc::new(discovery))
            .await;
        Ok(jwks_uri)
    }

    async fn fetch_jwks(&self, jwks_uri: &str) -> Result<Arc<JwkSet>, JwtError> {
        if let Some(jwks) = self.jwks_cache.get(jwks_uri).await {
            return Ok(jwks);
        }
        let jwks: JwkSet = self
            .http_client
            .get(jwks_uri)
            .send()
            .await
            .map_err(|e| JwtError::Jwks(e.to_string()))?
            .error_for_status()
            .map_err(|e| JwtError::Jwks(e.to_string()))?
            .json()
            .await
            .map_err(|e| JwtError::Jwks(e.to_string()))?;
        let arc = Arc::new(jwks);
        self.jwks_cache
            .insert(jwks_uri.to_string(), arc.clone())
            .await;
        Ok(arc)
    }

    #[cfg(test)]
    async fn seed_discovery(&self, jwks_uri: String) {
        self.discovery_cache
            .insert(self.issuer.clone(), Arc::new(OidcDiscovery { jwks_uri }))
            .await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use jsonwebtoken::{encode, EncodingKey, Header};
    use serde_json::json;
    use std::time::{SystemTime, UNIX_EPOCH};
    use wiremock::matchers::{method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    // === Test RSA keypair (TEST ONLY — generated 2026-05-17, never used in prod) ===
    const TEST_PRIVATE_PEM: &str = "-----BEGIN PRIVATE KEY-----\n\
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCuNazhOcfCwP6Q\n\
ORwbKB76yrzpMgjs4QO/OAgJoqWwoBedTlJv3aUmTc1qdD3d6/c7uq8jgJkuMq+7\n\
P/JGjDoUYUYBnaewfHwOSh0vOoZnRPHzp5tM524P9Atpqc1rDU++M1DoZd4P2/4r\n\
Vz0j1OEqS/DgqmiCPOYIaeoFMmiFc8YmBwQ3flu025z/4Yk70zB23h6c80Wu/2Zi\n\
lOcxJoZ5bnhaGi+a+dF19aSKeHW24UogY3dLJeRbzCUn/Fmdl2gIJ+8Oo/gvNaCA\n\
tWOgUpdVFIwKmqCdENMI/tPHrLdFc+z1i7S6UFRFK5D77Y8H4O/YPTarXQgiKkPP\n\
gHi23pgVAgMBAAECggEAKOvl1LAQawCPq4wmvIBTqqCl+Hcu3onKqge855qDpjYs\n\
5eAogCuF6DX9aySsBa2wkSC8lC/Yi6APZIJUZFr7J59j5OxGIDBVqbuiGF58hNSO\n\
qyfzVIDGe0vdxG/FF4D0et6uAjEvlPUdwsuGypxuWdOl3PhafUFV3aMXfCoHoFUZ\n\
00Vc/ngeehjMwiBkDb3h4czaWQnwIO86rshoDdfbQpWCMABSyXqLv9pxioR4mOq4\n\
GHjdtRH+Pt6mDVes2HEfo/hv2ZUmlhN/yO7zSmVFWV4Dy4yTpmmXoc7URHayhut3\n\
SMKOWEBNHzfQ4ESHuYRiH6ZiGR8W4w8+UZa+x6iE0QKBgQD2O2BHb7KXurOf4pMc\n\
PsUR1v2DuTMDb8diSm1E7Rt0z6LflCc1vHT4YLDeOvVuKmgWpPodDXUJjgvHCOkF\n\
6u2lAuz/50uEN2ZkWMQ9lVuMXq1VOWlZySKZvsf78Xaccf8aVF8NFYK7OLy6r3YH\n\
rqec0YUJA3A25zLo0iH5ipDdvQKBgQC1Ht9fWfc8R0MBZdMGYAaNHW7f63Q1yzCs\n\
FWBRTUQDrdLNEoCC/VG3pKj30RQ1tqxizDBnBYwD+MxVcOeSdHpzNNrz6MtZtwDv\n\
Gu8XVjYuJdlQQCl7hr3XDcrRXPNyQtCOFG0zJnnhMczQ7RDq6nAITUcLhBGzc/xp\n\
qvpmFt8tOQKBgA1yYqikDfHBTWvu2K/TMbnurruR0ppecVoJzHvWIwi3CiMBmT6T\n\
AyRJS39nYt3YTQTnj40knf6elkARWYBsOvwm88Bp5jLbP6k9O8JNNMmupfKghwNT\n\
O6N/yrYUkrCqfQ74CpTRVulYiN39FQoIXLjwrD44xNkKuToDt71D9vNVAoGBAJm0\n\
jnn7/m3gSAPqptBVM5oULWDID4ILYs3XAjtc5+h7Xlb8aaVAV1YS3fYZMB55XQgn\n\
Irh7I5zHSpkDzPIj+TrF0z6FA/Wp8Zf48oiKeEZnhmmtWcbjzT2xDbrpOAxymUzK\n\
FvX+pBYxThDL7rx9of/ZnP4v4Vm6h64hFIkIxfM5AoGAD5kkcMLv6ofBYNW3LxFL\n\
ulRy+olN705X1sJZdQqDvjr4tT5083aetElhKRjky9FtaO0i00ZqF/AAVG7nwori\n\
8a9cwk4aLt1LduHzbYhhqRn1EHIsEMa81dgXdA34fC29oOBJu/JHhgcB0BIkzzQe\n\
xGYc5U6M/Zw9SyZb+QBKlzo=\n\
-----END PRIVATE KEY-----\n";

    const TEST_JWK_N: &str = "rjWs4TnHwsD-kDkcGyge-sq86TII7OEDvzgICaKlsKAXnU5Sb92lJk3NanQ93ev3O7qvI4CZLjKvuz_yRow6FGFGAZ2nsHx8DkodLzqGZ0Tx86ebTOduD_QLaanNaw1PvjNQ6GXeD9v-K1c9I9ThKkvw4KpogjzmCGnqBTJohXPGJgcEN35btNuc_-GJO9Mwdt4enPNFrv9mYpTnMSaGeW54WhovmvnRdfWkinh1tuFKIGN3SyXkW8wlJ_xZnZdoCCfvDqP4LzWggLVjoFKXVRSMCpqgnRDTCP7Tx6y3RXPs9Yu0ulBURSuQ--2PB-Dv2D02q10IIipDz4B4tt6YFQ";
    const TEST_JWK_E: &str = "AQAB";
    const TEST_KID: &str = "heimdall-test-key-1";

    fn jwks_response() -> serde_json::Value {
        json!({
            "keys": [{
                "kty": "RSA",
                "kid": TEST_KID,
                "use": "sig",
                "alg": "RS256",
                "n": TEST_JWK_N,
                "e": TEST_JWK_E,
            }]
        })
    }

    fn now() -> usize {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs() as usize
    }

    fn sign_token(claims: serde_json::Value, kid: &str) -> String {
        let mut header = Header::new(Algorithm::RS256);
        header.kid = Some(kid.to_string());
        let key = EncodingKey::from_rsa_pem(TEST_PRIVATE_PEM.as_bytes())
            .expect("test private pem");
        encode(&header, &claims, &key).expect("sign token")
    }

    async fn start_jwks_server() -> MockServer {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/keys"))
            .respond_with(ResponseTemplate::new(200).set_body_json(jwks_response()))
            .mount(&server)
            .await;
        server
    }

    fn build_validator(issuer: &str, audience: &str) -> JwtValidator {
        JwtValidator::new(issuer.to_string(), audience.to_string())
    }

    #[tokio::test]
    async fn validates_well_formed_token() {
        let server = start_jwks_server().await;
        let issuer = server.uri();
        let audience = "heimdall";
        let validator = build_validator(&issuer, audience);
        validator
            .seed_discovery(format!("{}/keys", server.uri()))
            .await;

        let token = sign_token(
            json!({
                "sub": "machine-user@yggdrasil",
                "iss": issuer,
                "aud": audience,
                "exp": now() + 3600,
                "scope": "llm:invoke",
                "urn:zitadel:iam:org:id": "asgard_medical",
            }),
            TEST_KID,
        );

        let claims = validator.validate(&token).await.expect("valid");
        assert_eq!(claims.sub, "machine-user@yggdrasil");
        assert_eq!(claims.tenant_id.as_deref(), Some("asgard_medical"));
        assert_eq!(claims.scope.as_deref(), Some("llm:invoke"));
    }

    #[tokio::test]
    async fn rejects_expired_token() {
        let server = start_jwks_server().await;
        let issuer = server.uri();
        let validator = build_validator(&issuer, "heimdall");
        validator
            .seed_discovery(format!("{}/keys", server.uri()))
            .await;

        let token = sign_token(
            json!({
                "sub": "u", "iss": issuer, "aud": "heimdall",
                // 1h past expiry — well outside jsonwebtoken's default 60s leeway
                "exp": now() - 3600,
            }),
            TEST_KID,
        );
        let err = validator.validate(&token).await.unwrap_err();
        assert!(matches!(err, JwtError::Decode(_)), "got: {err:?}");
    }

    #[tokio::test]
    async fn rejects_wrong_issuer() {
        let server = start_jwks_server().await;
        let validator = build_validator("https://expected.example.com", "heimdall");
        validator
            .seed_discovery(format!("{}/keys", server.uri()))
            .await;

        let token = sign_token(
            json!({
                "sub": "u",
                "iss": "https://wrong.example.com",
                "aud": "heimdall",
                "exp": now() + 3600,
            }),
            TEST_KID,
        );
        let err = validator.validate(&token).await.unwrap_err();
        assert!(matches!(err, JwtError::Decode(_)));
    }

    #[tokio::test]
    async fn rejects_wrong_audience() {
        let server = start_jwks_server().await;
        let issuer = server.uri();
        let validator = build_validator(&issuer, "heimdall");
        validator
            .seed_discovery(format!("{}/keys", server.uri()))
            .await;

        let token = sign_token(
            json!({
                "sub": "u", "iss": issuer, "aud": "some-other-service",
                "exp": now() + 3600,
            }),
            TEST_KID,
        );
        let err = validator.validate(&token).await.unwrap_err();
        assert!(matches!(err, JwtError::Decode(_)));
    }

    #[tokio::test]
    async fn rejects_unknown_kid() {
        let server = start_jwks_server().await;
        let issuer = server.uri();
        let validator = build_validator(&issuer, "heimdall");
        validator
            .seed_discovery(format!("{}/keys", server.uri()))
            .await;

        let token = sign_token(
            json!({
                "sub": "u", "iss": issuer, "aud": "heimdall",
                "exp": now() + 3600,
            }),
            "unknown-kid",
        );
        let err = validator.validate(&token).await.unwrap_err();
        assert!(matches!(err, JwtError::KeyNotFound(_)), "got: {err:?}");
    }

    #[tokio::test]
    async fn rejects_garbage_token() {
        let validator = build_validator("https://x", "heimdall");
        let err = validator.validate("not.a.jwt").await.unwrap_err();
        assert!(matches!(err, JwtError::InvalidHeader(_)));
    }

    #[tokio::test]
    async fn jwks_is_cached_across_calls() {
        let server = start_jwks_server().await;
        let issuer = server.uri();
        let validator = build_validator(&issuer, "heimdall");
        validator
            .seed_discovery(format!("{}/keys", server.uri()))
            .await;

        let token = sign_token(
            json!({
                "sub": "u", "iss": issuer, "aud": "heimdall",
                "exp": now() + 3600,
            }),
            TEST_KID,
        );
        validator.validate(&token).await.expect("first");
        validator.validate(&token).await.expect("second");
        let received = server.received_requests().await.unwrap();
        let jwks_hits = received.iter().filter(|r| r.url.path() == "/keys").count();
        assert_eq!(jwks_hits, 1, "JWKS endpoint should be hit exactly once (cache)");
    }

    #[tokio::test]
    async fn oidc_discovery_resolves_jwks_uri() {
        let server = MockServer::start().await;
        let jwks_path = "/oauth/v2/keys";
        Mock::given(method("GET"))
            .and(path("/.well-known/openid-configuration"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "issuer": server.uri(),
                "jwks_uri": format!("{}{}", server.uri(), jwks_path),
            })))
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path(jwks_path))
            .respond_with(ResponseTemplate::new(200).set_body_json(jwks_response()))
            .mount(&server)
            .await;

        let issuer = server.uri();
        let validator = build_validator(&issuer, "heimdall");

        let token = sign_token(
            json!({
                "sub": "u", "iss": issuer, "aud": "heimdall",
                "exp": now() + 3600,
            }),
            TEST_KID,
        );
        validator.validate(&token).await.expect("discovery path works");
    }
}
