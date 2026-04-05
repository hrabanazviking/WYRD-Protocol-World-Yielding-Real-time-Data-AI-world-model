// WyrdHelpers.cpp — Pure helper implementations for WyrdForge CryEngine plugin.
// No CryEngine or libcurl dependency.

#include "WyrdHelpers.h"
#include <algorithm>
#include <cctype>
#include <sstream>
#include <iomanip>
#include <regex>

namespace WyrdForge
{

// ---------------------------------------------------------------------------
// NormalizePersonaId
// ---------------------------------------------------------------------------

std::string WyrdHelpers::NormalizePersonaId(const std::string& name)
{
    if (name.empty()) return {};

    std::string lower(name.size(), '\0');
    std::transform(name.begin(), name.end(), lower.begin(),
                   [](unsigned char c){ return std::tolower(c); });

    // Replace non-alphanumeric (except _) with _; collapse consecutive _
    std::string out;
    out.reserve(lower.size());
    bool lastWasUnderscore = false;

    for (char c : lower)
    {
        bool isAlnum = std::isalnum((unsigned char)c) || c == '_';
        if (isAlnum)
        {
            out += c;
            lastWasUnderscore = (c == '_');
        }
        else if (!lastWasUnderscore)
        {
            out += '_';
            lastWasUnderscore = true;
        }
    }

    // Strip leading underscores
    auto start = out.find_first_not_of('_');
    if (start == std::string::npos) return {};
    out = out.substr(start);

    // Strip trailing underscores
    auto end = out.find_last_not_of('_');
    if (end != std::string::npos) out = out.substr(0, end + 1);

    // Truncate at 64
    if (out.size() > 64) out = out.substr(0, 64);

    return out;
}

// ---------------------------------------------------------------------------
// EscapeJson
// ---------------------------------------------------------------------------

std::string WyrdHelpers::EscapeJson(const std::string& s)
{
    std::string out;
    out.reserve(s.size() + 8);

    for (unsigned char c : s)
    {
        switch (c)
        {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b";  break;
            case '\f': out += "\\f";  break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (c < 0x20)
                {
                    std::ostringstream oss;
                    oss << "\\u" << std::hex << std::setw(4)
                        << std::setfill('0') << (int)c;
                    out += oss.str();
                }
                else out += (char)c;
                break;
        }
    }
    return out;
}

// ---------------------------------------------------------------------------
// JSON body builders
// ---------------------------------------------------------------------------

std::string WyrdHelpers::BuildQueryBody(const std::string& personaId,
                                         const std::string& userInput)
{
    std::string input = userInput;
    // Trim and check blank
    input.erase(0, input.find_first_not_of(" \t\r\n"));
    input.erase(input.find_last_not_of(" \t\r\n") + 1);
    if (input.empty()) input = "What is the current world state?";

    return "{\"persona_id\":\"" + EscapeJson(personaId)
         + "\",\"user_input\":\""  + EscapeJson(input)
         + "\",\"use_turn_loop\":false}";
}

std::string WyrdHelpers::BuildObservationBody(const std::string& title,
                                               const std::string& summary)
{
    return "{\"event_type\":\"observation\","
           "\"payload\":{\"title\":\""   + EscapeJson(title)
         + "\",\"summary\":\""           + EscapeJson(summary) + "\"}}";
}

std::string WyrdHelpers::BuildFactBody(const std::string& subjectId,
                                        const std::string& key,
                                        const std::string& value)
{
    return "{\"event_type\":\"fact\","
           "\"payload\":{\"subject_id\":\"" + EscapeJson(subjectId)
         + "\",\"key\":\""                  + EscapeJson(key)
         + "\",\"value\":\""               + EscapeJson(value) + "\"}}";
}

// ---------------------------------------------------------------------------
// ParseResponse
// ---------------------------------------------------------------------------

std::string WyrdHelpers::ParseResponse(const std::string& json,
                                        const std::string& fallback)
{
    if (json.empty()) return fallback;

    auto keyPos = json.find("\"response\"");
    if (keyPos == std::string::npos) return fallback;

    auto colon = json.find(':', keyPos);
    if (colon == std::string::npos) return fallback;

    auto q1 = json.find('"', colon + 1);
    if (q1 == std::string::npos) return fallback;
    q1++; // skip opening quote

    // Find closing unescaped quote
    size_t q2 = q1;
    while (q2 < json.size())
    {
        if (json[q2] == '"' && (q2 == 0 || json[q2 - 1] != '\\')) break;
        q2++;
    }
    if (q2 >= json.size()) return fallback;

    std::string value = json.substr(q1, q2 - q1);
    if (value.empty()) return fallback;
    return value;
}

// ---------------------------------------------------------------------------
// ToFacts
// ---------------------------------------------------------------------------

std::vector<WyrdFact> WyrdHelpers::ToFacts(
    const std::string& entityName,
    const std::string& entityId,
    const std::string& levelName,
    const std::vector<std::pair<std::string, std::string>>& customFacts)
{
    std::vector<WyrdFact> facts;

    if (!entityName.empty()) facts.push_back({"name",      entityName});
    if (!entityId.empty())   facts.push_back({"entity_id", entityId});
    if (!levelName.empty())  facts.push_back({"level",     levelName});

    for (const auto& [k, v] : customFacts)
        if (!k.empty() && !v.empty())
            facts.push_back({k, v});

    return facts;
}

} // namespace WyrdForge
