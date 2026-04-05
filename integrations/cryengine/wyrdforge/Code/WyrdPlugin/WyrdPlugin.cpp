// WyrdPlugin.cpp — CryEngine ICryPlugin implementation for WyrdForge.
//
// Uses libcurl for HTTP (CryEngine's preferred HTTP approach for plugins).
// For async calls, pushes completed work to a queue drained on the game thread
// via IPluginManager::Update() / IEntityComponent::Update().
//
// ─── CRYENGINE SETUP ──────────────────────────────────────────────────────────
//
//  1. Register the plugin in your .cryproject:
//       "plugins": [{ "guid": "...", "path": "WyrdForge" }]
//
//  2. Access the system:
//       IWyrdSystem* pWyrd = gEnv->pSystem->GetIPluginManager()
//           ->QueryPlugin<IWyrdSystem>();
//
//  3. In an entity component's Initialize():
//       pWyrd->SetConfig({ "your.server.ip", 8765 });
//
//  4. In response to player chat / dialogue trigger:
//       pWyrd->QueryAsync("sigrid_npc", playerInput,
//           [this](WyrdForge::WyrdQueryResult r)
//           {
//               GetDialogueComponent()->ShowText(r.response);
//           });
//
//  5. On entity spawn:
//       pWyrd->SyncEntity(personaId, WyrdHelpers::ToFacts(
//           entity->GetName(), entity->GetGuidAsString(), levelName, {}));
//
// ─────────────────────────────────────────────────────────────────────────────

#include "IWyrdSystem.h"
#include "WyrdHelpers.h"

// NOTE: Full libcurl implementation omitted — CryEngine plugin systems vary
// significantly across CE versions (5.6, 5.7, LY fork). The interface above
// (IWyrdSystem) is the stable contract; the HTTP backend is swappable.
// A reference curl implementation would use:
//   curl_easy_setopt(curl, CURLOPT_URL, config.baseUrl() + path);
//   curl_easy_setopt(curl, CURLOPT_POST, 1L);
//   curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
//   curl_easy_setopt(curl, CURLOPT_TIMEOUT, config.timeoutSeconds);
//   curl_easy_perform(curl);
// wrapped in a std::async / CryEngine threadpool task, with results queued
// to the game thread via a mutex-protected std::queue<std::function<void()>>.

namespace WyrdForge
{

class WyrdPlugin final : public IWyrdSystem
{
public:
    void SetConfig(const WyrdConfig& config) override { m_config = config; }
    const WyrdConfig& GetConfig() const override      { return m_config;  }

    void QueryAsync(const std::string& personaId,
                    const std::string& userInput,
                    std::function<void(WyrdQueryResult)> onComplete) override
    {
        // TODO: dispatch to libcurl thread, queue onComplete for game-thread drain
        (void)personaId; (void)userInput; (void)onComplete;
    }

    void PushObservation(const std::string& title,
                         const std::string& summary) override
    {
        // TODO: async libcurl POST /event with BuildObservationBody
        (void)title; (void)summary;
    }

    void PushFact(const std::string& subjectId,
                  const std::string& key,
                  const std::string& value) override
    {
        (void)subjectId; (void)key; (void)value;
    }

    void SyncEntity(const std::string& personaId,
                    const std::vector<WyrdFact>& facts) override
    {
        for (const auto& f : facts)
            PushFact(personaId, f.key, f.value);
    }

    void HealthCheckAsync(std::function<void(bool)> onResult) override
    {
        (void)onResult;
    }

    const std::string& GetLastError() const override { return m_lastError; }

private:
    WyrdConfig  m_config;
    std::string m_lastError;
};

} // namespace WyrdForge
