// WyrdHelpersCoreHonestTest.cpp — HONEST tests for the O3DE helpers'
// logic core (E3).
//
// Before E3, WyrdHelpers.h declared the helpers and no implementation
// existed; the only "tests" were a Python mirror suite testing a copy.
// The algorithms now live in the shipped WyrdHelpersCore.cpp (pure
// standard C++), which this harness compiles and runs directly. The
// AZStd adapter (WyrdHelpers.cpp) and the AZ::Component are NOT covered:
// they need the AZ framework, which does not exist on this machine —
// and the component's HTTP path is a labelled STUB regardless (see
// ../../TESTING.md).
//
// Build & run (from this folder):
//   g++ -std=c++17 -I ../../Code/Source \
//       WyrdHelpersCoreHonestTest.cpp ../../Code/Source/WyrdHelpersCore.cpp \
//       -o /tmp/wyrd_o3de_honest && /tmp/wyrd_o3de_honest

#include "WyrdHelpersCore.h"

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
    CHECK_EQ(WyrdHelpersCore::NormalizePersonaId("Sigrid"), "sigrid");
    CHECK_EQ(WyrdHelpersCore::NormalizePersonaId("Erik Red"), "erik_red");
    CHECK_EQ(WyrdHelpersCore::NormalizePersonaId(""), "");
    CHECK_EQ(WyrdHelpersCore::NormalizePersonaId("npc.archer-1"), "npc_archer_1");
    CHECK_TRUE(WyrdHelpersCore::NormalizePersonaId(std::string(100, 'x')).size() == 64);

    // EscapeJson — quotes, backslashes, control characters.
    CHECK_EQ(WyrdHelpersCore::EscapeJson("a\"b\\c"), "a\\\"b\\\\c");
    CHECK_EQ(WyrdHelpersCore::EscapeJson("a\nb"), "a\\nb");
    CHECK_EQ(WyrdHelpersCore::EscapeJson("plain"), "plain");

    // Body builders — exact shipped JSON shapes.
    CHECK_EQ(WyrdHelpersCore::BuildQueryBody("sigrid", "hello"),
             "{\"persona_id\":\"sigrid\",\"user_input\":\"hello\","
             "\"use_turn_loop\":false}");
    CHECK_EQ(WyrdHelpersCore::BuildQueryBody("sigrid", "   "),
             "{\"persona_id\":\"sigrid\","
             "\"user_input\":\"What is the current world state?\","
             "\"use_turn_loop\":false}");
    CHECK_EQ(WyrdHelpersCore::BuildObservationBody("T", "S"),
             "{\"event_type\":\"observation\",\"payload\":"
             "{\"title\":\"T\",\"summary\":\"S\"}}");
    CHECK_EQ(WyrdHelpersCore::BuildFactBody("sigrid", "name", "Sigrid"),
             "{\"event_type\":\"fact\",\"payload\":"
             "{\"subject_id\":\"sigrid\",\"key\":\"name\",\"value\":\"Sigrid\"}}");

    // ParseResponse — extracts "response", falls back otherwise.
    CHECK_EQ(WyrdHelpersCore::ParseResponse("{\"response\":\"the hall is warm\"}"),
             "the hall is warm");
    CHECK_EQ(WyrdHelpersCore::ParseResponse(""), "The spirits whisper nothing of note.");
    CHECK_EQ(WyrdHelpersCore::ParseResponse("{\"other\":1}", "FB"), "FB");
    CHECK_EQ(WyrdHelpersCore::ParseResponse("{\"response\":\"\"}", "FB"), "FB");

    // ToFacts — skips empty fields, keeps custom pairs with both sides.
    const auto facts = WyrdHelpersCore::ToFacts(
        "Sigrid", "e1", "", {{"mood", "calm"}, {"", "skip"}, {"skip2", ""}});
    CHECK_TRUE(facts.size() == 3);
    CHECK_EQ(facts[0].key, "name");
    CHECK_EQ(facts[0].value, "Sigrid");
    CHECK_EQ(facts[1].key, "entity_id");
    CHECK_EQ(facts[2].key, "mood");

    std::cout << "o3de helpers core honest: " << g_checks << " checks passed\n";
    return 0;
}
