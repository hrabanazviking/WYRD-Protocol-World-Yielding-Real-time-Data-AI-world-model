#pragma once

// WyrdClientCore.h — the host-free WYRD client logic for the CryEngine
// integration (E3).
//
// Before E3, WyrdPlugin.cpp's methods were TODO no-ops: QueryAsync,
// PushObservation, PushFact and HealthCheckAsync silently did nothing.
// The logic those methods need — building request bodies, parsing
// responses, fallback/error semantics, completion queueing for the game
// thread — has no CryEngine dependency, so it lives here, implemented
// for real against an injected HTTP transport (IWyrdTransport), and is
// compiled and executed by the honest harness in
// tests/honest/WyrdClientCoreHonestTest.cpp.
//
// What is NOT here, deliberately: the actual HTTP transport. Binding
// libcurl (or CryEngine's HTTP layer) requires a CryEngine installation
// to build and verify; see the STUB notice in WyrdPlugin.cpp. With no
// transport bound, every operation fails honestly: the failure is
// recorded in GetLastError(), and queries complete with the configured
// fallback (silent mode) or a Failure result — never with silence.

#include "IWyrdSystem.h"

#include <cstddef>
#include <functional>
#include <memory>
#include <mutex>
#include <queue>
#include <string>

namespace WyrdForge
{

/// <summary>
/// HTTP transport injected into WyrdClientCore. A CryEngine deployment
/// implements this over libcurl; tests implement it in memory.
/// Post/Get return true when the server answered with a success status;
/// the response body (if any) is written to responseOut.
/// </summary>
struct IWyrdTransport
{
    virtual ~IWyrdTransport() = default;

    virtual bool Post(const std::string& url, const std::string& body,
                      std::string& responseOut) = 0;
    virtual bool Get(const std::string& url, std::string& responseOut) = 0;
};

/// <summary>
/// IWyrdSystem implementation with real logic and a swappable transport.
///
/// Async surface: QueryAsync / HealthCheckAsync perform the transport
/// call, then QUEUE their completion callback instead of invoking it
/// inline. The host drains the queue on its game thread by calling
/// DrainCompletions() once per tick — the pattern the original plugin
/// sketch promised. Push* are fire-and-forget and complete inline.
/// </summary>
class WyrdClientCore final : public IWyrdSystem
{
public:
    /// <summary>Bind (or replace) the HTTP transport. Without one, every
    /// operation fails honestly as described in the file header.</summary>
    void SetTransport(std::shared_ptr<IWyrdTransport> transport);
    bool HasTransport() const;

    // IWyrdSystem
    void SetConfig(const WyrdConfig& config) override;
    const WyrdConfig& GetConfig() const override;
    void QueryAsync(const std::string& personaId,
                    const std::string& userInput,
                    std::function<void(WyrdQueryResult)> onComplete) override;
    void PushObservation(const std::string& title,
                         const std::string& summary) override;
    void PushFact(const std::string& subjectId,
                  const std::string& key,
                  const std::string& value) override;
    void SyncEntity(const std::string& personaId,
                    const std::vector<WyrdFact>& facts) override;
    void HealthCheckAsync(std::function<void(bool)> onResult) override;
    const std::string& GetLastError() const override;

    /// <summary>Run every queued completion; returns how many ran.</summary>
    std::size_t DrainCompletions();
    /// <summary>Completions waiting for DrainCompletions().</summary>
    std::size_t PendingCompletions() const;

private:
    void QueueCompletion(std::function<void()> completion);
    void SetLastError(const std::string& error);
    bool PostEvent(const std::string& body); // shared Push* path

    WyrdConfig  m_config;
    std::string m_lastError;
    std::shared_ptr<IWyrdTransport> m_transport;

    mutable std::mutex m_mutex;
    std::queue<std::function<void()>> m_completions;
};

} // namespace WyrdForge
