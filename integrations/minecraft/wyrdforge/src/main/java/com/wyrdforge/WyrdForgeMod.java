package com.wyrdforge;

import com.wyrdforge.WyrdModConfig.ChatCommandResult;
import com.wyrdforge.WyrdModConfig.CommandType;
import com.wyrdforge.WyrdModConfig.Config;
import com.wyrdforge.WyrdModConfig.QueryResult;

import java.util.List;
import java.util.logging.Logger;

/**
 * WyrdForgeMod — Fabric mod entry point for the WyrdForge Minecraft integration.
 *
 * This class implements net.fabricmc.api.ModInitializer but we keep it free of
 * Fabric imports so the module can be tested without a game runtime.
 * The actual @Mod wiring is done via fabric.mod.json entrypoints.
 *
 * ─── INTEGRATION GUIDE (Fabric 1.21) ─────────────────────────────────────────
 *
 * 1. Add Fabric API dependency in build.gradle.
 *
 * 2. Register chat listener in onInitialize():
 *
 *    ServerMessageEvents.CHAT_MESSAGE.register((message, sender, params) -> {
 *        String text = message.getContent().getString();
 *        ChatCommandResult cmd = ChatCommandHandler.parse(text);
 *        if (cmd.type == CommandType.NONE) return;
 *        handleCommand(cmd, sender);
 *    });
 *
 * 3. Register slash commands (CommandRegistrationCallback) for /wyrd, /wyrd-sync,
 *    /wyrd-health using Brigadier — delegate to handleCommand().
 *
 * 4. Push player-join observations:
 *
 *    ServerPlayConnectionEvents.JOIN.register((handler, sender, server) -> {
 *        var player  = handler.player;
 *        String name = player.getName().getString();
 *        String uuid = player.getUuidAsString();
 *        String dim  = player.getWorld().getRegistryKey().getValue().toString();
 *        var facts   = EntityMapper.toFacts(name, uuid, dim, null);
 *        client.pushObservation("Player joined", name + " joined the server.");
 *        client.syncEntity(EntityMapper.toPersonaId(name), facts);
 *    });
 *
 * 5. Push entity death observations (ServerLivingEntityEvents.AFTER_DEATH):
 *    client.pushObservation("Entity died", entityName + " was slain.");
 *
 * ─────────────────────────────────────────────────────────────────────────────
 */
public class WyrdForgeMod {

    private static final Logger LOG = Logger.getLogger("WyrdForge");

    /** Singleton client — initialised in onInitialize(). */
    private static WyrdHttpClient client;

    /** Singleton config — may be loaded from a file in a real implementation. */
    private static Config config = new Config();

    // -------------------------------------------------------------------------
    // Mod lifecycle
    // -------------------------------------------------------------------------

    /**
     * Called by Fabric on server initialisation.
     * Implements net.fabricmc.api.ModInitializer#onInitialize() conceptually.
     */
    public void onInitialize() {
        LOG.info("[WyrdForge] Initialising WyrdForge Fabric mod v1.0.0");
        LOG.info("[WyrdForge] " + config);

        client = new WyrdHttpClient(config);

        // Verify server is reachable
        if (client.healthCheck()) {
            LOG.info("[WyrdForge] WyrdHTTPServer reachable at " + config.baseUrl());
        } else {
            LOG.warning("[WyrdForge] WyrdHTTPServer NOT reachable at " + config.baseUrl()
                + " — commands will fail until the server starts.");
        }

        // NOTE: Wire Fabric events here — see class-level Javadoc.
    }

    // -------------------------------------------------------------------------
    // Command dispatcher (called from chat / Brigadier callbacks)
    // -------------------------------------------------------------------------

    /**
     * Dispatch a parsed chat command.
     *
     * @param cmd    Parsed command.
     * @param sender Player name string (used for persona_id fallback on SYNC).
     * @return Reply string to send back to the player; null if no reply needed.
     */
    public static String handleCommand(ChatCommandResult cmd, String sender) {
        return switch (cmd.type) {
            case HEALTH -> {
                boolean ok = client != null && client.healthCheck();
                yield ok
                    ? "[WyrdForge] WyrdHTTPServer is healthy."
                    : "[WyrdForge] WyrdHTTPServer is UNREACHABLE.";
            }

            case SYNC -> {
                if (cmd.personaId.isEmpty()) {
                    yield ChatCommandHandler.USAGE_SYNC;
                }
                if (client == null) yield "[WyrdForge] Not initialised.";
                String personaId = EntityMapper.toPersonaId(cmd.personaId);
                List<WyrdModConfig.Fact> facts = EntityMapper.toFacts(
                    cmd.personaId, "", null, null);
                client.syncEntity(personaId, facts);
                yield "[WyrdForge] Synced " + personaId + " to WYRD.";
            }

            case QUERY -> {
                if (cmd.personaId.isEmpty()) {
                    yield ChatCommandHandler.USAGE_QUERY;
                }
                if (client == null) yield "[WyrdForge] Not initialised.";
                QueryResult result = client.queryContext(cmd.personaId, cmd.query);
                yield result.success
                    ? result.response
                    : "[WyrdForge] Error: " + result.errorMessage;
            }

            default -> null;
        };
    }

    // -------------------------------------------------------------------------
    // Config / client accessors (for testing and hot-reload)
    // -------------------------------------------------------------------------

    public static WyrdHttpClient getClient()  { return client;  }
    public static Config         getConfig()  { return config;  }

    public static void setConfig(Config cfg) {
        config = cfg;
        client = new WyrdHttpClient(cfg);
    }
}
