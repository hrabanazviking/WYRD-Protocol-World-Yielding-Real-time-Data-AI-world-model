// WyrdClientCore.cpp — host-free client logic for the CryEngine
// integration (E3). Pure standard C++ on top of WyrdHelpers; see the
// header for what is implemented here and what remains a stub (the
// libcurl transport binding in WyrdPlugin.cpp).

#include "WyrdClientCore.h"
#include "WyrdHelpers.h"

namespace WyrdForge
{

namespace
{
const char* const kNoTransport =
    "WyrdForge: no HTTP transport bound (the CryEngine libcurl "
    "transport is a stub — see WyrdPlugin.cpp).";
const char* const kHttpFailed =
    "WyrdForge: HTTP request to WyrdHTTPServer failed.";
} // namespace

// ---------------------------------------------------------------------------
// Transport / config / error state
// ---------------------------------------------------------------------------

void WyrdClientCore::SetTransport(std::shared_ptr<IWyrdTransport> transport)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    m_transport = std::move(transport);
}

bool WyrdClientCore::HasTransport() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return static_cast<bool>(m_transport);
}

void WyrdClientCore::SetConfig(const WyrdConfig& config) { m_config = config; }

const WyrdConfig& WyrdClientCore::GetConfig() const { return m_config; }

const std::string& WyrdClientCore::GetLastError() const { return m_lastError; }

void WyrdClientCore::SetLastError(const std::string& error)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    m_lastError = error;
}

// ---------------------------------------------------------------------------
// Completion queue (drained by the host on its game thread)
// ---------------------------------------------------------------------------

void WyrdClientCore::QueueCompletion(std::function<void()> completion)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    m_completions.push(std::move(completion));
}

std::size_t WyrdClientCore::PendingCompletions() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_completions.size();
}

std::size_t WyrdClientCore::DrainCompletions()
{
    std::queue<std::function<void()>> ready;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        ready.swap(m_completions);
    }
    std::size_t ran = 0;
    while (!ready.empty())
    {
        ready.front()();
        ready.pop();
        ++ran;
    }
    return ran;
}

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

void WyrdClientCore::QueryAsync(const std::string& personaId,
                                const std::string& userInput,
                                std::function<void(WyrdQueryResult)> onComplete)
{
    WyrdQueryResult result;
    std::shared_ptr<IWyrdTransport> transport;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        transport = m_transport;
    }

    if (!transport)
    {
        SetLastError(kNoTransport);
        result = m_config.silentOnError
            ? WyrdQueryResult::Ok(personaId, m_config.fallbackResponse)
            : WyrdQueryResult::Failure(personaId, kNoTransport);
    }
    else
    {
        std::string responseBody;
        const bool ok = transport->Post(
            m_config.baseUrl() + "/query",
            WyrdHelpers::BuildQueryBody(personaId, userInput),
            responseBody);
        if (ok)
        {
            result = WyrdQueryResult::Ok(
                personaId,
                WyrdHelpers::ParseResponse(responseBody,
                                           m_config.fallbackResponse));
        }
        else
        {
            SetLastError(kHttpFailed);
            result = m_config.silentOnError
                ? WyrdQueryResult::Ok(personaId, m_config.fallbackResponse)
                : WyrdQueryResult::Failure(personaId, kHttpFailed);
        }
    }

    if (onComplete)
        QueueCompletion([onComplete, result]() { onComplete(result); });
}

// ---------------------------------------------------------------------------
// Fire-and-forget pushes
// ---------------------------------------------------------------------------

bool WyrdClientCore::PostEvent(const std::string& body)
{
    std::shared_ptr<IWyrdTransport> transport;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        transport = m_transport;
    }
    if (!transport)
    {
        SetLastError(kNoTransport);
        return false;
    }
    std::string responseBody;
    if (!transport->Post(m_config.baseUrl() + "/event", body, responseBody))
    {
        SetLastError(kHttpFailed);
        return false;
    }
    return true;
}

void WyrdClientCore::PushObservation(const std::string& title,
                                     const std::string& summary)
{
    PostEvent(WyrdHelpers::BuildObservationBody(title, summary));
}

void WyrdClientCore::PushFact(const std::string& subjectId,
                              const std::string& key,
                              const std::string& value)
{
    PostEvent(WyrdHelpers::BuildFactBody(subjectId, key, value));
}

void WyrdClientCore::SyncEntity(const std::string& personaId,
                                const std::vector<WyrdFact>& facts)
{
    for (const auto& f : facts)
        PushFact(personaId, f.key, f.value);
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

void WyrdClientCore::HealthCheckAsync(std::function<void(bool)> onResult)
{
    bool healthy = false;
    std::shared_ptr<IWyrdTransport> transport;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        transport = m_transport;
    }

    if (!transport)
    {
        SetLastError(kNoTransport);
    }
    else
    {
        std::string responseBody;
        healthy = transport->Get(m_config.baseUrl() + "/health", responseBody);
        if (!healthy)
            SetLastError(kHttpFailed);
    }

    if (onResult)
        QueueCompletion([onResult, healthy]() { onResult(healthy); });
}

} // namespace WyrdForge
