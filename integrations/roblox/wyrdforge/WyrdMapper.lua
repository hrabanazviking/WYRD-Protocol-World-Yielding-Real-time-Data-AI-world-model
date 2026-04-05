--[[
  WyrdMapper.lua — Pure helper functions for WyrdForge Roblox integration.

  No Roblox service dependencies — all functions operate on plain Luau values.
  This module is tested directly via Python mirror tests (tests/test_wyrdforge.py).

  Functions:
    WyrdMapper.escapeJson(s)                        → escaped string
    WyrdMapper.normalizePersonaId(name)             → persona_id string
    WyrdMapper.buildQueryBody(personaId, userInput) → JSON string
    WyrdMapper.buildObservationBody(title, summary) → JSON string
    WyrdMapper.buildFactBody(subjectId, key, value) → JSON string
    WyrdMapper.toFacts(npcName, npcId, placeId, customFacts) → array of {key, value}
    WyrdMapper.parseResponse(body)                  → response string
--]]

local WyrdMapper = {}

-- ---------------------------------------------------------------------------
-- JSON string escaping
-- ---------------------------------------------------------------------------

--- Escape a string value for safe embedding inside a JSON string literal.
--- Handles double-quote, backslash, and common control characters.
function WyrdMapper.escapeJson(s)
    if s == nil then return "" end
    s = tostring(s)

    local result = s
        :gsub('\\', '\\\\')   -- backslash first (must be before other replacements)
        :gsub('"',  '\\"')
        :gsub('\b', '\\b')
        :gsub('\f', '\\f')
        :gsub('\n', '\\n')
        :gsub('\r', '\\r')
        :gsub('\t', '\\t')

    -- Remaining control characters (0x00–0x1F, excluding those above)
    result = result:gsub('[\0-\x08\x0b\x0c\x0e-\x1f]', function(c)
        return string.format('\\u%04x', string.byte(c))
    end)

    return result
end

-- ---------------------------------------------------------------------------
-- Persona ID normalisation
-- ---------------------------------------------------------------------------

--- Normalize a player / NPC name to a WYRD persona_id.
--- Rules: lowercase, non-alphanumeric → '_', collapse '__+', strip leading/trailing '_', truncate 64.
function WyrdMapper.normalizePersonaId(name)
    if name == nil or name == "" then return "" end

    -- Lowercase
    local result = string.lower(name)

    -- Replace non-alphanumeric (except underscore) with underscore
    result = result:gsub('[^%a%d_]', '_')

    -- Collapse consecutive underscores
    result = result:gsub('_+', '_')

    -- Strip leading underscores
    result = result:gsub('^_+', '')

    -- Strip trailing underscores
    result = result:gsub('_+$', '')

    -- Truncate at 64
    if #result > 64 then
        result = result:sub(1, 64)
    end

    return result
end

-- ---------------------------------------------------------------------------
-- JSON body builders
-- ---------------------------------------------------------------------------

--- Build the JSON body for POST /query.
--- @param personaId string  WYRD persona_id
--- @param userInput string  Player input; empty → default world-state question
function WyrdMapper.buildQueryBody(personaId, userInput)
    if userInput == nil or userInput:match('^%s*$') then
        userInput = "What is the current world state?"
    end
    return string.format(
        '{"persona_id":"%s","user_input":"%s","use_turn_loop":false}',
        WyrdMapper.escapeJson(personaId),
        WyrdMapper.escapeJson(userInput)
    )
end

--- Build the JSON body for POST /event (observation).
function WyrdMapper.buildObservationBody(title, summary)
    return string.format(
        '{"event_type":"observation","payload":{"title":"%s","summary":"%s"}}',
        WyrdMapper.escapeJson(title),
        WyrdMapper.escapeJson(summary)
    )
end

--- Build the JSON body for POST /event (fact).
function WyrdMapper.buildFactBody(subjectId, key, value)
    return string.format(
        '{"event_type":"fact","payload":{"subject_id":"%s","key":"%s","value":"%s"}}',
        WyrdMapper.escapeJson(subjectId),
        WyrdMapper.escapeJson(key),
        WyrdMapper.escapeJson(value)
    )
end

-- ---------------------------------------------------------------------------
-- Fact list builder
-- ---------------------------------------------------------------------------

--- Build a list of WYRD facts from NPC / player data.
--- @param npcName    string           Display name
--- @param npcId      string           Roblox UserId or model name
--- @param placeId    string|nil       game.PlaceId as string; nil to omit
--- @param customFacts table|nil       {key=value, ...}; nil values are skipped
--- @return           table            Array of {key=string, value=string}
function WyrdMapper.toFacts(npcName, npcId, placeId, customFacts)
    local facts = {}

    if npcName and npcName ~= "" then
        table.insert(facts, {key = "name", value = npcName})
    end
    if npcId and npcId ~= "" then
        table.insert(facts, {key = "npc_id", value = tostring(npcId)})
    end
    if placeId and placeId ~= "" then
        table.insert(facts, {key = "place_id", value = tostring(placeId)})
    end
    if customFacts then
        for k, v in pairs(customFacts) do
            if k and k ~= "" and v ~= nil and v ~= "" then
                table.insert(facts, {key = k, value = tostring(v)})
            end
        end
    end

    return facts
end

-- ---------------------------------------------------------------------------
-- Response parser
-- ---------------------------------------------------------------------------

local FALLBACK = "The spirits whisper nothing of note."

--- Extract the "response" string from a WyrdHTTPServer /query JSON reply.
--- Uses a simple pattern match — no full JSON parser needed for this field.
function WyrdMapper.parseResponse(body)
    if body == nil or body:match('^%s*$') then
        return FALLBACK
    end

    -- Match: "response":"<value>"
    local value = body:match('"response"%s*:%s*"(.-[^\\])"')
    if value == nil then
        -- Try empty string case: "response":""
        if body:match('"response"%s*:%s*""') then
            return FALLBACK
        end
        return FALLBACK
    end

    -- Unescape basic sequences for display
    value = value
        :gsub('\\"',  '"')
        :gsub('\\\\', '\\')
        :gsub('\\n',  '\n')
        :gsub('\\r',  '\r')
        :gsub('\\t',  '\t')

    if value:match('^%s*$') then
        return FALLBACK
    end

    return value
end

return WyrdMapper
