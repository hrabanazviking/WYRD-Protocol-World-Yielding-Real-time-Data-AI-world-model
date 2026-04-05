#pragma once

#include <AzCore/std/string/string.h>
#include <AzCore/std/containers/vector.h>
#include <AzCore/std/utility/pair.h>
#include <AzCore/EBus/EBus.h>
#include <AzCore/RTTI/RTTI.h>

namespace WyrdForge
{

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

struct WyrdFact
{
    AZStd::string key;
    AZStd::string value;
};

struct WyrdConfig
{
    AZStd::string host           = "localhost";
    int           port           = 8765;
    float         timeoutSeconds = 10.0f;
    bool          silentOnError  = true;
    AZStd::string fallbackResponse = "The spirits whisper nothing of note.";

    AZStd::string BaseUrl() const
    {
        return AZStd::string::format("http://%s:%d", host.c_str(), port);
    }
};

struct WyrdQueryResult
{
    bool          success;
    AZStd::string personaId;
    AZStd::string response;
    AZStd::string errorMessage;

    static WyrdQueryResult Ok(AZStd::string pid, AZStd::string resp)
    {
        return WyrdQueryResult{ true, AZStd::move(pid), AZStd::move(resp), {} };
    }

    static WyrdQueryResult Failure(AZStd::string pid, AZStd::string err)
    {
        return WyrdQueryResult{ false, AZStd::move(pid), {}, AZStd::move(err) };
    }
};

// ---------------------------------------------------------------------------
// WyrdRequestBus — O3DE EBus interface
// ---------------------------------------------------------------------------

class WyrdRequests : public AZ::EBusTraits
{
public:
    // Single handler (the WyrdSystemComponent)
    static const AZ::EBusHandlerPolicy HandlerPolicy = AZ::EBusHandlerPolicy::Single;
    static const AZ::EBusBusPolicy     BusPolicy     = AZ::EBusBusPolicy::Single;

    virtual ~WyrdRequests() = default;

    virtual void SetConfig(const WyrdConfig& config) = 0;

    /**
     * Async query — result delivered via WyrdNotificationBus on the main thread.
     *
     * O3DE wiring:
     *   WyrdRequestBus::Broadcast(&WyrdRequests::QueryNPC,
     *       "sigrid_npc", playerInput);
     *   // then in your component: connect to WyrdNotificationBus::OnQueryComplete
     */
    virtual void QueryNPC(const AZStd::string& personaId,
                          const AZStd::string& userInput) = 0;

    virtual void PushObservation(const AZStd::string& title,
                                 const AZStd::string& summary) = 0;

    virtual void PushFact(const AZStd::string& subjectId,
                          const AZStd::string& key,
                          const AZStd::string& value) = 0;

    virtual void SyncEntity(const AZStd::string& personaId,
                             const AZStd::vector<WyrdFact>& facts) = 0;

    virtual void HealthCheck() = 0;

    virtual const AZStd::string& GetLastError() const = 0;
};

using WyrdRequestBus = AZ::EBus<WyrdRequests>;

// ---------------------------------------------------------------------------
// WyrdNotificationBus — results delivered back to interested components
// ---------------------------------------------------------------------------

class WyrdNotifications : public AZ::EBusTraits
{
public:
    static const AZ::EBusHandlerPolicy HandlerPolicy = AZ::EBusHandlerPolicy::Multiple;
    static const AZ::EBusBusPolicy     BusPolicy     = AZ::EBusBusPolicy::Single;

    virtual ~WyrdNotifications() = default;

    virtual void OnQueryComplete(const WyrdQueryResult& result) { (void)result; }
    virtual void OnHealthCheckComplete(bool isHealthy)          { (void)isHealthy; }
};

using WyrdNotificationBus = AZ::EBus<WyrdNotifications>;

} // namespace WyrdForge
