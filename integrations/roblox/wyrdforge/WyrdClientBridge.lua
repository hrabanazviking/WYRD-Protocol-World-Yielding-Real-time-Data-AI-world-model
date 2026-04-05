--[[
  WyrdClientBridge.lua — LocalScript helper for client-side WYRD access.

  Place this LocalScript (or require it from a LocalScript) in
  StarterPlayerScripts or StarterCharacterScripts.

  It communicates with the server-side WyrdBridge via the RemoteFunction and
  RemoteEvent created by WyrdRemoteSetup.lua.

  USAGE:
    local WyrdClient = require(game.StarterPlayer.StarterPlayerScripts.WyrdClientBridge)

    -- Query an NPC (yields current thread until server responds):
    local reply = WyrdClient:Query("sigrid_npc", "What do you know of the old gods?")
    npcDialogue.Text = reply

    -- Push an observation (fire-and-forget, no yield):
    WyrdClient:PushObservation("Player interacted with altar", "Player touched the runestone.")

  NOTE: RemoteFunction:InvokeServer() yields the LocalScript thread.
  If you need non-blocking behaviour, wrap in task.spawn().
--]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

-- Wait for the server to create the events folder (may take a frame)
local eventsFolder = ReplicatedStorage:WaitForChild("WyrdEvents", 10)
if not eventsFolder then
    warn("[WyrdForge] WyrdClientBridge: WyrdEvents folder not found in ReplicatedStorage. "
       .. "Ensure WyrdRemoteSetup is running on the server.")
end

local wyrdQuery = eventsFolder and eventsFolder:WaitForChild("WyrdQuery",       10)
local wyrdObs   = eventsFolder and eventsFolder:WaitForChild("WyrdObservation",  10)

-- ---------------------------------------------------------------------------
-- Module
-- ---------------------------------------------------------------------------

local WyrdClientBridge = {}

--- Query WYRD world context for an NPC. Yields the current thread.
--- @param personaId string  WYRD persona_id for the NPC being queried
--- @param input     string  Player dialogue input
--- @return          string  NPC response, or fallback if server is unreachable
function WyrdClientBridge:Query(personaId, input)
    if not wyrdQuery then
        return "The spirits are silent."
    end
    local ok, result = pcall(function()
        return wyrdQuery:InvokeServer(personaId, input)
    end)
    if ok and type(result) == "string" then
        return result
    end
    warn("[WyrdForge] WyrdClientBridge:Query error: " .. tostring(result))
    return "The spirits are silent."
end

--- Push an observation to WYRD. Fire-and-forget (does not yield).
--- @param title   string  Short event title
--- @param summary string  Longer event description
function WyrdClientBridge:PushObservation(title, summary)
    if not wyrdObs then return end
    wyrdObs:FireServer(title, summary)
end

return WyrdClientBridge
