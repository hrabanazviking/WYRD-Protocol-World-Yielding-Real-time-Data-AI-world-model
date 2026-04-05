/**
 * WyrdForge content script — injected into D&D Beyond pages.
 * Reads the character/monster name from the page, injects a sidebar panel,
 * and communicates with background.js via chrome.runtime.sendMessage.
 */
/* global chrome */

import {
  normalizePersonaId,
  renderSidebarPanel,
  buildQueryMessage,
  classifyDDBUrl,
} from "./wyrdforge.js";

const PANEL_ID = "wyrdforge-ddb-panel";

function getCharacterName() {
  // Try multiple DDB selectors in priority order
  const selectors = [
    ".ddbc-character-name",           // character builder
    ".character-header-desktop__name",
    "h1.page-header__name",
    ".mon-stat-block__name",          // monster stat block
    "h1.brew-title",
    "h1",
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el?.textContent?.trim()) return el.textContent.trim();
  }
  return "";
}

function findSidebarContainer() {
  const candidates = [
    ".ct-sidebar__portal",
    ".aside-panel",
    ".character-sheet-right-column",
    ".quick-nav",
    ".ddb-navigation",
    "aside",
    ".container",
  ];
  for (const sel of candidates) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return document.body;
}

function createPanel() {
  const name = getCharacterName();
  const personaId = normalizePersonaId(name);
  const panel = document.createElement("div");
  panel.id = PANEL_ID;
  panel.innerHTML = renderSidebarPanel({ personaId, loading: false, output: "", error: null });
  return { panel, personaId };
}

async function refreshContext(panel, personaId) {
  panel.innerHTML = renderSidebarPanel({ personaId, loading: true, output: "", error: null });
  try {
    const response = await chrome.runtime.sendMessage(buildQueryMessage(personaId));
    if (response?.error) {
      panel.innerHTML = renderSidebarPanel({ personaId, loading: false, output: "", error: response.error });
    } else {
      const text = response?.response ?? "";
      panel.innerHTML = renderSidebarPanel({ personaId, loading: false, output: text, error: null });
    }
  } catch (err) {
    panel.innerHTML = renderSidebarPanel({ personaId, loading: false, output: "", error: err.message });
  }
  panel.querySelector(".wyrd-refresh")?.addEventListener("click", () => refreshContext(panel, personaId));
}

function injectPanel() {
  if (document.getElementById(PANEL_ID)) return;
  const type = classifyDDBUrl(window.location.href);
  if (type === "unknown") return;

  const { panel, personaId } = createPanel();
  const container = findSidebarContainer();
  container.prepend(panel);

  panel.querySelector(".wyrd-refresh")?.addEventListener("click", () => refreshContext(panel, personaId));
}

// Inject on load, and again after DDB's React router updates the URL
injectPanel();
const observer = new MutationObserver(() => injectPanel());
observer.observe(document.body, { childList: true, subtree: false });
