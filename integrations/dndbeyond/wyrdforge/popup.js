/* global chrome */

document.addEventListener("DOMContentLoaded", () => {
  chrome.storage.sync.get(["wyrdforge_config"], (data) => {
    const cfg = data?.wyrdforge_config;
    if (cfg) {
      document.getElementById("host").value = cfg.host || "localhost";
      document.getElementById("port").value = cfg.port || 8765;
      document.getElementById("enabled").checked = cfg.enabled !== false;
    }
  });

  document.getElementById("save").addEventListener("click", () => {
    const host = document.getElementById("host").value.trim() || "localhost";
    const port = parseInt(document.getElementById("port").value, 10) || 8765;
    const enabled = document.getElementById("enabled").checked;
    chrome.storage.sync.set({ wyrdforge_config: { host, port, enabled } }, () => {
      const status = document.getElementById("status");
      status.textContent = "Saved.";
      setTimeout(() => { status.textContent = ""; }, 1500);
    });
  });
});
