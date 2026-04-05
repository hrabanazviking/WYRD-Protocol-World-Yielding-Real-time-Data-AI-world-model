// wyrdforge.cpp — WyrdForge Defold native extension (Phase 11F).
//
// Provides three pure-function Lua bindings for the WYRD Protocol:
//
//   wyrdforge.normalize_persona_id(name)              -> string
//   wyrdforge.build_query_body(persona_id, input)     -> json_string
//   wyrdforge.build_event_body(event_type, payload)   -> json_string
//
// The Lua module (lua/wyrdforge.lua) uses these to build request bodies
// and Defold's built-in http module to send them.
//
// Defold extension SDK docs: https://defold.com/manuals/extensions/

#define LIB_NAME "wyrdforge"
#define MODULE_NAME "wyrdforge"

#include <dmsdk/sdk.h>
#include <string>
#include <algorithm>
#include <cctype>

namespace wyrdforge {

// ---------------------------------------------------------------------------
// Pure C++ helpers (also tested via Python equivalents in tests/)
// ---------------------------------------------------------------------------

/// Escape a string for embedding in a JSON string literal.
static std::string EscapeJson(const std::string& s)
{
    std::string out;
    out.reserve(s.size() + 8);
    for (unsigned char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b";  break;
            case '\f': out += "\\f";  break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    snprintf(buf, sizeof(buf), "\\u%04x", c);
                    out += buf;
                } else {
                    out += (char)c;
                }
                break;
        }
    }
    return out;
}

/// Normalize a display name to a WYRD persona_id (lowercase snake_case, max 64 chars).
static std::string NormalizePersonaId(const std::string& name)
{
    std::string out;
    out.reserve(name.size());
    bool last_under = false;

    for (unsigned char c : name) {
        if (std::isalnum(c)) {
            out += (char)std::tolower((int)c);
            last_under = false;
        } else if (c == '_') {
            out += '_';
            last_under = true;
        } else if (!last_under) {
            out += '_';
            last_under = true;
        }
    }

    // Strip leading and trailing underscores
    size_t start = out.find_first_not_of('_');
    if (start == std::string::npos) return "";
    size_t end = out.find_last_not_of('_');
    out = out.substr(start, end - start + 1);

    // Truncate to 64 characters
    if (out.size() > 64) out.resize(64);

    return out;
}

/// Build a /query request body JSON string.
static std::string BuildQueryBody(const std::string& persona_id, const std::string& user_input)
{
    const std::string& input = user_input.empty()
        ? std::string("What is the current world state?")
        : user_input;

    return std::string("{")
        + "\"persona_id\":\"" + EscapeJson(persona_id) + "\","
        + "\"user_input\":\"" + EscapeJson(input) + "\","
        + "\"use_turn_loop\":false"
        + "}";
}

/// Build a /event request body JSON string.
/// payload_json must be a valid, already-encoded JSON object string.
static std::string BuildEventBody(const std::string& event_type, const std::string& payload_json)
{
    return std::string("{")
        + "\"event_type\":\"" + EscapeJson(event_type) + "\","
        + "\"payload\":" + payload_json
        + "}";
}

// ---------------------------------------------------------------------------
// Lua bindings
// ---------------------------------------------------------------------------

/// wyrdforge.normalize_persona_id(name) -> string
static int L_NormalizePersonaId(lua_State* L)
{
    DM_LUA_STACK_CHECK(L, 1);
    const char* name = luaL_checkstring(L, 1);
    std::string result = NormalizePersonaId(std::string(name ? name : ""));
    lua_pushstring(L, result.c_str());
    return 1;
}

/// wyrdforge.build_query_body(persona_id, user_input) -> json_string
static int L_BuildQueryBody(lua_State* L)
{
    DM_LUA_STACK_CHECK(L, 1);
    const char* persona_id = luaL_checkstring(L, 1);
    const char* user_input = luaL_optstring(L, 2, "");
    std::string result = BuildQueryBody(
        std::string(persona_id ? persona_id : ""),
        std::string(user_input ? user_input : "")
    );
    lua_pushstring(L, result.c_str());
    return 1;
}

/// wyrdforge.build_event_body(event_type, payload_json) -> json_string
static int L_BuildEventBody(lua_State* L)
{
    DM_LUA_STACK_CHECK(L, 1);
    const char* event_type  = luaL_checkstring(L, 1);
    const char* payload_json = luaL_checkstring(L, 2);
    std::string result = BuildEventBody(
        std::string(event_type   ? event_type   : ""),
        std::string(payload_json ? payload_json : "{}")
    );
    lua_pushstring(L, result.c_str());
    return 1;
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

static const luaL_reg Module_methods[] =
{
    {"normalize_persona_id", L_NormalizePersonaId},
    {"build_query_body",     L_BuildQueryBody},
    {"build_event_body",     L_BuildEventBody},
    {0, 0}
};

static void LuaInit(lua_State* L)
{
    int top = lua_gettop(L);
    luaL_register(L, MODULE_NAME, Module_methods);
    lua_pop(L, 1);
    assert(top == lua_gettop(L));
}

// ---------------------------------------------------------------------------
// Extension lifecycle
// ---------------------------------------------------------------------------

static dmExtension::Result AppInitialize(dmExtension::AppParams* params)
{
    return dmExtension::RESULT_OK;
}

static dmExtension::Result AppFinalize(dmExtension::AppParams* params)
{
    return dmExtension::RESULT_OK;
}

static dmExtension::Result Initialize(dmExtension::Params* params)
{
    LuaInit(params->m_L);
    dmLogInfo("WyrdForge extension initialized.");
    return dmExtension::RESULT_OK;
}

static dmExtension::Result Finalize(dmExtension::Params* params)
{
    return dmExtension::RESULT_OK;
}

} // namespace wyrdforge

DM_DECLARE_EXTENSION(WyrdForge, LIB_NAME,
    wyrdforge::AppInitialize,
    wyrdforge::AppFinalize,
    wyrdforge::Initialize,
    0,   // update — not needed
    0,   // on_event — not needed
    wyrdforge::Finalize)
