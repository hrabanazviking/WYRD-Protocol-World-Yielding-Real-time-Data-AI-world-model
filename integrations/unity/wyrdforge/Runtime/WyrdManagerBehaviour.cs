using System;
using System.Collections;
using System.Threading.Tasks;
using UnityEngine;

namespace WyrdForge.Unity
{
    /// <summary>
    /// WyrdManagerBehaviour — the real Unity host layer for WyrdForge (E3).
    ///
    /// Attach this component to a GameObject (conventionally an empty
    /// GameObject named "WyrdManager"). It wraps the plain-C#
    /// <see cref="WyrdManager"/> client: on Awake it builds a WyrdManager
    /// from the serialized connection settings below and publishes it as
    /// WyrdManager.Instance, so WyrdNPCBehaviour components (and your own
    /// scripts) can reach it.
    ///
    /// The plain-C# classes (WyrdManager, WyrdEntityData, WyrdNPC,
    /// WyrdUnityOptions) are unchanged and remain usable without Unity —
    /// the xUnit suite compiles them directly. This behaviour is only the
    /// Unity-facing shell: serialized settings, lifecycle, coroutines.
    ///
    /// Networking note: queries run through WyrdManager's HttpClient and
    /// are surfaced to Unity code as coroutines that poll the task, the
    /// standard dependency-free pattern. Results therefore arrive on the
    /// main thread.
    ///
    /// NOT VERIFIED IN UNITY: this file was authored on a machine with no
    /// Unity installation (see README.md in this package). It compiles
    /// only inside Unity (or a project referencing UnityEngine).
    /// </summary>
    [AddComponentMenu("WyrdForge/Wyrd Manager")]
    public sealed class WyrdManagerBehaviour : MonoBehaviour
    {
        // ---------------------------------------------------------------------
        // Serialized connection settings (edited in the Inspector)
        // ---------------------------------------------------------------------

        [Header("Connection")]
        [SerializeField] private string host = "localhost";
        [SerializeField] private int port = 8765;
        [SerializeField] private int timeoutSeconds = 10;

        [Header("Behaviour")]
        [SerializeField] private bool autoRegisterNPCs = true;
        [SerializeField] private bool silentOnError = true;
        [SerializeField] private bool persistAcrossScenes = true;
        [SerializeField] private bool checkHealthOnStart = true;

        [Header("Fallback")]
        [SerializeField]
        private string fallbackResponse = "The spirits whisper nothing of note.";

        // ---------------------------------------------------------------------
        // Runtime state
        // ---------------------------------------------------------------------

        /// <summary>The wrapped plain-C# client. Created in Awake.</summary>
        public WyrdManager Manager { get; private set; }

        /// <summary>Result of the most recent health check, if any.</summary>
        public bool? LastHealthOk { get; private set; }

        /// <summary>Human-readable status line for debugging / HUD use.</summary>
        public string StatusText { get; private set; } = "Not started.";

        public string Host => host;
        public int Port => port;

        /// <summary>Build options from the current serialized settings.</summary>
        public WyrdUnityOptions BuildOptions()
        {
            return new WyrdUnityOptions(host, port, timeoutSeconds,
                                        autoRegisterNPCs, silentOnError)
            {
                FallbackResponse = fallbackResponse
            };
        }

        // ---------------------------------------------------------------------
        // Unity lifecycle
        // ---------------------------------------------------------------------

        private void Awake()
        {
            Manager = new WyrdManager(BuildOptions());
            WyrdManager.SetInstance(Manager);
            StatusText = "WyrdManager created; not yet health-checked.";
            if (persistAcrossScenes)
                DontDestroyOnLoad(gameObject);
        }

        private void Start()
        {
            if (checkHealthOnStart)
                StartCoroutine(HealthCheckCoroutine(null));
        }

        private void OnDestroy()
        {
            // Only clear the singleton if it still points at our manager,
            // so a replacement behaviour in the next scene keeps its own.
            if (Manager != null && WyrdManager.Instance == Manager)
                WyrdManager.SetInstance(null);
        }

        // ---------------------------------------------------------------------
        // Coroutine surface (the API Unity scripts should call)
        // ---------------------------------------------------------------------

        /// <summary>
        /// Query WYRD for a persona. onComplete receives the response text,
        /// or the configured fallback response when the query failed.
        /// </summary>
        public IEnumerator QueryCoroutine(string personaId, string input,
                                          Action<string> onComplete)
        {
            if (Manager == null)
            {
                onComplete?.Invoke(fallbackResponse);
                yield break;
            }

            Task<WyrdQueryResult> task = Manager.QueryAsync(personaId, input);
            while (!task.IsCompleted)
                yield return null;

            if (task.IsFaulted)
            {
                StatusText = "Query faulted: " +
                    (task.Exception != null ? task.Exception.GetBaseException().Message : "unknown");
                onComplete?.Invoke(fallbackResponse);
                yield break;
            }

            WyrdQueryResult result = task.Result;
            StatusText = result.Success
                ? "Query OK for '" + result.PersonaId + "'."
                : "Query failed: " + result.ErrorMessage;
            onComplete?.Invoke(result.Success ? result.Response : fallbackResponse);
        }

        /// <summary>Health-check WyrdHTTPServer; reports via LastHealthOk/StatusText and the optional callback.</summary>
        public IEnumerator HealthCheckCoroutine(Action<bool> onComplete)
        {
            if (Manager == null)
            {
                LastHealthOk = false;
                onComplete?.Invoke(false);
                yield break;
            }

            Task<bool> task = Manager.HealthCheckAsync();
            while (!task.IsCompleted)
                yield return null;

            bool ok = !task.IsFaulted && task.Result;
            LastHealthOk = ok;
            StatusText = ok
                ? "WyrdHTTPServer reachable at " + Manager.Options.BaseUrl() + "."
                : "WyrdHTTPServer unreachable: " + (Manager.LastError ?? "no details");
            onComplete?.Invoke(ok);
        }

        /// <summary>Number of entities registered with the wrapped manager.</summary>
        public int EntityCount => Manager != null ? Manager.EntityCount : 0;
    }
}
