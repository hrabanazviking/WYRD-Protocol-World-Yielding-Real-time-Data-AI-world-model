/**
 * WyrdForge — WYRD Protocol Construct 3 addon (Phase 11D).
 * Runtime plugin class.
 *
 * Runs in the C3 game runtime. Defines the plugin's runtime identity
 * and ties action/condition/expression method names to the instance.
 */
"use strict";

{
  const C3 = globalThis.C3;

  C3.Plugins["WyrdForge"] = class WyrdForgePlugin extends C3.SDKPluginBase {
    constructor(opts) {
      super(opts);
    }

    Release() {
      super.Release();
    }
  };

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  C3.Plugins["WyrdForge"].Acts = {
    /**
     * Configure WyrdHTTPServer connection.
     * @param {string} host
     * @param {number} port
     * @param {number} timeoutMs
     */
    Init(host, port, timeoutMs) {
      this._Init(host, port, timeoutMs);
    },

    /**
     * Query WYRD world context for a character.
     * @param {string} personaId
     * @param {string} query
     */
    async QueryCharacter(personaId, query) {
      await this._QueryCharacter(personaId, query);
    },

    /**
     * Push a world observation to WYRD memory.
     * @param {string} title
     * @param {string} summary
     */
    async PushObservation(title, summary) {
      await this._PushEvent("observation", { title, summary });
    },

    /**
     * Push a world fact to WYRD.
     * @param {string} subjectId
     * @param {string} key
     * @param {string} value
     */
    async PushFact(subjectId, key, value) {
      await this._PushEvent("fact", { subject_id: subjectId, key, value });
    },
  };

  // -------------------------------------------------------------------------
  // Conditions
  // -------------------------------------------------------------------------

  C3.Plugins["WyrdForge"].Cnds = {
    OnQueryComplete() {
      return true; // fires as trigger
    },
    OnQueryError() {
      return true; // fires as trigger
    },
    IsReady() {
      return this._IsReady();
    },
  };

  // -------------------------------------------------------------------------
  // Expressions
  // -------------------------------------------------------------------------

  C3.Plugins["WyrdForge"].Exps = {
    LastResponse() {
      return this._lastResponse;
    },
    LastError() {
      return this._lastError;
    },
  };
}
