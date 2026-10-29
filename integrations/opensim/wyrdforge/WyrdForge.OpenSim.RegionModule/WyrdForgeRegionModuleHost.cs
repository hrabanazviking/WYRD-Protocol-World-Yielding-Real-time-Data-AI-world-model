// WyrdForgeRegionModuleHost.cs — REAL OpenSim region module for WyrdForge (E3).
//
// This class implements OpenSim's IRegionModuleBase contract for real, via
// INonSharedRegionModule. It is the host layer that E3 adds; the plain
// bridge class WyrdForgeRegionModule (in the WyrdForge.OpenSim project)
// remains the host-free, unit-tested core, and this host wraps one bridge
// instance per region and wires it to the region's events:
//
//   Initialise(IConfigSource)  — read [WyrdForge] config, build the bridge
//   AddRegion(Scene)           — subscribe to the region's events
//   RegionLoaded(Scene)        — announce readiness (all modules loaded)
//   RemoveRegion(Scene)        — unsubscribe everything subscribed
//   Close()                    — dispose the bridge client
//
// SHAREABLE vs NON-SHAREABLE — chosen deliberately: NON-SHARED.
// A non-shared module gets one instance per region. That is the right
// shape here because (a) the wrapped bridge owns an HttpClient-backed
// WyrdClient whose lifetime should follow the region's, (b) event
// subscriptions are per-Scene and must be unwound per region, and
// (c) a region removed at runtime must not leave a shared instance
// holding handlers into a dead Scene. The cost (one small bridge object
// per region) is negligible.
//
// EVENT WIRING (in AddRegion):
//   Scene.EventManager.OnMakeRootAgent   → sync the entering avatar to WYRD
//   Scene.EventManager.OnChatFromClient  → dispatch /wyrd chat commands and
//                                          SimChat the bridge's reply back
//
// WHY THIS FILE LIVES IN ITS OWN PROJECT: it references OpenSim.Framework,
// OpenSim.Region.Framework, OpenMetaverse, Nini and Mono.Addins — none of
// which exist outside an OpenSim installation. Isolating the dependency
// here keeps the core WyrdForge.OpenSim project host-free and unit-testable
// (its xUnit suite ProjectReferences only the core project). This is the
// standard OpenSim module structure: build the deployment project against
// your OpenSim bin/ directory (see this folder's README.md), then copy the
// resulting WyrdForge.OpenSim.RegionModule.dll (+ WyrdForge.OpenSim.dll and
// WyrdForge.Client.dll) into that same bin/ directory.
//
// HONESTY: this file was authored on a machine with NO OpenSim installation
// and NO dotnet SDK. It has NOT been compiled and NOT been run in a region.
// It is written against the stable, long-lived OpenSim 0.9.x module API
// (IRegionModuleBase / INonSharedRegionModule have been unchanged in shape
// for many releases), but the first build against a real OpenSim bin/ is a
// genuine verification step, not a formality.

using System;
using System.Threading.Tasks;
using Mono.Addins;
using Nini.Config;
using OpenMetaverse;
using OpenSim.Framework;
using OpenSim.Region.Framework.Interfaces;
using OpenSim.Region.Framework.Scenes;

[assembly: Addin("WyrdForge", "1.0")]

namespace WyrdForge.OpenSim
{
    /// <summary>
    /// OpenSim region module host for WyrdForge. Discovered by OpenSim's
    /// Mono.Addins region-module loader via the Extension attribute below;
    /// enable it in OpenSim.ini with a [WyrdForge] section (see README.md).
    /// </summary>
    [Extension(Path = "/OpenSim/RegionModules", NodeName = "RegionModule",
               Id = "WyrdForgeRegionModule")]
    public sealed class WyrdForgeRegionModuleHost : INonSharedRegionModule
    {
        private WyrdForgeRegionModule _bridge;
        private OpenSimBridgeOptions _options = new OpenSimBridgeOptions();
        private Scene _scene;

        // -----------------------------------------------------------------
        // IRegionModuleBase
        // -----------------------------------------------------------------

        /// <summary>Module name reported to OpenSim's module loader.</summary>
        public string Name => "WyrdForge";

        /// <summary>
        /// INonSharedRegionModule marker: this module replaces no other
        /// module interface, so there is no replaceable interface.
        /// </summary>
        public Type ReplaceableInterface => null;

