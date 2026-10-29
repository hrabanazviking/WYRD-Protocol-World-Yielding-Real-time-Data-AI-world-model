// WyrdHelpersHonestTest.cpp — HONEST tests for the CryEngine helpers (E1).
//
// This file is compiled together with the SHIPPED
// ../../Code/WyrdPlugin/WyrdHelpers.cpp and run natively. It tests
// the shipped C++ itself — unlike ../test_wyrdforge.py, which is a
// Python mirror test that re-implements the logic in Python and
// tests the copy (see ../../TESTING.md).
//
// WyrdHelpers is pure standard C++ (its header states: no CryEngine
// or libcurl dependency), so g++ alone can execute it. The plugin
// glue (WyrdPlugin.cpp) still needs CryEngine and is NOT covered.
//
// Build & run:
//   g++ -std=c++17 -I ../../Code/WyrdPlugin \
//       WyrdHelpersHonestTest.cpp ../../Code/WyrdPlugin/WyrdHelpers.cpp \
//       -o /tmp/wyrd_cryengine_honest && /tmp/wyrd_cryengine_honest

#include "WyrdHelpers.h"

#include <cassert>
#include <iostream>
#include <string>

static int g_checks = 0;

#define CHECK_EQ(actual, expected)                                        \
    do {                                                                  \
        ++g_checks;                                                       \
        const std::string a_ = (actual);                                  \
        const std::string e_ = (expected);                                \
        if (a_ != e_) {                                                   \
            std::cerr << "FAIL line " << __LINE__ << ": got \"" << a_     \
                      << "\" expected \"" << e_ << "\"\n";                \
            return 1;                                                     \
        }                                                                 \
    } while (0)

#define CHECK_TRUE(cond)                                                  \
    do {                                                                  \
        ++g_checks;                                                       \
        if (!(cond)) {                                                    \
            std::cerr << "FAIL line " << __LINE__ << ": " #cond "\n";     \
            return 1;                                                     \
        }                                                                 \
    } while (0)

int main() {
    using namespace WyrdForge;

    // NormalizePersonaId — the shipped algorithm.
    CHECK_EQ(WyrdHelpers::NormalizePersonaId("Sigrid"), "sigrid");
    CHECK_EQ(WyrdHelpers::NormalizePersonaId("Erik Red"), "erik_red");
    CHECK_EQ(WyrdHelpers::NormalizePersonaId(""), "");
    CHECK_EQ(WyrdHelpers::NormalizePersonaId("npc.archer-1"), "npc_archer_1");
    CHECK_TRUE(WyrdHelpers::NormalizePersonaId(std::string(100, 'x')).size() == 64);

    // EscapeJson — quotes, backslashes, control characters.
    CHECK_EQ(WyrdHelpers::EscapeJson("a\"b\\c"), "a\\\"b\\\\c");
    CHECK_EQ(WyrdHelpers::EscapeJson("a\nb"), "a\\nb");
    CHECK_EQ(WyrdHelpers::EscapeJson("plain"), "plain");

    // Body builders — exact shipped JSON shapes.
    CHECK_EQ(WyrdHelpers::BuildQueryBody("sigrid", "hello"),
             "{\"persona_id\":\"sigrid\",\"user_input\":\"hello\","
             "\"use_turn_loop\":false}");
    CHECK_EQ(WyrdHelpers::BuildQueryBody("sigrid", "   "),
             "{\"persona_id\":\"sigrid\","
             "\"user_input\":\"What is the current world state?\","
             "\"use_turn_loop\":false}");
    CHECK_EQ(WyrdHelpers::BuildObservationBody("T", "S"),
             "{\"event_type\":\"observation\",\"payload\":"
             "{\"title\":\"T\",\"summary\":\"S\"}}");
    CHECK_EQ(WyrdHelpers::BuildFactBody("sigrid", "name", "Sigrid"),
             "{\"event_type\":\"fact\",\"payload\":"
             "{\"subject_id\":\"sigrid\",\"key\":\"name\",\"value\":\"Sigrid\"}}");

    // ParseResponse — extracts "response", falls back otherwise.
    CHECK_EQ(WyrdHelpers::ParseResponse("{\"response\":\"the hall is warm\"}"),
             "the hall is warm");
    CHECK_EQ(WyrdHelpers::ParseResponse(""), "The spirits whisper nothing of note.");
    CHECK_EQ(WyrdHelpers::ParseResponse("{\"other\":1}", "FB"), "FB");
    CHECK_EQ(WyrdHelpers::ParseResponse("{\"response\":\"\"}", "FB"), "FB");

    // ToFacts — skips empty fields, keeps custom pairs with both sides.
    const auto facts = WyrdHelpers::ToFacts(
        "Sigrid", "e1", "", {{"mood", "calm"}, {"", "skip"}, {"skip2", ""}});
    CHECK_TRUE(facts.size() == 3);
    CHECK_EQ(facts[0].key, "name");
    CHECK_EQ(facts[0].value, "Sigrid");
    CHECK_EQ(facts[1].key, "entity_id");
    CHECK_EQ(facts[2].key, "mood");

    std::cout << "cryengine honest: " << g_checks << " checks passed\n";
    return 0;
}
