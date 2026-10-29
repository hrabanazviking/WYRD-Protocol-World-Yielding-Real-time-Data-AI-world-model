// WyrdClientCoreHonestTest.cpp — HONEST tests for the CryEngine client
// core (E3).
//
// Compiled together with the SHIPPED WyrdClientCore.cpp + WyrdHelpers.cpp
// and run natively. Before E3 the plugin methods were TODO no-ops; the
// logic now lives in WyrdClientCore behind an injected IWyrdTransport,
// so this harness executes the shipped logic itself with an in-memory
// fake transport. What it does NOT prove: anything about libcurl or
// CryEngine — no transport is bound in the shipped plugin (STUB, see
// ../../Code/WyrdPlugin/WyrdPlugin.cpp and ../../TESTING.md).
//
// Build & run (from this folder):
//   g++ -std=c++17 -I ../../Code/WyrdPlugin \
//       WyrdClientCoreHonestTest.cpp ../../Code/WyrdPlugin/WyrdClientCore.cpp \
//       ../../Code/WyrdPlugin/WyrdHelpers.cpp ../../Code/WyrdPlugin/WyrdPlugin.cpp \
//       -o /tmp/wyrd_cryengine_core_honest && /tmp/wyrd_cryengine_core_honest
// (WyrdPlugin.cpp is in the build to prove the shipped plugin shell
// compiles host-free; it defines no entry point.)

#include "WyrdClientCore.h"
#include "WyrdHelpers.h"

#include <iostream>
#include <memory>
#include <string>
#include <utility>
#include <vector>

static int g_checks = 0;

#define CHECK_TRUE(cond)                                                  \
    do {                                                                  \
        ++g_checks;                                                       \
        if (!(cond)) {                                                    \
            std::cerr << "FAIL line " << __LINE__ << ": " #cond "\n";     \
            return 1;                                                     \
        }                                                                 \
    } while (0)

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

namespace
{

struct FakeTransport final : WyrdForge::IWyrdTransport
{
    bool postOk = true;
    bool getOk = true;
    std::string postResponse = "{\"response\":\"the hall is warm\"}";
    std::vector<std::pair<std::string, std::string>> posts; // (url, body)
    std::vector<std::string> gets;

    bool Post(const std::string& url, const std::string& body,
              std::string& responseOut) override
    {
        posts.emplace_back(url, body);
        responseOut = postResponse;
        return postOk;
    }

    bool Get(const std::string& url, std::string& responseOut) override
    {
        gets.push_back(url);
        responseOut = "{}";
        return getOk;
    }
};

WyrdForge::WyrdConfig Config(bool silent)
{
    WyrdForge::WyrdConfig cfg;
    cfg.host = "example-host";
    cfg.port = 9999;
    cfg.silentOnError = silent;
    cfg.fallbackResponse = "FB";
    return cfg;
}

} // namespace

