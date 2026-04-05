#pragma once

#include <AzCore/std/string/string.h>
#include <AzCore/std/containers/vector.h>
#include <WyrdForge/WyrdTypes.h>

namespace WyrdForge
{

/**
 * WyrdHelpers — pure static helpers for WyrdForge O3DE Gem.
 * No AzFramework or engine runtime dependency — fully testable.
 */
class WyrdHelpers
{
public:
    WyrdHelpers() = delete;

    static AZStd::string NormalizePersonaId(const AZStd::string& name);
    static AZStd::string EscapeJson(const AZStd::string& s);
    static AZStd::string BuildQueryBody(const AZStd::string& personaId,
                                         const AZStd::string& userInput);
    static AZStd::string BuildObservationBody(const AZStd::string& title,
                                               const AZStd::string& summary);
    static AZStd::string BuildFactBody(const AZStd::string& subjectId,
                                        const AZStd::string& key,
                                        const AZStd::string& value);
    static AZStd::string ParseResponse(
        const AZStd::string& json,
        const AZStd::string& fallback = "The spirits whisper nothing of note.");

    static AZStd::vector<WyrdFact> ToFacts(
        const AZStd::string& entityName,
        const AZStd::string& entityId,
        const AZStd::string& levelName,
        const AZStd::vector<AZStd::pair<AZStd::string, AZStd::string>>& customFacts);
};

} // namespace WyrdForge