        /// <summary>
        /// Called once by OpenSim before any region is added. Reads the
        /// [WyrdForge] section of OpenSim.ini and builds the bridge.
        /// </summary>
        public void Initialise(IConfigSource source)
        {
            var options = new OpenSimBridgeOptions();
            IConfig config = source != null ? source.Configs["WyrdForge"] : null;
            if (config != null)
            {
                options = new OpenSimBridgeOptions(
                    Host: config.GetString("Host", options.Host),
                    Port: config.GetInt("Port", options.Port),
                    TimeoutMs: config.GetInt("TimeoutMs", options.TimeoutMs),
                    AutoSyncAvatars: config.GetBoolean(
                        "AutoSyncAvatars", options.AutoSyncAvatars),
                    EnableChatCommands: config.GetBoolean(
                        "EnableChatCommands", options.EnableChatCommands));
            }

            _options = options;
            _bridge = new WyrdForgeRegionModule(options);
            Console.WriteLine(
                "[WyrdForge] Region module initialised (host {0}, port {1}).",
                options.Host, options.Port);
        }

        /// <summary>
        /// Called when this module instance is attached to a region.
        /// Subscribes the region events the bridge serves.
        /// </summary>
        public void AddRegion(Scene scene)
        {
            _scene = scene;
            scene.EventManager.OnMakeRootAgent += OnMakeRootAgent;
            scene.EventManager.OnChatFromClient += OnChatFromClient;
        }

        /// <summary>
        /// Called when all modules have been added to the region and the
        /// region is ready. Nothing further to wire: the bridge is lazy —
        /// it contacts WyrdHTTPServer on first use.
        /// </summary>
        public void RegionLoaded(Scene scene)
        {
            Console.WriteLine(
                "[WyrdForge] Region module loaded for region '{0}'.",
                scene != null ? scene.RegionInfo.RegionName : "?");
        }

        /// <summary>
        /// Called when the region is removed. Unsubscribes exactly what
        /// AddRegion subscribed, so a removed region leaves no handlers.
        /// </summary>
        public void RemoveRegion(Scene scene)
        {
            scene.EventManager.OnMakeRootAgent -= OnMakeRootAgent;
            scene.EventManager.OnChatFromClient -= OnChatFromClient;
            if (_scene == scene)
                _scene = null;
        }

        /// <summary>Called at simulator shutdown. Disposes the bridge.</summary>
        public void Close()
        {
            if (_bridge != null)
            {
                _bridge.Dispose();
                _bridge = null;
            }
        }

        // -----------------------------------------------------------------
        // Region event handlers
        // -----------------------------------------------------------------

        // An avatar became a root agent in this region (entered / teleported
        // in and settled). Sync it to WYRD as entity facts, fire-and-forget:
        // an event handler must never block or throw into the simulator.
        private void OnMakeRootAgent(ScenePresence presence)
        {
            if (_bridge == null || presence == null)
                return;
            if (!_options.AutoSyncAvatars)
                return;

            var record = new AvatarRecord(
                AgentId: presence.UUID.ToString(),
                Name: presence.Firstname + " " + presence.Lastname,
                Region: _scene != null ? _scene.RegionInfo.RegionName : null);
            _ = SyncAvatarSafelyAsync(record);
        }

        private async Task SyncAvatarSafelyAsync(AvatarRecord record)
        {
            try
            {
                await _bridge.SyncAvatarAsync(record).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                Console.WriteLine(
                    "[WyrdForge] Avatar sync failed: {0}", ex.Message);
            }
        }

        // Local chat. The bridge's ChatCommandParser decides whether the
        // message is a /wyrd command at all (it returns null for anything
        // else); a recognised command's reply is said back into the region.
        private void OnChatFromClient(object sender, OSChatMessage chat)
        {
            if (_bridge == null || chat == null || _scene == null)
                return;
            if (!_options.EnableChatCommands)
                return;
            if (chat.Channel != 0)
                return; // WYRD commands are typed in local chat (channel 0)
            _ = DispatchChatSafelyAsync(chat);
        }

        private async Task DispatchChatSafelyAsync(OSChatMessage chat)
        {
            try
            {
                string reply = await _bridge
                    .DispatchChatCommandAsync(chat.Message)
                    .ConfigureAwait(false);
                if (reply != null && _scene != null)
                {
                    _scene.SimChat(
                        reply, ChatTypeEnum.Say, 0, chat.Position,
                        "WyrdForge", UUID.Zero, false);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine(
                    "[WyrdForge] Chat dispatch failed: {0}", ex.Message);
            }
        }
    }
}
