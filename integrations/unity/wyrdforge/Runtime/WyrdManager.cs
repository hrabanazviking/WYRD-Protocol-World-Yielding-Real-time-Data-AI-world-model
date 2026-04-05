using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace WyrdForge.Unity
{
    /// <summary>
    /// WyrdManager — Singleton entry point for the WyrdForge Unity integration.
    ///
    /// Place this on a persistent GameObject (DontDestroyOnLoad).
    /// All WyrdNPC components auto-register with this manager on Start().
    ///
    /// ─── WIRE-UP GUIDE ───────────────────────────────────────────────────────
    ///
    /// 1. Create an empty GameObject named "WyrdManager".
    /// 2. Attach this script and configure Options (host, port, timeout).
    /// 3. Call DontDestroyOnLoad(gameObject) in Awake() for scene persistence.
    /// 4. In NPC scripts:
    ///      StartCoroutine(WyrdManager.Instance.QueryCoroutine(
    ///          "sigrid_npc", playerInput, reply => npcText.text = reply));
    ///
    /// 5. For editor tooling (optional), add a custom Editor window that calls
    ///    WyrdManager.Instance.HealthCheck() and displays entity registry state.
    ///
    /// ─── UNITY COROUTINE PATTERN ─────────────────────────────────────────────
    ///
    ///   // Using UnityWebRequest (recommended for build compatibility):
    ///   IEnumerator QueryCoroutine(string personaId, string input, Action&lt;string&gt; onComplete)
    ///   {
    ///       var req = new UnityWebRequest(Options.BaseUrl() + "/query", "POST");
    ///       var body = WyrdEntityData.BuildQueryBody(personaId, input);
    ///       req.uploadHandler   = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
    ///       req.downloadHandler = new DownloadHandlerBuffer();
    ///       req.SetRequestHeader("Content-Type", "application/json");
    ///       yield return req.SendWebRequest();
    ///       if (req.result == UnityWebRequest.Result.Success)
    ///           onComplete(WyrdEntityData.ParseResponse(req.downloadHandler.text));
    ///       else
    ///           onComplete(Options.FallbackResponse);
    ///   }
    ///
    /// ─────────────────────────────────────────────────────────────────────────
    /// </summary>
    public sealed class WyrdManager
    {
        // -------------------------------------------------------------------------
        // Singleton
        // -------------------------------------------------------------------------

        private static WyrdManager _instance;

        /// <summary>Singleton instance. Created lazily with default options.</summary>
        public static WyrdManager Instance
            => _instance ??= new WyrdManager(new WyrdUnityOptions());

        // -------------------------------------------------------------------------
        // State
        // -------------------------------------------------------------------------

        public WyrdUnityOptions Options { get; private set; }

        private readonly Dictionary<string, WyrdEntityData> _entities
            = new(StringComparer.Ordinal);

        private readonly object _lock = new();

        private readonly HttpClient _http;

        private string _lastError;

        // -------------------------------------------------------------------------
        // Construction
        // -------------------------------------------------------------------------

        public WyrdManager(WyrdUnityOptions options)
        {
            Options = options ?? throw new ArgumentNullException(nameof(options));
            _http   = new HttpClient
            {
                Timeout = TimeSpan.FromSeconds(options.TimeoutSeconds)
            };
        }

        public static void SetInstance(WyrdManager manager)
            => _instance = manager;

        // -------------------------------------------------------------------------
        // Entity registry
        // -------------------------------------------------------------------------

        /// <summary>
        /// Register a WYRD entity. Call from WyrdNPC.Start().
        /// Throws ArgumentException if EntityId is null or empty.
        /// </summary>
        public void RegisterEntity(WyrdEntityData entity)
        {
            if (entity == null) throw new ArgumentNullException(nameof(entity));
            var id = string.IsNullOrWhiteSpace(entity.EntityId)
                ? WyrdEntityData.NormalizePersonaId(entity.Name)
                : entity.EntityId;
            if (string.IsNullOrEmpty(id))
                throw new ArgumentException("WyrdEntityData must have a non-empty EntityId or Name.", nameof(entity));

            lock (_lock) { _entities[id] = entity; }
        }

        /// <summary>Retrieve a registered entity by its persona_id.</summary>
        public WyrdEntityData GetEntity(string personaId)
        {
            lock (_lock) { return _entities.TryGetValue(personaId, out var e) ? e : null; }
        }

        public int EntityCount { get { lock (_lock) { return _entities.Count; } } }

        // -------------------------------------------------------------------------
        // Query (async)
        // -------------------------------------------------------------------------

        /// <summary>
        /// Query WyrdHTTPServer for world context. Async — use with await or Task.Run.
        /// In Unity, prefer the documented coroutine pattern with UnityWebRequest.
        /// </summary>
        public async Task<WyrdQueryResult> QueryAsync(string personaId, string input,
                                                      CancellationToken ct = default)
        {
            var body = WyrdEntityData.BuildQueryBody(personaId, input);
            try
            {
                var content  = new StringContent(body, Encoding.UTF8, "application/json");
                var response = await _http.PostAsync(
                    Options.BaseUrl() + "/query", content, ct).ConfigureAwait(false);
                var json     = await response.Content.ReadAsStringAsync().ConfigureAwait(false);

                if (response.IsSuccessStatusCode)
                    return WyrdQueryResult.Ok(personaId, WyrdEntityData.ParseResponse(json));

                var err = $"HTTP {(int)response.StatusCode}";
                _lastError = err;
                return WyrdQueryResult.Failure(personaId, err);
            }
            catch (Exception ex)
            {
                _lastError = ex.Message;
                if (Options.SilentOnError)
                    return WyrdQueryResult.Ok(personaId, Options.FallbackResponse);
                return WyrdQueryResult.Failure(personaId, ex.Message);
            }
        }

        // -------------------------------------------------------------------------
        // Fire-and-forget helpers
        // -------------------------------------------------------------------------

        /// <summary>Push an observation. Fire-and-forget; errors captured in LastError.</summary>
        public void PushObservation(string title, string summary)
            => _ = PostFireAndForget("/event",
                    WyrdEntityData.BuildObservationBody(title, summary));

        /// <summary>Push a fact. Fire-and-forget.</summary>
        public void PushFact(string subjectId, string key, string value)
            => _ = PostFireAndForget("/event",
                    WyrdEntityData.BuildFactBody(subjectId, key, value));

        /// <summary>Sync an entity by pushing all its facts. Fire-and-forget.</summary>
        public void SyncEntity(WyrdEntityData entity)
        {
            var personaId = string.IsNullOrWhiteSpace(entity.EntityId)
                ? WyrdEntityData.NormalizePersonaId(entity.Name)
                : entity.EntityId;
            foreach (var fact in entity.ToFacts())
                PushFact(personaId, fact.Key, fact.Value);
        }

        // -------------------------------------------------------------------------
        // Health
        // -------------------------------------------------------------------------

        /// <summary>Check WyrdHTTPServer health. Blocking (use Task.Run in Unity).</summary>
        public async Task<bool> HealthCheckAsync(CancellationToken ct = default)
        {
            try
            {
                var response = await _http.GetAsync(
                    Options.BaseUrl() + "/health", ct).ConfigureAwait(false);
                return response.IsSuccessStatusCode;
            }
            catch (Exception ex) { _lastError = ex.Message; return false; }
        }

        public string LastError => _lastError;

        // -------------------------------------------------------------------------
        // Internal
        // -------------------------------------------------------------------------

        private async Task PostFireAndForget(string path, string body)
        {
            try
            {
                var content = new StringContent(body, Encoding.UTF8, "application/json");
                var resp    = await _http.PostAsync(Options.BaseUrl() + path, content)
                                         .ConfigureAwait(false);
                if (!resp.IsSuccessStatusCode)
                    _lastError = $"HTTP {(int)resp.StatusCode}";
            }
            catch (Exception ex) { _lastError = ex.Message; }
        }
    }
}
