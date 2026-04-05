// WyrdSystemComponent.cpp — O3DE AZ::Component implementation.
//
// HTTP is done via AzFramework::HttpRequestor (O3DE's built-in HTTP system).
//
// ─── AzFramework::HttpRequestor usage ────────────────────────────────────────
//
//   AzFramework::HttpRequestorRequestBus::Broadcast(
//       &AzFramework::HttpRequestorRequests::AddRequestWithHeaders,
//       url,
//       Aws::Http::HttpMethod::HTTP_POST,
//       headers,
//       body,
//       [this, personaId](const Aws::Http::HttpRequest&,
//                         Aws::Http::HttpResponse& response,
//                         AZStd::string body)
//       {
//           auto result = response.GetResponseCode() == Aws::Http::HttpResponseCode::OK
//               ? WyrdQueryResult::Ok(personaId, WyrdHelpers::ParseResponse(body))
//               : WyrdQueryResult::Failure(personaId, "HTTP error");
//           WyrdNotificationBus::Broadcast(
//               &WyrdNotifications::OnQueryComplete, result);
//       },
//       AZ::RHI::Factory::Get().GetAPIUniqueIndex());
//
// ─────────────────────────────────────────────────────────────────────────────

#include "WyrdSystemComponent.h"
#include "WyrdHelpers.h"
#include <AzCore/Serialization/SerializeContext.h>
#include <AzCore/Serialization/EditContext.h>

namespace WyrdForge
{

// ---------------------------------------------------------------------------
// Reflection
// ---------------------------------------------------------------------------

void WyrdSystemComponent::Reflect(AZ::ReflectContext* context)
{
    if (auto* sc = azrtti_cast<AZ::SerializeContext*>(context))
    {
        sc->Class<WyrdSystemComponent, AZ::Component>()
            ->Version(1)
            ->Field("Host",           &WyrdSystemComponent::m_config)
            ;

        if (AZ::EditContext* ec = sc->GetEditContext())
        {
            ec->Class<WyrdSystemComponent>("WyrdForge System",
                "WYRD Protocol world model bridge")
                ->ClassElement(AZ::Edit::ClassElements::EditorData, "")
                    ->Attribute(AZ::Edit::Attributes::Category, "AI")
                    ->Attribute(AZ::Edit::Attributes::AppearsInAddComponentMenu,
                                AZ_CRC_CE("System"))
                ;
        }
    }
}

void WyrdSystemComponent::GetProvidedServices(
    AZ::ComponentDescriptor::DependencyArrayType& provided)
{
    provided.push_back(AZ_CRC_CE("WyrdForgeService"));
}

void WyrdSystemComponent::GetIncompatibleServices(
    AZ::ComponentDescriptor::DependencyArrayType& incompatible)
{
    incompatible.push_back(AZ_CRC_CE("WyrdForgeService"));
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

void WyrdSystemComponent::Init() {}

void WyrdSystemComponent::Activate()
{
    WyrdRequestBus::Handler::BusConnect();
    AZ_TracePrintf("WyrdForge", "[WyrdForge] WyrdSystemComponent activated. %s\n",
                   m_config.BaseUrl().c_str());
}

void WyrdSystemComponent::Deactivate()
{
    WyrdRequestBus::Handler::BusDisconnect();
}

// ---------------------------------------------------------------------------
// WyrdRequestBus::Handler
// ---------------------------------------------------------------------------

void WyrdSystemComponent::SetConfig(const WyrdConfig& config) { m_config = config; }

void WyrdSystemComponent::QueryNPC(const AZStd::string& personaId,
                                    const AZStd::string& userInput)
{
    AZStd::string body = WyrdHelpers::BuildQueryBody(personaId, userInput);
    PostAsync("/query", body, [this, personaId](bool ok, AZStd::string responseBody)
    {
        WyrdQueryResult result = ok
            ? WyrdQueryResult::Ok(personaId,
                  WyrdHelpers::ParseResponse(responseBody, m_config.fallbackResponse))
            : WyrdQueryResult::Failure(personaId, responseBody);

        WyrdNotificationBus::Broadcast(&WyrdNotifications::OnQueryComplete, result);
    });
}

void WyrdSystemComponent::PushObservation(const AZStd::string& title,
                                           const AZStd::string& summary)
{
    PostAsync("/event", WyrdHelpers::BuildObservationBody(title, summary),
        [this](bool ok, AZStd::string err){ if (!ok) m_lastError = err; });
}

void WyrdSystemComponent::PushFact(const AZStd::string& subjectId,
                                    const AZStd::string& key,
                                    const AZStd::string& value)
{
    PostAsync("/event", WyrdHelpers::BuildFactBody(subjectId, key, value),
        [this](bool ok, AZStd::string err){ if (!ok) m_lastError = err; });
}

void WyrdSystemComponent::SyncEntity(const AZStd::string& personaId,
                                      const AZStd::vector<WyrdFact>& facts)
{
    for (const auto& f : facts)
        PushFact(personaId, f.key, f.value);
}

void WyrdSystemComponent::HealthCheck()
{
    // TODO: AzFramework::HttpRequestorRequestBus GET /health
    // → WyrdNotificationBus::Broadcast(&WyrdNotifications::OnHealthCheckComplete, ok)
}

const AZStd::string& WyrdSystemComponent::GetLastError() const { return m_lastError; }

// ---------------------------------------------------------------------------
// Internal
// ---------------------------------------------------------------------------

void WyrdSystemComponent::PostAsync(const AZStd::string& path,
                                     const AZStd::string& body,
                                     AZStd::function<void(bool, AZStd::string)> onDone)
{
    // TODO: AzFramework::HttpRequestorRequestBus POST
    // Full impl follows the pattern documented at top of file.
    (void)path; (void)body; (void)onDone;
}

} // namespace WyrdForge
