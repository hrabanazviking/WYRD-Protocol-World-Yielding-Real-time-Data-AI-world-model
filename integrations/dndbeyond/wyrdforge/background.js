/**
 * WyrdForge background service worker — handles WYRD HTTP requests.
 * Content scripts can't call localhost directly (CORS), so they relay via
 * chrome.runtime.sendMessage → background → WyrdHTTPServer.
 */
/* global chrome */

import { WyrdClient, isValidMessage, getConfigFromStorage, STORAGE_KEY } from "./wyrdforge.js";

async function getClient() {
  const data = await chrome.storage.sync.get(["wyrdforge_config"]);
  const cfg = getConfigFromStorage(data);
  return new WyrdClient({ host: cfg.host, port: cfg.port });
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!isValidMessage(msg)) return false;

  (async () => {
    const client = await getClient();
    try {
      if (msg.type === "WYRD_HEALTH") {
        const r = await client.health();
        sendResponse(r);
      } else if (msg.type === "WYRD_QUERY") {
        const r = await client.query(msg.personaId, msg.query || "", { useTurnLoop: false });
        sendResponse(r);
      } else if (msg.type === "WYRD_SYNC") {
        const r = await client.pushEvent("fact", {
          subject_id: msg.personaId,
          key: "name",
          value: msg.name,
        });
        sendResponse(r);
      }
    } catch (err) {
      sendResponse({ error: err.message });
    }
  })();

  return true; // async response
});
