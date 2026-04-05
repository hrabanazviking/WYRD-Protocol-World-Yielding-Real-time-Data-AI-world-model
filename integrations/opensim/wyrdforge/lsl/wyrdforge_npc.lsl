// wyrdforge_npc.lsl — WyrdForge NPC script for Second Life / OpenSim (Phase 12A).
//
// Drop this script into any in-world object (NPC prim, talking sign, character object).
// When an avatar touches the object, it queries WYRD world context for that avatar
// and says the response aloud in local chat.
//
// SETUP
//   1. Start WyrdHTTPServer on a machine accessible from the region server.
//      python -m wyrdforge.server --port 8765
//   2. In Second Life, HTTP-out requires the destination to be on the allow-list
//      (or on a public IP). In OpenSim you control the allow-list via OpenSim.ini.
//   3. Drop this script into your NPC prim or interactive object.
//   4. Say on channel WYRD_CONFIG_CHANNEL (default -7650):
//        host:your.server.ip
//        port:8765
//        persona:your_default_persona_id
//
// CHANNEL COMMANDS (say on channel -7650 near the object, owner only):
//   host:<hostname_or_ip>   — set WyrdHTTPServer hostname
//   port:<number>            — set WyrdHTTPServer port
//   persona:<persona_id>     — set a fixed persona_id (overrides avatar name lookup)
//   enabled:true|false       — toggle the script on/off
//   status                   — whisper current config to owner

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

string  wyrd_host      = "localhost";
integer wyrd_port      = 8765;
string  fixed_persona  = "";    // if set, always query this persona instead of toucher's name
integer enabled        = TRUE;
integer WYRD_CONFIG_CHANNEL = -7650;

// ---------------------------------------------------------------------------
// Internal state
// ---------------------------------------------------------------------------

key     pending_request = NULL_KEY;
string  pending_avatar  = "";
integer listen_handle   = 0;

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

string wyrd_base_url()
{
    return "http://" + wyrd_host + ":" + (string)wyrd_port;
}

/// Normalize an avatar display name to a WYRD persona_id.
/// Lowercases, replaces non-alphanumeric chars with underscores,
/// collapses consecutive underscores, strips leading/trailing underscores,
/// truncates at 64 characters.
string wyrd_normalize_persona_id(string name)
{
    string result  = llToLower(name);
    string out     = "";
    integer i      = 0;
    integer len    = llStringLength(result);
    integer last_u = FALSE;

    while (i < len)
    {
        string c = llGetSubString(result, i, i);
        integer o = llOrd(result, i);

        // a-z, 0-9, _
        if ((o >= 97 && o <= 122) || (o >= 48 && o <= 57) || o == 95)
        {
            out    += c;
            last_u  = (o == 95);
        }
        else if (!last_u)
        {
            out    += "_";
            last_u  = TRUE;
        }
        ++i;
    }

    // Strip leading underscores
    while (llStringLength(out) > 0 && llGetSubString(out, 0, 0) == "_")
        out = llDeleteSubString(out, 0, 0);

    // Strip trailing underscores
    while (llStringLength(out) > 0 &&
           llGetSubString(out, llStringLength(out) - 1, llStringLength(out) - 1) == "_")
        out = llDeleteSubString(out, llStringLength(out) - 1, llStringLength(out) - 1);

    // Truncate at 64
    if (llStringLength(out) > 64)
        out = llGetSubString(out, 0, 63);

    return out;
}

/// Build a /query request body JSON string.
string wyrd_build_query_body(string persona_id, string user_input)
{
    if (user_input == "")
        user_input = "What is the current world state?";

    return "{\"persona_id\":\"" + persona_id
         + "\",\"user_input\":\"" + user_input
         + "\",\"use_turn_loop\":false}";
}

/// Build a /event observation body JSON string.
string wyrd_build_observation_body(string title, string summary)
{
    return "{\"event_type\":\"observation\","
         + "\"payload\":{\"title\":\"" + title
         + "\",\"summary\":\"" + summary + "\"}}";
}

/// Build a /event fact body JSON string.
string wyrd_build_fact_body(string subject_id, string key, string value)
{
    return "{\"event_type\":\"fact\","
         + "\"payload\":{\"subject_id\":\"" + subject_id
         + "\",\"key\":\"" + key
         + "\",\"value\":\"" + value + "\"}}";
}

// ---------------------------------------------------------------------------
// HTTP request dispatch
// ---------------------------------------------------------------------------

