/**
 * WyrdForge — WYRD Protocol Construct 3 addon (Phase 11D).
 * Editor-side plugin script.
 *
 * This file runs in the Construct 3 editor environment. It registers
 * the plugin, its properties, and its action/condition/expression
 * metadata. All runtime logic is in c3runtime/.
 */
"use strict";

{
  const SDK = globalThis.SDK;

  // ---------------------------------------------------------------------------
  // Plugin class
  // ---------------------------------------------------------------------------

  const PLUGIN_CLASS = SDK.Plugins["WyrdForge"] = class WyrdForgePlugin extends SDK.IPluginBase {
    constructor() {
      super("WyrdForge");

      SDK.Lang.PushContext("plugins.wyrdforge");

      this._info.SetName(lang(".name"));
      this._info.SetDescription(lang(".description"));
      this._info.SetVersion("1.0.0");
      this._info.SetCategory("data-and-storage");
      this._info.SetAuthor("RuneForgeAI");
      this._info.SetHelpUrl(lang(".help-url"));
      this._info.SetIsSingleGlobal(true);

      SDK.Lang.PopContext();
    }
  };

  PLUGIN_CLASS.Register("WyrdForge", PLUGIN_CLASS);

  // ---------------------------------------------------------------------------
  // Properties (editor parameters shown in the Properties bar)
  // ---------------------------------------------------------------------------

  SDK.Lang.PushContext("plugins.wyrdforge.properties");

  PLUGIN_CLASS._info.SetProperties([
    new SDK.PluginProperty("text", "host", "localhost"),
    new SDK.PluginProperty("integer", "port", 8765),
    new SDK.PluginProperty("integer", "timeout-ms", 8000),
    new SDK.PluginProperty("check", "enabled", true),
  ]);

  SDK.Lang.PopContext();

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  SDK.Lang.PushContext("plugins.wyrdforge.actions");

  {
    const A = SDK.Actions["WyrdForge_Init"] = class extends SDK.IActionBase {
      constructor() {
        super(PLUGIN_CLASS);
        SDK.Lang.PushContext("init");
        this._info.SetName(lang(".list-name"));
        this._info.SetDescription(lang(".description"));
        this._info.SetDisplayText(lang(".display-text"));
        this._info.AddParam(new SDK.Params.String("host", "localhost"));
        this._info.AddParam(new SDK.Params.Integer("port", 8765));
        this._info.AddParam(new SDK.Params.Integer("timeout-ms", 8000));
        SDK.Lang.PopContext();
      }
    };
  }

  {
    const A = SDK.Actions["WyrdForge_QueryCharacter"] = class extends SDK.IActionBase {
      constructor() {
        super(PLUGIN_CLASS);
        SDK.Lang.PushContext("query-character");
        this._info.SetName(lang(".list-name"));
        this._info.SetDescription(lang(".description"));
        this._info.SetDisplayText(lang(".display-text"));
        this._info.AddParam(new SDK.Params.String("persona-id", ""));
        this._info.AddParam(new SDK.Params.String("query", ""));
        SDK.Lang.PopContext();
      }
    };
  }

  {
    const A = SDK.Actions["WyrdForge_PushObservation"] = class extends SDK.IActionBase {
      constructor() {
        super(PLUGIN_CLASS);
        SDK.Lang.PushContext("push-observation");
        this._info.SetName(lang(".list-name"));
        this._info.SetDescription(lang(".description"));
        this._info.SetDisplayText(lang(".display-text"));
        this._info.AddParam(new SDK.Params.String("title", ""));
        this._info.AddParam(new SDK.Params.String("summary", ""));
        SDK.Lang.PopContext();
      }
    };
  }

  {
    const A = SDK.Actions["WyrdForge_PushFact"] = class extends SDK.IActionBase {
      constructor() {
        super(PLUGIN_CLASS);
        SDK.Lang.PushContext("push-fact");
        this._info.SetName(lang(".list-name"));
        this._info.SetDescription(lang(".description"));
        this._info.SetDisplayText(lang(".display-text"));
        this._info.AddParam(new SDK.Params.String("subject-id", ""));
        this._info.AddParam(new SDK.Params.String("key", ""));
        this._info.AddParam(new SDK.Params.String("value", ""));
        SDK.Lang.PopContext();
      }
    };
  }

  SDK.Lang.PopContext();

  // ---------------------------------------------------------------------------
  // Conditions
  // ---------------------------------------------------------------------------

  SDK.Lang.PushContext("plugins.wyrdforge.conditions");

  {
    const C = SDK.Conditions["WyrdForge_OnQueryComplete"] = class extends SDK.IConditionBase {
      constructor() {
        super(PLUGIN_CLASS);
        SDK.Lang.PushContext("on-query-complete");
        this._info.SetName(lang(".list-name"));
        this._info.SetDescription(lang(".description"));
        this._info.SetDisplayText(lang(".display-text"));
        this._info.SetIsTrigger(true);
        SDK.Lang.PopContext();
      }
    };
  }

  {
    const C = SDK.Conditions["WyrdForge_OnQueryError"] = class extends SDK.IConditionBase {
      constructor() {
        super(PLUGIN_CLASS);
        SDK.Lang.PushContext("on-query-error");
        this._info.SetName(lang(".list-name"));
        this._info.SetDescription(lang(".description"));
        this._info.SetDisplayText(lang(".display-text"));
        this._info.SetIsTrigger(true);
        SDK.Lang.PopContext();
      }
    };
  }

  {
    const C = SDK.Conditions["WyrdForge_IsReady"] = class extends SDK.IConditionBase {
      constructor() {
        super(PLUGIN_CLASS);
        SDK.Lang.PushContext("is-ready");
        this._info.SetName(lang(".list-name"));
        this._info.SetDescription(lang(".description"));
        this._info.SetDisplayText(lang(".display-text"));
        SDK.Lang.PopContext();
      }
    };
  }

  SDK.Lang.PopContext();

  // ---------------------------------------------------------------------------
  // Expressions
  // ---------------------------------------------------------------------------

  SDK.Lang.PushContext("plugins.wyrdforge.expressions");

  {
    const E = SDK.Expressions["WyrdForge_LastResponse"] = class extends SDK.IExpressionBase {
      constructor() {
        super(PLUGIN_CLASS);
        SDK.Lang.PushContext("last-response");
        this._info.SetName(lang(".translated-name"));
        this._info.SetDescription(lang(".description"));
        this._info.SetReturnType("string");
        SDK.Lang.PopContext();
      }
    };
  }

  {
    const E = SDK.Expressions["WyrdForge_LastError"] = class extends SDK.IExpressionBase {
      constructor() {
        super(PLUGIN_CLASS);
        SDK.Lang.PushContext("last-error");
        this._info.SetName(lang(".translated-name"));
        this._info.SetDescription(lang(".description"));
        this._info.SetReturnType("string");
        SDK.Lang.PopContext();
      }
    };
  }

  SDK.Lang.PopContext();
}
