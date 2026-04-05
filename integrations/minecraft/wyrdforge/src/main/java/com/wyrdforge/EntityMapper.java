package com.wyrdforge;

import com.wyrdforge.WyrdModConfig.Fact;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * EntityMapper — pure static helpers that convert Minecraft entity / player data
 * into WYRD Protocol types (persona IDs, fact lists).
 *
 * No Minecraft runtime dependency — all methods operate on plain Java strings
 * so they can be tested without a game instance.
 */
public final class EntityMapper {

    private EntityMapper() {}

    // -------------------------------------------------------------------------
    // Persona ID normalisation
    // -------------------------------------------------------------------------

    /**
     * Normalize a player / entity name to a WYRD persona_id.
     * Rules:
     *   - Lowercase
     *   - Replace any character that is not [a-z0-9_] with underscore
     *   - Collapse consecutive underscores to one
     *   - Strip leading and trailing underscores
     *   - Truncate to 64 characters
     */
    public static String toPersonaId(String name) {
        if (name == null || name.isEmpty()) return "";

        StringBuilder sb = new StringBuilder(name.toLowerCase());

        // Replace non-alphanumeric (except underscore) with underscore
        for (int i = 0; i < sb.length(); i++) {
            char c = sb.charAt(i);
            if (!Character.isLetterOrDigit(c) && c != '_') {
                sb.setCharAt(i, '_');
            }
        }

        // Collapse consecutive underscores
        String result = sb.toString().replaceAll("_+", "_");

        // Strip leading/trailing underscores
        result = result.replaceAll("^_+", "").replaceAll("_+$", "");

        // Truncate
        if (result.length() > 64) result = result.substring(0, 64);

        return result;
    }

    // -------------------------------------------------------------------------
    // Fact list generation
    // -------------------------------------------------------------------------

    /**
     * Build a list of WYRD facts from entity data.
     *
     * @param entityName   Display name of the player/entity
     * @param entityId     UUID string or numeric entity ID
     * @param worldName    Dimension/world name (e.g. "minecraft:overworld"); may be null
     * @param customFacts  Extra key→value pairs to append; null values are skipped
     */
    public static List<Fact> toFacts(String entityName, String entityId,
                                     String worldName,
                                     Map<String, String> customFacts) {
        List<Fact> facts = new ArrayList<>();

        if (entityName != null && !entityName.isEmpty())
            facts.add(new Fact("name", entityName));

        if (entityId != null && !entityId.isEmpty())
            facts.add(new Fact("entity_id", entityId));

        if (worldName != null && !worldName.isEmpty())
            facts.add(new Fact("world", worldName));

        if (customFacts != null) {
            for (Map.Entry<String, String> e : customFacts.entrySet()) {
                if (e.getKey() != null && !e.getKey().isEmpty()
                        && e.getValue() != null && !e.getValue().isEmpty()) {
                    facts.add(new Fact(e.getKey(), e.getValue()));
                }
            }
        }

        return facts;
    }

    // -------------------------------------------------------------------------
    // JSON body builders (no external library needed)
    // -------------------------------------------------------------------------

    /**
     * Build the JSON body for POST /query.
     *
     * @param personaId  WYRD persona_id
     * @param userInput  Player chat input; if blank defaults to "What is the current world state?"
     */
    public static String buildQueryBody(String personaId, String userInput) {
        if (userInput == null || userInput.isBlank())
            userInput = "What is the current world state?";
        return "{\"persona_id\":\"" + escapeJson(personaId)
             + "\",\"user_input\":\"" + escapeJson(userInput)
             + "\",\"use_turn_loop\":false}";
    }

    /**
     * Build the JSON body for POST /event (type = "observation").
     */
    public static String buildObservationBody(String title, String summary) {
        return "{\"event_type\":\"observation\","
             + "\"payload\":{\"title\":\"" + escapeJson(title)
             + "\",\"summary\":\"" + escapeJson(summary) + "\"}}";
    }

    /**
     * Build the JSON body for POST /event (type = "fact").
     */
    public static String buildFactBody(String subjectId, String key, String value) {
        return "{\"event_type\":\"fact\","
             + "\"payload\":{\"subject_id\":\"" + escapeJson(subjectId)
             + "\",\"key\":\"" + escapeJson(key)
             + "\",\"value\":\"" + escapeJson(value) + "\"}}";
    }

    /**
     * Extract the "response" field from a WyrdHTTPServer /query JSON reply.
     * Returns fallback text if the field is missing or blank.
     */
    public static String parseResponse(String json) {
        if (json == null || json.isBlank())
            return "The spirits whisper nothing of note.";

        int idx = json.indexOf("\"response\"");
        if (idx < 0) return "The spirits whisper nothing of note.";

        int colon = json.indexOf(':', idx);
        if (colon < 0) return "The spirits whisper nothing of note.";

        // Find the opening quote
        int start = json.indexOf('"', colon + 1);
        if (start < 0) return "The spirits whisper nothing of note.";
        start++; // skip opening quote

        // Find the closing quote (respecting escaped quotes)
        int end = start;
        while (end < json.length()) {
            if (json.charAt(end) == '"' && json.charAt(end - 1) != '\\') break;
            end++;
        }

        String value = json.substring(start, end).trim();
        return value.isEmpty() ? "The spirits whisper nothing of note." : value;
    }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    /** Escape a string for embedding inside a JSON string value. */
    static String escapeJson(String s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder(s.length() + 8);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"'  -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\b' -> sb.append("\\b");
                case '\f' -> sb.append("\\f");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
                }
            }
        }
        return sb.toString();
    }
}