/// POST body_json to path on WyrdHTTPServer.
key wyrd_post(string path, string body_json)
{
    return llHTTPRequest(
        wyrd_base_url() + path,
        [
            HTTP_METHOD,         "POST",
            HTTP_MIMETYPE,       "application/json",
            HTTP_BODY_MAXLENGTH, 16384,
            HTTP_VERIFY_CERT,    FALSE   // set TRUE in production with a valid cert
        ],
        body_json
    );
}

// ---------------------------------------------------------------------------
// Config command handler
// ---------------------------------------------------------------------------

integer handle_config_command(string sender_name, key sender_id, string message)
{
    // Only owner may configure
    if (sender_id != llGetOwner()) return FALSE;

    if (message == "status")
    {
        llWhisper(0, "[WyrdForge] host=" + wyrd_host
                    + " port=" + (string)wyrd_port
                    + " persona=" + (fixed_persona == "" ? "(avatar name)" : fixed_persona)
                    + " enabled=" + (string)enabled);
        return TRUE;
    }

    list parts = llParseString2List(message, [":"], []);
    if (llGetListLength(parts) < 2) return FALSE;

    string cmd = llToLower(llStringTrim(llList2String(parts, 0), STRING_TRIM));
    string val = llStringTrim(llList2String(parts, 1), STRING_TRIM);

    if (cmd == "host")   { wyrd_host = val;          llWhisper(0, "[WyrdForge] host set to " + val); return TRUE; }
    if (cmd == "port")   { wyrd_port = (integer)val; llWhisper(0, "[WyrdForge] port set to " + val); return TRUE; }
    if (cmd == "persona"){ fixed_persona = val;       llWhisper(0, "[WyrdForge] persona set to " + (val == "" ? "(avatar name)" : val)); return TRUE; }
    if (cmd == "enabled"){ enabled = (llToLower(val) == "true"); llWhisper(0, "[WyrdForge] enabled=" + (string)enabled); return TRUE; }

    return FALSE;
}

// ---------------------------------------------------------------------------
// Event handlers
// ---------------------------------------------------------------------------

default
{
    state_entry()
    {
        listen_handle = llListen(WYRD_CONFIG_CHANNEL, "", NULL_KEY, "");
        llOwnerSay("[WyrdForge] NPC script ready. Touch to query WYRD world context.");
        llOwnerSay("[WyrdForge] Config channel: " + (string)WYRD_CONFIG_CHANNEL);
    }

    touch_start(integer num_detected)
    {
        if (!enabled) return;
        if (pending_request != NULL_KEY)
        {
            llWhisper(0, "[WyrdForge] Still waiting for a previous response…");
            return;
        }

        string av_name = llDetectedName(0);
        key    av_key  = llDetectedKey(0);

        string persona_id = (fixed_persona != "")
            ? fixed_persona
            : wyrd_normalize_persona_id(av_name);

        if (persona_id == "")
        {
            llWhisper(0, "[WyrdForge] Could not determine persona ID for: " + av_name);
            return;
        }

        // Push a "touched" observation to WYRD memory
        string obs_body = wyrd_build_observation_body(
            "Avatar touched NPC",
            av_name + " touched the object."
        );
        wyrd_post("/event", obs_body);  // fire-and-forget

        // Query WYRD for world context
        string query_body = wyrd_build_query_body(persona_id, "");
        pending_request   = wyrd_post("/query", query_body);
        pending_avatar    = av_name;
    }

    http_response(key request_id, integer status, list metadata, string body)
    {
        if (request_id != pending_request) return;
        pending_request = NULL_KEY;

        if (status >= 200 && status < 300)
        {
            // Extract the "response" field using llJsonGetValue (LSL17+ / OpenSim)
            string response = llJsonGetValue(body, ["response"]);

            if (response == JSON_INVALID || response == "" || response == "null")
                response = "The spirits whisper nothing of note.";

            llSay(0, response);
        }
        else
        {
            llOwnerSay("[WyrdForge] HTTP error " + (string)status
                      + " querying WYRD for " + pending_avatar);
        }

        pending_avatar = "";
    }

    listen(integer channel, string name, key id, string message)
    {
        if (channel == WYRD_CONFIG_CHANNEL)
            handle_config_command(name, id, message);
    }

    on_rez(integer start_param)
    {
        // Re-register listen on rez (listen handles don't survive across rez)
        if (listen_handle) llListenRemove(listen_handle);
        listen_handle = llListen(WYRD_CONFIG_CHANNEL, "", NULL_KEY, "");
    }

    changed(integer change)
    {
        if (change & CHANGED_OWNER)
            llResetScript();
    }
}
