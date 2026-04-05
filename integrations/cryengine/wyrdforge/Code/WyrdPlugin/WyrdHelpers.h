#pragma once

#include <string>
#include <vector>
#include "IWyrdSystem.h"

namespace WyrdForge
{

/**
 * WyrdHelpers — pure static helper functions.
 * No CryEngine or libcurl dependency — fully testable in isolation.
 */
class WyrdHelpers
{
public:
    WyrdHelpers() = delete;

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

    static std::vector<WyrdFact> ToFacts(
        const std::string& entityName,
        const std::string& entityId,
        const std::string& levelName,
        const std::vector<std::pair<std::string, std::string>>& customFacts);
};

} // namespace WyrdForge
