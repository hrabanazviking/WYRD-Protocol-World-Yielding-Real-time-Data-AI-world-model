// WyrdHelpers.cpp — implementations for the AZStd-typed WyrdHelpers API
// declared in WyrdHelpers.h (E3).
//
// Before E3 those declarations had NO implementation anywhere. The
// algorithms are pure string logic, so they are implemented once, in
// standard C++, in WyrdHelpersCore (WyrdHelpersCore.h/.cpp) — which IS
// compiled and executed by tests/honest/WyrdHelpersCoreHonestTest.cpp.
// This file is only a conversion adapter: AZStd::string <-> std::string
// at the boundary, delegation to the core for everything else.
//
// HONESTY: this adapter is NOT compiled on the machine that produced
// E3 — no AZ framework headers exist there. It uses only the most
// basic, stable AZStd::string surface (construction from const char*,
// c_str(), size()). The first build inside an O3DE project is a
// genuine verification step. See TESTING.md.

#include "WyrdHelpers.h"
#include "WyrdHelpersCore.h"

namespace WyrdForge
{

namespace
{

std::string ToStd(const AZStd::string& s)
{
    return std::string(s.c_str(), s.size());
}

AZStd::string ToAz(const std::string& s)
{
    return AZStd::string(s.c_str());
}

} // namespace

AZStd::string WyrdHelpers::NormalizePersonaId(const AZStd::string& name)
{
    return ToAz(WyrdHelpersCore::NormalizePersonaId(ToStd(name)));
}

AZStd::string WyrdHelpers::EscapeJson(const AZStd::string& s)
{
    return ToAz(WyrdHelpersCore::EscapeJson(ToStd(s)));
}

AZStd::string WyrdHelpers::BuildQueryBody(const AZStd::string& personaId,
                                          const AZStd::string& userInput)
{
    return ToAz(WyrdHelpersCore::BuildQueryBody(ToStd(personaId),
                                                ToStd(userInput)));
}

AZStd::string WyrdHelpers::BuildObservationBody(const AZStd::string& title,
                                                const AZStd::string& summary)
{
    return ToAz(WyrdHelpersCore::BuildObservationBody(ToStd(title),
                                                      ToStd(summary)));
}

AZStd::string WyrdHelpers::BuildFactBody(const AZStd::string& subjectId,
                                         const AZStd::string& key,
                                         const AZStd::string& value)
{
    return ToAz(WyrdHelpersCore::BuildFactBody(ToStd(subjectId),
                                               ToStd(key), ToStd(value)));
}

AZStd::string WyrdHelpers::ParseResponse(const AZStd::string& json,
                                         const AZStd::string& fallback)
{
    return ToAz(WyrdHelpersCore::ParseResponse(ToStd(json), ToStd(fallback)));
}

AZStd::vector<WyrdFact> WyrdHelpers::ToFacts(
    const AZStd::string& entityName,
    const AZStd::string& entityId,
    const AZStd::string& levelName,
    const AZStd::vector<AZStd::pair<AZStd::string, AZStd::string>>& customFacts)
{
    std::vector<std::pair<std::string, std::string>> customStd;
    customStd.reserve(customFacts.size());
    for (const auto& kv : customFacts)
        customStd.emplace_back(ToStd(kv.first), ToStd(kv.second));

    const auto factsStd = WyrdHelpersCore::ToFacts(
        ToStd(entityName), ToStd(entityId), ToStd(levelName), customStd);

    AZStd::vector<WyrdFact> facts;
    facts.reserve(factsStd.size());
    for (const auto& f : factsStd)
        facts.push_back(WyrdFact{ ToAz(f.key), ToAz(f.value) });
    return facts;
}

} // namespace WyrdForge
