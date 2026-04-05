#pragma once

#include <string>
#include <vector>
#include <functional>

namespace WyrdForge
{

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

struct WyrdFact
{
    std::string key;
    std::string value;
};

struct WyrdQueryResult
{
    bool        success;
    std::string personaId;
    std::string response;
    std::string errorMessage;

    static WyrdQueryResult Ok(std::string personaId, std::string response)
    {
        return WyrdQueryResult{ true,  std::move(personaId),
                                std::move(response), {} };
    }

    static WyrdQueryResult Failure(std::string personaId, std::string error)
    {
        return WyrdQueryResult{ false, std::move(personaId),
                                {}, std::move(error) };
    }
};

struct WyrdConfig
{
    std::string host           = "localhost";
    int         port           = 8765;
    int         timeoutSeconds = 10;
    bool        silentOnError  = true;
    std::string fallbackResponse = "The spirits whisper nothing of note.";

    std::string baseUrl() const
    {
        return "http://" + host + ":" + std::to_string(port);
    }
};

// ---------------------------------------------------------------------------
// IWyrdSystem — CryEngine plugin interface
// ---------------------------------------------------------------------------

struct IWyrdSystem
{
    virtual ~IWyrdSystem() = default;

    virtual void            SetConfig(const WyrdConfig& config) = 0;
    virtual const WyrdConfig& GetConfig() const = 0;

    /**
     * Query WYRD world context. Async — calls onComplete on the game thread
     * when the HTTP response arrives. Uses CryEngine's ISystem / ITimer
     * tick to pump pending completions.
     *
     * CryEngine wiring:
     *   // In your entity component Update():
     *   gEnv->pSystem->GetIPluginManager()
     *       ->QueryPlugin<IWyrdSystem>()->QueryAsync(
     *           "sigrid_npc", playerInput,
     *           [this](WyrdQueryResult r){ SetDialogueText(r.response); });
     */
    virtual void QueryAsync(const std::string& personaId,
                            const std::string& userInput,
                            std::function<void(WyrdQueryResult)> onComplete) = 0;

    /** Push an observation event. Fire-and-forget. */
    virtual void PushObservation(const std::string& title,
                                 const std::string& summary) = 0;

    /** Push a fact. Fire-and-forget. */
    virtual void PushFact(const std::string& subjectId,
                          const std::string& key,
                          const std::string& value) = 0;

    /** Sync an entity by pushing all its facts. Fire-and-forget per fact. */
    virtual void SyncEntity(const std::string& personaId,
                            const std::vector<WyrdFact>& facts) = 0;

    /** Async health check. */
    virtual void HealthCheckAsync(std::function<void(bool)> onResult) = 0;

    /** Last error from a fire-and-forget or failed call. Empty if none. */
    virtual const std::string& GetLastError() const = 0;
};

} // namespace WyrdForge
