package com.wyrdforge;

import java.util.List;

/**
 * WyrdModConfig — configuration and result data types for the WyrdForge Fabric mod.
 *
 * All types are intentionally dependency-free POJOs so they can be tested
 * without a Minecraft runtime.
 */
public final class WyrdModConfig {

    private WyrdModConfig() {}

    // -------------------------------------------------------------------------
    // Configuration
    // -------------------------------------------------------------------------

    /** Runtime configuration for the WyrdHTTPServer connection. */
    public static final class Config {
        public final String host;
        public final int    port;
        public final int    timeoutSeconds;
        public final boolean autoRespondToChat;
        public final boolean enableCommands;

        public Config() {
            this("localhost", 8765, 10, true, true);
        }

        public Config(String host, int port, int timeoutSeconds,
                      boolean autoRespondToChat, boolean enableCommands) {
            this.host              = host;
            this.port              = port;
            this.timeoutSeconds    = timeoutSeconds;
            this.autoRespondToChat = autoRespondToChat;
            this.enableCommands    = enableCommands;
        }

        public String baseUrl() {
            return "http://" + host + ":" + port;
        }

        @Override
        public String toString() {
            return "[WyrdForge] host=" + host + " port=" + port
                + " timeout=" + timeoutSeconds + "s"
                + " autoChat=" + autoRespondToChat
                + " commands=" + enableCommands;
        }
    }

    // -------------------------------------------------------------------------
    // Fact (key/value pair)
    // -------------------------------------------------------------------------

    /** A single ECS fact: subject → key → value. */
    public static final class Fact {
        public final String key;
        public final String value;

        public Fact(String key, String value) {
            this.key   = key;
            this.value = value;
        }

        @Override
        public String toString() {
            return key + "=" + value;
        }
    }

    // -------------------------------------------------------------------------
    // QueryResult
    // -------------------------------------------------------------------------

    /** Result of a /query call to WyrdHTTPServer. */
    public static final class QueryResult {
        public final boolean success;
        public final String  personaId;
        public final String  response;
        public final String  errorMessage;  // null on success

        public QueryResult(boolean success, String personaId,
                           String response, String errorMessage) {
            this.success      = success;
            this.personaId    = personaId;
            this.response     = response;
            this.errorMessage = errorMessage;
        }

        public static QueryResult ok(String personaId, String response) {
            return new QueryResult(true, personaId, response, null);
        }

        public static QueryResult failure(String personaId, String error) {
            return new QueryResult(false, personaId, "", error);
        }
    }

    // -------------------------------------------------------------------------
    // ChatCommandResult
    // -------------------------------------------------------------------------

    /** Parsed result of a chat command. */
    public enum CommandType { NONE, QUERY, SYNC, HEALTH }

    public static final class ChatCommandResult {
        public final CommandType type;
        public final String      personaId;   // may be empty
        public final String      query;       // may be empty

        public ChatCommandResult(CommandType type, String personaId, String query) {
            this.type      = type;
            this.personaId = personaId != null ? personaId : "";
            this.query     = query     != null ? query     : "";
        }

        public static ChatCommandResult none() {
            return new ChatCommandResult(CommandType.NONE, "", "");
        }
    }
}
