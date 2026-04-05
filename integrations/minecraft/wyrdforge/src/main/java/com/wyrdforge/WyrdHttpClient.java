package com.wyrdforge;

import com.wyrdforge.WyrdModConfig.Config;
import com.wyrdforge.WyrdModConfig.Fact;
import com.wyrdforge.WyrdModConfig.QueryResult;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.logging.Logger;

/**
 * WyrdHttpClient — thin Java HttpClient wrapper around WyrdHTTPServer.
 *
 * Thread-safe: the underlying java.net.http.HttpClient is thread-safe.
 * All blocking calls are synchronous; callers that need async can wrap in a
 * CompletableFuture or virtual thread.
 *
 * Wire-up in WyrdForgeMod (Fabric pattern — example):
 * <pre>
 *   // In your server tick / command callback:
 *   String reply = client.queryContext(personaId, playerMessage);
 *   player.sendMessage(Text.literal(reply));
 *
 *   // On player join:
 *   client.syncEntity(personaId, EntityMapper.toFacts(
 *       player.getName().getString(),
 *       player.getUuidAsString(),
 *       player.getWorld().getRegistryKey().getValue().toString(),
 *       null));
 * </pre>
 */
public final class WyrdHttpClient implements AutoCloseable {

    private static final Logger LOG = Logger.getLogger("WyrdForge");

    private final Config     config;
    private final HttpClient http;
    private volatile String  lastError;

    public WyrdHttpClient() {
        this(new Config());
    }

    public WyrdHttpClient(Config config) {
        this.config = config;
        this.http   = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(config.timeoutSeconds))
            .build();
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Query world context for the given persona. Blocking.
     *
     * @param personaId Normalised WYRD persona_id.
     * @param query     Player input; blank → "What is the current world state?"
     * @return QueryResult — success=false on network/HTTP error.
     */
    public QueryResult queryContext(String personaId, String query) {
        String body = EntityMapper.buildQueryBody(personaId, query);
        try {
            HttpResponse<String> resp = post("/query", body);
            if (resp.statusCode() >= 200 && resp.statusCode() < 300) {
                String text = EntityMapper.parseResponse(resp.body());
                return QueryResult.ok(personaId, text);
            }
            String err = "HTTP " + resp.statusCode();
            lastError = err;
            return QueryResult.failure(personaId, err);
        } catch (Exception e) {
            lastError = e.getMessage();
            return QueryResult.failure(personaId, e.getMessage());
        }
    }

    /**
     * Sync an entity to WYRD by pushing each fact. Fire-and-forget (errors logged).
     *
     * @param personaId WYRD persona_id used as subject_id for each fact.
     * @param facts     Fact list from EntityMapper.toFacts().
     */
    public void syncEntity(String personaId, List<Fact> facts) {
        for (Fact f : facts) {
            pushFact(personaId, f.key, f.value);
        }
    }

    /**
     * Push an observation to WYRD memory. Fire-and-forget.
     */
    public void pushObservation(String title, String summary) {
        String body = EntityMapper.buildObservationBody(title, summary);
        fireAndForget("/event", body);
    }

    /**
     * Push a single fact to WYRD. Fire-and-forget.
     */
    public void pushFact(String subjectId, String key, String value) {
        String body = EntityMapper.buildFactBody(subjectId, key, value);
        fireAndForget("/event", body);
    }

    /**
     * Check WyrdHTTPServer health. Blocking.
     *
     * @return true if /health returns 2xx.
     */
    public boolean healthCheck() {
        try {
            HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(config.baseUrl() + "/health"))
                .timeout(Duration.ofSeconds(config.timeoutSeconds))
                .GET()
                .build();
            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            return resp.statusCode() >= 200 && resp.statusCode() < 300;
        } catch (Exception e) {
            lastError = e.getMessage();
            return false;
        }
    }

    /** Last error message from a fire-and-forget or failed call; null if none. */
    public String getLastError() {
        return lastError;
    }

    @Override
    public void close() {
        // java.net.http.HttpClient does not implement Closeable in Java 17,
        // but the instance is GC-collected cleanly. This method is here for
        // future compatibility and try-with-resources patterns.
    }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    private HttpResponse<String> post(String path, String jsonBody)
            throws Exception {
        HttpRequest req = HttpRequest.newBuilder()
            .uri(URI.create(config.baseUrl() + path))
            .timeout(Duration.ofSeconds(config.timeoutSeconds))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
            .build();
        return http.send(req, HttpResponse.BodyHandlers.ofString());
    }

    private void fireAndForget(String path, String jsonBody) {
        http.sendAsync(
            HttpRequest.newBuilder()
                .uri(URI.create(config.baseUrl() + path))
                .timeout(Duration.ofSeconds(config.timeoutSeconds))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                .build(),
            HttpResponse.BodyHandlers.discarding()
        ).whenComplete((resp, ex) -> {
            if (ex != null) {
                lastError = ex.getMessage();
                LOG.warning("[WyrdForge] fire-and-forget error: " + ex.getMessage());
            } else if (resp.statusCode() < 200 || resp.statusCode() >= 300) {
                lastError = "HTTP " + resp.statusCode();
                LOG.warning("[WyrdForge] fire-and-forget HTTP error: " + resp.statusCode());
            }
        });
    }
}
