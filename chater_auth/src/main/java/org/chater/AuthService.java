package org.chater;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.api.client.googleapis.auth.oauth2.GoogleIdToken;
import com.google.api.client.googleapis.auth.oauth2.GoogleIdTokenVerifier;
import com.google.api.client.http.javanet.NetHttpTransport;
import com.google.api.client.json.gson.GsonFactory;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtParser;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.json.JSONObject;

import javax.crypto.SecretKey;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.RSAPublicKeySpec;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Base64;
import java.util.Collections;
import java.util.Date;

/**
 * AuthService — verifies Google / Apple identity tokens and issues a signed
 * HS256 JWT that the iOS client stores in the Keychain.
 *
 * Required environment variables:
 * JWT_SECRET — ≥32 random bytes, e.g. from `openssl rand -base64 32`
 * GOOGLE_CLIENT_ID — your iOS OAuth client ID
 * APPLE_BUNDLE_ID — e.g. com.singularis.eater (default)
 * JWT_EXPIRATION_HOURS — token lifetime in hours (default 48)
 */
public class AuthService {

    private static final Logger logger = LogManager.getLogger(AuthService.class);

    // ── Shared HTTP / JSON utilities ─────────────────────────────────────────
    private static final OkHttpClient HTTP_CLIENT = new OkHttpClient();
    private static final ObjectMapper JSON_MAPPER = new ObjectMapper();

    // ── Config (read once at startup; fail fast if required vars are absent) ─
    private static final String JWT_SECRET = getRequiredEnv("JWT_SECRET");
    private static final String GOOGLE_CLIENT_ID = getRequiredEnv("GOOGLE_CLIENT_ID");
    private static final String APPLE_BUNDLE_ID = System.getenv().getOrDefault("APPLE_BUNDLE_ID",
            "com.singularis.eater");
    private static final long JWT_EXPIRATION_HOURS = Long
            .parseLong(System.getenv().getOrDefault("JWT_EXPIRATION_HOURS", "26280")); // 3 years

    // ── Google verifier (reuse the instance — it caches Google's public keys) ─
    private static final GoogleIdTokenVerifier GOOGLE_VERIFIER = new GoogleIdTokenVerifier.Builder(
            new NetHttpTransport(), GsonFactory.getDefaultInstance())
            .setAudience(Collections.singletonList(GOOGLE_CLIENT_ID))
            .build();

    // ── Apple JWKS – in-memory cache (keys rotate rarely) ───────────────────
    private static JsonNode cachedAppleKeys = null;
    private static long appleKeysFetched = 0;
    private static final long APPLE_CACHE_TTL = 3600; // seconds

    // ═════════════════════════════════════════════════════════════════════════
    // Public entry point (called from Main.java via Kafka consumer loop)
    // ═════════════════════════════════════════════════════════════════════════

