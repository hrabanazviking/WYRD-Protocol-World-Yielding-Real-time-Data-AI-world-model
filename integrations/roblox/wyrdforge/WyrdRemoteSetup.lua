--[[
  WyrdRemoteSetup.lua — Server Script that wires RemoteFunction / RemoteEvent
  so client-side LocalScripts can reach the server-side WyrdBridge.

  Place this Script in ServerScriptService alongside WyrdBridge.lua.
  It runs once on server start and creates the RemoteEvents that
  WyrdClientBridge.lua expects to find in ReplicatedStorage.

  ─── ARCHITECTURE ───────────────────────────────────────────────────────────
  Client LocalScript
      │  :InvokeServer(personaId, input)
      ▼
  ReplicatedStorage.WyrdEvents.WyrdQuery  [RemoteFunction]
      │  server-side OnServerInvoke
      ▼
  WyrdBridge:Query(personaId, input)
      │  HTTP POST /query → WyrdHTTPServer
      ▼
  response string returned to client
  ─────────────────────────────────────────────────────────────────────────────

  RemoteEvents / RemoteFunctions created:
    ReplicatedStorage.WyrdEvents (Folder)
      WyrdQuery        [RemoteFunction]  — client invokes, server returns string
      WyrdObservation  [RemoteEvent]     — client fires, server pushes observation
--]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local WyrdBridge        = require(script.Parent.WyrdBridge)
local WyrdMapper        = require(script.Parent.WyrdMapper)

-- ---------------------------------------------------------------------------
-- Create WyrdEvents folder in ReplicatedStorage
-- ---------------------------------------------------------------------------

local eventsFolder = ReplicatedStorage:FindFirstChild("WyrdEvents")
if not eventsFolder then
    eventsFolder = Instance.new("Folder")
    eventsFolder.Name   = "WyrdEvents"
    eventsFolder.Parent = ReplicatedStorage
end

-- ---------------------------------------------------------------------------
-- WyrdQuery RemoteFunction
-- Allows clients to synchronously query WYRD world context.
-- Server yields on HTTP; client yields waiting for server response.
-- ---------------------------------------------------------------------------

local wyrdQuery = eventsFolder:FindFirstChild("WyrdQuery")
if not wyrdQuery then
    wyrdQuery        = Instance.new("RemoteFunction")
    wyrdQuery.Name   = "WyrdQuery"
    wyrdQuery.Parent = eventsFolder
end

wyrdQuery.OnServerInvoke = function(player, personaId, input)
    -- Validate inputs
    if type(personaId) ~= "string" or personaId == "" then
        personaId = WyrdMapper.normalizePersonaId(player.Name)
    end
    if type(input) ~= "string" then
        input = ""
    end

    -- Optional: push a "player queried NPC" observation
    WyrdBridge:PushObservation(
        "Player queried NPC",
        player.Name .. " asked: " .. input
    )

    return WyrdBridge:Query(personaId, input)
end

-- ---------------------------------------------------------------------------
-- WyrdObservation RemoteEvent
-- Allows clients to push observations without waiting for a response.
-- ---------------------------------------------------------------------------

local wyrdObs = eventsFolder:FindFirstChild("WyrdObservation")
if not wyrdObs then
    wyrdObs        = Instance.new("RemoteEvent")
    wyrdObs.Name   = "WyrdObservation"
    wyrdObs.Parent = eventsFolder
end

wyrdObs.OnServerEvent:Connect(function(player, title, summary)
    if type(title)   ~= "string" then title   = "Observation" end
    if type(summary) ~= "string" then summary = player.Name   end
    WyrdBridge:PushObservation(title, summary)
end)

-- ---------------------------------------------------------------------------
-- Server ready
-- ---------------------------------------------------------------------------

print("[WyrdForge] RemoteSetup complete — WyrdQuery and WyrdObservation ready.")
