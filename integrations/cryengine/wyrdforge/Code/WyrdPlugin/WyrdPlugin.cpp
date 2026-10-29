// WyrdPlugin.cpp — CryEngine plugin shell for WyrdForge.
//
// ═══ STUB — READ BEFORE TRUSTING ════════════════════════════════════════
//
// This file is a STUB at exactly one layer: the HTTP transport.
//
// As of E3 the client LOGIC is real: every IWyrdSystem method below
// delegates to WyrdClientCore (WyrdClientCore.h/.cpp), which builds the
// request bodies, parses responses, applies the silent/fallback error
// semantics, and queues completions for the game thread — and which is
// compiled and executed by the honest harness
// (tests/honest/WyrdClientCoreHonestTest.cpp).
//
// What does NOT exist anywhere in this repo:
//   - a libcurl (or CryEngine HTTP) transport bound to that core, and
//   - CryEngine plugin registration (ICryPlugin / plugin-manager glue —
//     its shape varies across CE 5.6 / 5.7 / Lumberyard-era forks).
//
// With no transport bound, the core fails honestly: GetLastError()
// reports "no HTTP transport bound", and queries complete (via
// DrainCompletions) with a Failure result, or with the configured
// fallback text in silent mode. Nothing silently pretends to work.
// Binding a transport in a real CryEngine project means implementing
// IWyrdTransport over libcurl and calling SetTransport() — one class,
// two methods (Post/Get).
//
// This file includes no CryEngine headers, so it compiles anywhere the
// core compiles (the honest harness build proves that much). In-engine
// behaviour is NOT verified: no CryEngine exists on the machine that
// produced E3. See TESTING.md for the full honesty picture.
// ════════════════════════════════════════════════════════════════════════
//
// Usage inside a CryEngine project (once a transport is bound):
//
//   IWyrdSystem* pWyrd = ...;  // your plugin-manager lookup
//   pWyrd->SetConfig({ "your.server.ip", 8765 });
//   pWyrd->QueryAsync("sigrid_npc", playerInput,
//       [this](WyrdForge::WyrdQueryResult r)
//       {
//           GetDialogueComponent()->ShowText(r.response);
//       });
//   // once per tick, on the game thread:
//   plugin->DrainCompletions();

#include "IWyrdSystem.h"
#include "WyrdClientCore.h"
#include "WyrdHelpers.h"

namespace WyrdForge
{

/// <summary>
/// The CryEngine-facing IWyrdSystem shell. All logic lives in
/// WyrdClientCore; this class only delegates (and, in a real deployment,
/// is where plugin registration + the libcurl transport binding belong).
/// </summary>
class WyrdPlugin final : public IWyrdSystem
{
public:
    void SetConfig(const WyrdConfig& config) override { m_core.SetConfig(config); }
    const WyrdConfig& GetConfig() const override      { return m_core.GetConfig(); }

    void QueryAsync(const std::string& personaId,
                    const std::string& userInput,
                    std::function<void(WyrdQueryResult)> onComplete) override
    {
        m_core.QueryAsync(personaId, userInput, std::move(onComplete));
    }

    void PushObservation(const std::string& title,
                         const std::string& summary) override
    {
        m_core.PushObservation(title, summary);
    }

    void PushFact(const std::string& subjectId,
                  const std::string& key,
                  const std::string& value) override
    {
        m_core.PushFact(subjectId, key, value);
    }

    void SyncEntity(const std::string& personaId,
                    const std::vector<WyrdFact>& facts) override
    {
        m_core.SyncEntity(personaId, facts);
    }

    void HealthCheckAsync(std::function<void(bool)> onResult) override
    {
        m_core.HealthCheckAsync(std::move(onResult));
    }

    const std::string& GetLastError() const override { return m_core.GetLastError(); }

    /// <summary>Bind the HTTP transport (the libcurl layer a deployment
    /// supplies). Not part of IWyrdSystem; without it the core reports
    /// the no-transport error described in the file header.</summary>
    void SetTransport(std::shared_ptr<IWyrdTransport> transport)
    {
        m_core.SetTransport(std::move(transport));
    }

    /// <summary>Run queued completions — call once per tick on the game thread.</summary>
    std::size_t DrainCompletions() { return m_core.DrainCompletions(); }

private:
    WyrdClientCore m_core;
};

} // namespace WyrdForge
