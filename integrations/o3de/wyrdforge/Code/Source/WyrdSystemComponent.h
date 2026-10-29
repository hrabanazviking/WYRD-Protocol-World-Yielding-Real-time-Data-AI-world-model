#pragma once

#include <AzCore/Component/Component.h>
#include <WyrdForge/WyrdTypes.h>

namespace WyrdForge
{

/**
 * WyrdSystemComponent — O3DE AZ::Component that implements WyrdRequestBus.
 *
 * ═══ STUB — READ BEFORE TRUSTING ═══════════════════════════════════
 * This component is a STUB at its HTTP layer: PostAsync() and
 * HealthCheck() in WyrdSystemComponent.cpp are TODO no-ops, so
 * QueryNPC / PushObservation / PushFact currently deliver NOTHING —
 * they build a request body (via the now-implemented WyrdHelpers) and
 * then drop it. The reflection/lifecycle/bus wiring around them is
 * real code, and the helper algorithms are implemented and host-free
 * tested (WyrdHelpersCore), but no query or push reaches a server
 * through this component until PostAsync is implemented over
 * AzFramework::HttpRequestor inside a real O3DE project. Nothing in
 * this Gem has been compiled: no O3DE exists on the machine that
 * produced E3. See TESTING.md in this Gem for the full picture.
 * ═══════════════════════════════════════════════════════════════════
 *
 * Add this component to your Level entity or a persistent entity in your game.
 *
 * ─── WIRE-UP GUIDE ───────────────────────────────────────────────────────────
 *
 * 1. In your Gem's Module, register WyrdSystemComponent:
 *      m_descriptors.insert(m_descriptors.end(), {
 *          WyrdSystemComponent::CreateDescriptor(),
 *      });
 *
 * 2. In Editor, add WyrdSystemComponent to the Level entity.
 *    Set Host/Port in the component's properties.
 *
 * 3. Query from any component:
 *    WyrdRequestBus::Broadcast(&WyrdRequests::QueryNPC, "sigrid", input);
 *
 * 4. Receive result in your dialogue component:
 *    Connect to WyrdNotificationBus and override OnQueryComplete.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 */
class WyrdSystemComponent
    : public AZ::Component
    , public WyrdRequestBus::Handler
{
public:
    AZ_COMPONENT(WyrdSystemComponent, "{A1B2C3D4-E5F6-7890-ABCD-000000000001}");

    static void Reflect(AZ::ReflectContext* context);
    static void GetProvidedServices(AZ::ComponentDescriptor::DependencyArrayType& provided);
    static void GetIncompatibleServices(AZ::ComponentDescriptor::DependencyArrayType& incompatible);

    // AZ::Component
    void Init()     override;
    void Activate() override;
    void Deactivate() override;

    // WyrdRequestBus::Handler
    void SetConfig(const WyrdConfig& config) override;
    void QueryNPC(const AZStd::string& personaId,
                  const AZStd::string& userInput) override;
    void PushObservation(const AZStd::string& title,
                         const AZStd::string& summary) override;
    void PushFact(const AZStd::string& subjectId,
                  const AZStd::string& key,
                  const AZStd::string& value) override;
    void SyncEntity(const AZStd::string& personaId,
                    const AZStd::vector<WyrdFact>& facts) override;
    void HealthCheck() override;
    const AZStd::string& GetLastError() const override;

private:
    void PostAsync(const AZStd::string& path, const AZStd::string& body,
                   AZStd::function<void(bool, AZStd::string)> onDone);

    WyrdConfig    m_config;
    AZStd::string m_lastError;
};

} // namespace WyrdForge