int main()
{
    using namespace WyrdForge;

    // -- No transport: honest failure, queued completion -------------------
    {
        WyrdClientCore core;
        core.SetConfig(Config(false));
        CHECK_TRUE(!core.HasTransport());

        bool called = false;
        WyrdQueryResult got;
        core.QueryAsync("sigrid", "hello",
                        [&](WyrdQueryResult r) { called = true; got = r; });
        CHECK_TRUE(!called);                       // queued, not inline
        CHECK_TRUE(core.PendingCompletions() == 1);
        CHECK_TRUE(core.DrainCompletions() == 1);
        CHECK_TRUE(called);
        CHECK_TRUE(!got.success);
        CHECK_TRUE(!core.GetLastError().empty());
        CHECK_TRUE(core.DrainCompletions() == 0);  // empty drain is a no-op
    }

    // -- No transport + silent mode: fallback text, still an error recorded -
    {
        WyrdClientCore core;
        core.SetConfig(Config(true));
        WyrdQueryResult got;
        core.QueryAsync("sigrid", "hello",
                        [&](WyrdQueryResult r) { got = r; });
        core.DrainCompletions();
        CHECK_TRUE(got.success);
        CHECK_EQ(got.response, "FB");
        CHECK_TRUE(!core.GetLastError().empty());
    }

    // -- Bound transport, success: real request shape + parsed response -----
    {
        auto fake = std::make_shared<FakeTransport>();
        WyrdClientCore core;
        core.SetConfig(Config(false));
        core.SetTransport(fake);
        CHECK_TRUE(core.HasTransport());
        CHECK_EQ(core.GetConfig().host, "example-host");

        WyrdQueryResult got;
        core.QueryAsync("sigrid", "hello",
                        [&](WyrdQueryResult r) { got = r; });
        core.DrainCompletions();
        CHECK_TRUE(got.success);
        CHECK_EQ(got.response, "the hall is warm");
        CHECK_TRUE(fake->posts.size() == 1);
        CHECK_EQ(fake->posts[0].first, "http://example-host:9999/query");
        CHECK_EQ(fake->posts[0].second,
                 WyrdHelpers::BuildQueryBody("sigrid", "hello"));
    }

    // -- Bound transport, HTTP failure: silent vs non-silent ----------------
    {
        auto fake = std::make_shared<FakeTransport>();
        fake->postOk = false;

        WyrdClientCore loud;
        loud.SetConfig(Config(false));
        loud.SetTransport(fake);
        WyrdQueryResult gotLoud;
        loud.QueryAsync("sigrid", "hello",
                        [&](WyrdQueryResult r) { gotLoud = r; });
        loud.DrainCompletions();
        CHECK_TRUE(!gotLoud.success);

        WyrdClientCore quiet;
        quiet.SetConfig(Config(true));
        quiet.SetTransport(fake);
        WyrdQueryResult gotQuiet;
        quiet.QueryAsync("sigrid", "hello",
                         [&](WyrdQueryResult r) { gotQuiet = r; });
        quiet.DrainCompletions();
        CHECK_TRUE(gotQuiet.success);
        CHECK_EQ(gotQuiet.response, "FB");
    }

    // -- Pushes: exact bodies to /event; SyncEntity fans out ----------------
    {
        auto fake = std::make_shared<FakeTransport>();
        WyrdClientCore core;
        core.SetConfig(Config(false));
        core.SetTransport(fake);

        core.PushFact("sigrid", "name", "Sigrid");
        core.PushObservation("T", "S");
        CHECK_TRUE(fake->posts.size() == 2);
        CHECK_EQ(fake->posts[0].first, "http://example-host:9999/event");
        CHECK_EQ(fake->posts[0].second,
                 WyrdHelpers::BuildFactBody("sigrid", "name", "Sigrid"));
        CHECK_EQ(fake->posts[1].second,
                 WyrdHelpers::BuildObservationBody("T", "S"));

        core.SyncEntity("sigrid", {{"name", "Sigrid"}, {"role", "seer"}});
        CHECK_TRUE(fake->posts.size() == 4);
    }

    // -- Push with no transport records the error instead of staying silent -
    {
        WyrdClientCore core;
        core.SetConfig(Config(false));
        core.PushFact("sigrid", "name", "Sigrid");
        CHECK_TRUE(!core.GetLastError().empty());
    }

    // -- Health: queued bool, true and false --------------------------------
    {
        auto fake = std::make_shared<FakeTransport>();
        WyrdClientCore core;
        core.SetConfig(Config(false));
        core.SetTransport(fake);

        bool health = false;
        core.HealthCheckAsync([&](bool ok) { health = ok; });
        CHECK_TRUE(core.DrainCompletions() == 1);
        CHECK_TRUE(health);
        CHECK_EQ(fake->gets[0], "http://example-host:9999/health");

        fake->getOk = false;
        health = true;
        core.HealthCheckAsync([&](bool ok) { health = ok; });
        core.DrainCompletions();
        CHECK_TRUE(!health);
    }

    std::cout << "cryengine core honest: " << g_checks << " checks passed\n";
    return 0;
}
