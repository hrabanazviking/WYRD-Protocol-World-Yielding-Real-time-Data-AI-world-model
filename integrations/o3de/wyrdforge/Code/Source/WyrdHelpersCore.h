#pragma once

// WyrdHelpersCore.h — the host-free logic core for the O3DE Gem's
// helpers (E3).
//
// Before E3, WyrdHelpers.h declared seven helper methods and NO
// implementation existed anywhere — the Gem's helpers were declarations
// without bodies. The algorithms themselves (persona normalisation,
// JSON escaping, request-body building, response parsing, fact
// assembly) are pure string logic with no AZ dependency, so they are
// implemented here for real, in standard C++, and are compiled and
// executed by the honest harness in tests/honest/.
//
// WyrdHelpers.cpp then implements the shipped AZStd-typed WyrdHelpers
// API as a thin conversion adapter over this core. The adapter itself
// is NOT compiled on the machine that produced E3 (no AZ framework
// headers exist there) — see WyrdHelpers.cpp's header and TESTING.md.

#include <string>
#include <utility>
#include <vector>

namespace WyrdForge
{

/// <summary>std::string twin of WyrdFact (the AZStd one lives in WyrdTypes.h).</summary>
struct WyrdFactStd
{
    std::string key;
    std::string value;
};

/// <summary>
/// Pure standard-C++ implementations of the WyrdHelpers algorithms.
/// WyrdHelpers (AZStd API) delegates to these; the honest harness tests
/// these directly.
/// </summary>
class WyrdHelpersCore
{
public:
    WyrdHelpersCore() = delete;

    static std::string NormalizePersonaId(const std::string& name);
    static std::string EscapeJson(const std::string& s);
    static std::string BuildQueryBody(const std::string& personaId,
                                      const std::string& userInput);
    static std::string BuildObservationBody(const std::string& title,
                                            const std::string& summary);
    static std::string BuildFactBody(const std::string& subjectId,
                                     const std::string& key,
                                     const std::string& value);
    static std::string ParseResponse(
        const std::string& json,
        const std::string& fallback = "The spirits whisper nothing of note.");

    static std::vector<WyrdFactStd> ToFacts(
        const std::string& entityName,
        const std::string& entityId,
        const std::string& levelName,
        const std::vector<std::pair<std::string, std::string>>& customFacts);
};

} // namespace WyrdForge