    public static JSONObject processAuthRequest(JSONObject authRequest) {
        try {
            String provider = authRequest.getString("provider");
            String idToken = authRequest.getString("idToken");
            String email = authRequest.getString("email");
            String name = authRequest.optString("name", "");
            String profilePictureURL = authRequest.optString("profilePictureURL", "");

            logger.info("Processing auth request – provider={}, email={}", provider, email);

            String verifiedEmail;
            switch (provider.toLowerCase()) {
                case "google":
                    verifiedEmail = verifyGoogleToken(idToken, email);
                    break;
                case "apple":
                    verifiedEmail = verifyAppleToken(idToken, email);
                    break;
                default:
                    logger.error("Unsupported provider: {}", provider);
                    return errorResponse("unsupported_provider",
                            "Provider '" + provider + "' is not supported");
            }

            if (verifiedEmail == null) {
                logger.error("Token verification failed – provider={}, email={}", provider, email);
                return errorResponse("invalid_token",
                        capitalize(provider) + " token verification failed");
            }

            if (name == null || name.trim().isEmpty()) {
                name = extractNameFromEmail(verifiedEmail);
            }

            String jwtToken = issueJwt(verifiedEmail, name, profilePictureURL);
            long expiresIn = JWT_EXPIRATION_HOURS * 3600;

            JSONObject response = new JSONObject();
            response.put("token", jwtToken);
            response.put("expiresIn", expiresIn);
            response.put("userEmail", verifiedEmail);
            response.put("userName", name);
            response.put("profilePictureURL", profilePictureURL);

            logger.info("Auth token issued for email={}", verifiedEmail);
            return response;

        } catch (Exception e) {
            logger.error("Unexpected error in processAuthRequest", e);
            return errorResponse("internal_error",
                    "Authentication service temporarily unavailable");
        }
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Google token verification
    // Uses GoogleIdTokenVerifier which:
    // • Downloads / caches Google's RSA public keys
    // • Verifies the RS256 signature
    // • Checks expiration, audience, issuer
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * @return verified email on success, null on any failure
     */
    private static String verifyGoogleToken(String idTokenStr, String claimedEmail) {
        try {
            GoogleIdToken googleIdToken = GOOGLE_VERIFIER.verify(idTokenStr);
            if (googleIdToken == null) {
                logger.error("Google ID token failed signature / claim verification");
                return null;
            }

            GoogleIdToken.Payload payload = googleIdToken.getPayload();

            // Email must be verified by Google
            if (!Boolean.TRUE.equals(payload.getEmailVerified())) {
                logger.error("Google token: email_verified is false for {}", payload.getEmail());
                return null;
            }

            String tokenEmail = payload.getEmail();
            if (!tokenEmail.equalsIgnoreCase(claimedEmail)) {
                logger.error("Google token: email mismatch – token={}, claimed={}", tokenEmail, claimedEmail);
                return null;
            }

            logger.info("Google token verified for email={}", tokenEmail);
            return tokenEmail;

        } catch (Exception e) {
            logger.error("Google token verification error: {}", e.getMessage());
            return null;
        }
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Apple token verification
    // Manual RS256 path because Apple does not publish a Java SDK:
    // 1. Fetch Apple JWKS (cached 1 h)
    // 2. Match by kid from JWT header
    // 3. Build RSA public key from JWK n/e
    // 4. Verify via jjwt: signature, expiration, issuer, audience
    // 5. Check email matches
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * @return verified email on success, null on any failure
     */
    private static String verifyAppleToken(String idTokenStr, String claimedEmail) {
        try {
            // 1. Decode JWT header (no verification yet)
            String[] parts = idTokenStr.split("\\.");
            if (parts.length != 3) {
                logger.error("Apple token: malformed JWT (expected 3 parts)");
                return null;
            }
            String headerJson = new String(Base64.getUrlDecoder().decode(parts[0]), StandardCharsets.UTF_8);
            String kid = JSON_MAPPER.readTree(headerJson).path("kid").asText();

            // 2. Get cached Apple JWKS
            JsonNode appleKeys = fetchApplePublicKeys();
            if (appleKeys == null)
                return null;

            // 3. Find JWK with matching kid
            JsonNode matchingKey = null;
            for (JsonNode key : appleKeys) {
                if (kid.equals(key.path("kid").asText())) {
                    matchingKey = key;
                    break;
                }
            }
            if (matchingKey == null) {
                logger.error("Apple token: no JWK found for kid={}", kid);
                return null;
            }

            // 4. Build RSA public key from n + e (Base64URL encoded big integers)
            PublicKey publicKey = buildRsaKey(matchingKey);

            // 5. Verify token with jjwt: signature, exp, iss, aud
            JwtParser parser = Jwts.parser()
                    .verifyWith(publicKey)
                    .requireIssuer("https://appleid.apple.com")
                    .requireAudience(APPLE_BUNDLE_ID)
                    .build();

            Claims claims = parser.parseSignedClaims(idTokenStr).getPayload();

            // 6. Email match
            String tokenEmail = claims.get("email", String.class);
            if (tokenEmail == null || !tokenEmail.equalsIgnoreCase(claimedEmail)) {
                logger.error("Apple token: email mismatch – token={}, claimed={}", tokenEmail, claimedEmail);
                return null;
            }

            logger.info("Apple token verified for email={}", tokenEmail);
            return tokenEmail;

        } catch (Exception e) {
            logger.error("Apple token verification error: {}", e.getMessage());
            return null;
        }
    }

    /** Fetch Apple's JWKS, caching for APPLE_CACHE_TTL seconds. */
    private static synchronized JsonNode fetchApplePublicKeys() {
        long now = Instant.now().getEpochSecond();
        if (cachedAppleKeys != null && (now - appleKeysFetched) < APPLE_CACHE_TTL) {
            return cachedAppleKeys;
        }
        try {
            Request req = new Request.Builder()
                    .url("https://appleid.apple.com/auth/keys")
                    .build();
            try (Response resp = HTTP_CLIENT.newCall(req).execute()) {
                if (!resp.isSuccessful() || resp.body() == null) {
                    logger.error("Failed to fetch Apple JWKS: HTTP {}", resp.code());
                    return null;
                }
                cachedAppleKeys = JSON_MAPPER.readTree(resp.body().string()).path("keys");
                appleKeysFetched = now;
                logger.info("Apple JWKS refreshed");
                return cachedAppleKeys;
            }
        } catch (Exception e) {
            logger.error("Error fetching Apple JWKS: {}", e.getMessage());
            return null;
        }
    }

    /**
     * Reconstruct an RSA PublicKey from a JWK node containing Base64URL "n" and
     * "e".
     */
    private static PublicKey buildRsaKey(JsonNode jwk) throws Exception {
        byte[] nBytes = Base64.getUrlDecoder().decode(jwk.path("n").asText());
        byte[] eBytes = Base64.getUrlDecoder().decode(jwk.path("e").asText());
        BigInteger modulus = new BigInteger(1, nBytes);
        BigInteger exponent = new BigInteger(1, eBytes);
        return KeyFactory.getInstance("RSA").generatePublic(new RSAPublicKeySpec(modulus, exponent));
    }

    // ═════════════════════════════════════════════════════════════════════════
    // JWT issuance
    // Issues a signed HS256 JWT. The client stores this token but can NEVER
    // generate one because JWT_SECRET lives only on the server.
    // ═════════════════════════════════════════════════════════════════════════

    private static String issueJwt(String email, String name, String pictureUrl) {
        byte[] secretBytes = JWT_SECRET.getBytes(StandardCharsets.UTF_8);
        if (secretBytes.length < 32) {
            throw new IllegalStateException(
                    "JWT_SECRET must be ≥32 bytes for HS256. "
                            + "Generate with: openssl rand -base64 32");
        }

        SecretKey key = Keys.hmacShaKeyFor(secretBytes);
        Instant now = Instant.now();
        Instant expiresAt = now.plus(JWT_EXPIRATION_HOURS, ChronoUnit.HOURS);

        return Jwts.builder()
                .subject(email)
                .claim("name", name)
                .claim("picture", pictureUrl)
                .issuedAt(Date.from(now))
                .expiration(Date.from(expiresAt))
                .signWith(key)
                .compact();
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Helpers
    // ═════════════════════════════════════════════════════════════════════════

    private static String extractNameFromEmail(String email) {
        if (email == null || !email.contains("@"))
            return "User";
        String local = email.split("@")[0].replaceAll("[._]", " ");
        StringBuilder sb = new StringBuilder();
        for (String word : local.split(" ")) {
            if (!word.isEmpty()) {
                sb.append(Character.toUpperCase(word.charAt(0)))
                        .append(word.substring(1).toLowerCase())
                        .append(" ");
            }
        }
        return sb.toString().trim();
    }

    private static JSONObject errorResponse(String code, String message) {
        JSONObject obj = new JSONObject();
        obj.put("error", code);
        obj.put("message", message);
        return obj;
    }

    private static String capitalize(String s) {
        if (s == null || s.isEmpty())
            return s;
        return Character.toUpperCase(s.charAt(0)) + s.substring(1).toLowerCase();
    }

    /**
     * Reads a required env var; fails fast with a descriptive message if absent.
     */
    private static String getRequiredEnv(String name) {
        String val = System.getenv(name);
        if (val == null || val.trim().isEmpty()) {
            throw new IllegalStateException(
                    "Required environment variable '" + name + "' is not set. "
                            + "See deployment configuration.");
        }
        return val;
    }
}