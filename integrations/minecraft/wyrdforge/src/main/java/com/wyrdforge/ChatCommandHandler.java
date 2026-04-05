package com.wyrdforge;

import com.wyrdforge.WyrdModConfig.ChatCommandResult;
import com.wyrdforge.WyrdModConfig.CommandType;

/**
 * ChatCommandHandler — pure static chat-command parser for WyrdForge.
 *
 * Recognised commands (case-insensitive prefix):
 *   /wyrd-health              → HEALTH
 *   /wyrd-sync <name>         → SYNC + personaId
 *   /wyrd <persona_id> [text] → QUERY + personaId [+ query]
 *
 * No Minecraft runtime dependency — can be unit-tested in isolation.
 */
public final class ChatCommandHandler {

    private ChatCommandHandler() {}

    private static final String CMD_HEALTH = "/wyrd-health";
    private static final String CMD_SYNC   = "/wyrd-sync";
    private static final String CMD_QUERY  = "/wyrd";

    /**
     * Parse a raw chat message.
     *
     * @param message Raw chat string; may be null or blank.
     * @return ChatCommandResult — type NONE if not a wyrd command.
     */
    public static ChatCommandResult parse(String message) {
        if (message == null) return ChatCommandResult.none();

        String trimmed = message.strip();
        if (trimmed.isEmpty()) return ChatCommandResult.none();

        String lower = trimmed.toLowerCase();

        // /wyrd-health  (check before /wyrd to avoid prefix collision)
        if (lower.equals(CMD_HEALTH)) {
            return new ChatCommandResult(CommandType.HEALTH, "", "");
        }

        // /wyrd-sync [name]
        if (lower.startsWith(CMD_SYNC)) {
            String rest = trimmed.substring(CMD_SYNC.length()).strip();
            return new ChatCommandResult(CommandType.SYNC, rest, "");
        }

        // /wyrd <persona_id> [query]
        if (lower.startsWith(CMD_QUERY + " ") || lower.equals(CMD_QUERY)) {
            String rest = trimmed.substring(CMD_QUERY.length()).strip();
            if (rest.isEmpty()) {
                // No persona_id — usage error, caller decides what to do
                return new ChatCommandResult(CommandType.QUERY, "", "");
            }
            int spaceIdx = rest.indexOf(' ');
            if (spaceIdx < 0) {
                // persona_id only, no query
                return new ChatCommandResult(CommandType.QUERY, rest, "");
            }
            String personaId = rest.substring(0, spaceIdx);
            String query     = rest.substring(spaceIdx + 1).strip();
            return new ChatCommandResult(CommandType.QUERY, personaId, query);
        }

        return ChatCommandResult.none();
    }

    // -------------------------------------------------------------------------
    // Usage strings (returned by WyrdForgeMod on bad commands)
    // -------------------------------------------------------------------------

    public static final String USAGE_QUERY  = "[WyrdForge] Usage: /wyrd <persona_id> [query text]";
    public static final String USAGE_SYNC   = "[WyrdForge] Usage: /wyrd-sync <player_name>";
    public static final String USAGE_HEALTH = "[WyrdForge] Usage: /wyrd-health";
}
