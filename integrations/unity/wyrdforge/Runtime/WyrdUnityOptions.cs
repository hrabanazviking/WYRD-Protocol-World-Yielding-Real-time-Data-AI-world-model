using System;
using System.Collections.Generic;

namespace WyrdForge.Unity
{
    /// <summary>
    /// Configuration for the WyrdForge Unity integration.
    /// Serializable so it can be stored as a ScriptableObject asset or
    /// embedded directly on the WyrdManager MonoBehaviour.
    ///
    /// ScriptableObject usage (recommended):
    /// <code>
    ///   [CreateAssetMenu(fileName = "WyrdOptions", menuName = "WyrdForge/Options")]
    ///   public class WyrdOptionsAsset : ScriptableObject
    ///   {
    ///       public WyrdUnityOptions options;
    ///   }
    /// </code>
    /// </summary>
    [Serializable]
    public sealed class WyrdUnityOptions
    {
        /// <summary>WyrdHTTPServer hostname or IP.</summary>
        public string Host = "localhost";

        /// <summary>WyrdHTTPServer port (default 8765).</summary>
        public int Port = 8765;

        /// <summary>HTTP request timeout in seconds.</summary>
        public int TimeoutSeconds = 10;

        /// <summary>If true, WyrdManager registers NPCs automatically on Start().</summary>
        public bool AutoRegisterNPCs = true;

        /// <summary>If true, returns fallback text on HTTP error instead of throwing.</summary>
        public bool SilentOnError = true;

        /// <summary>Fallback response when WyrdHTTPServer is unreachable.</summary>
        public string FallbackResponse = "The spirits whisper nothing of note.";

        /// <summary>Build the base URL string for WyrdHTTPServer.</summary>
        public string BaseUrl() => $"http://{Host}:{Port}";

        public WyrdUnityOptions() { }

        public WyrdUnityOptions(string host, int port, int timeoutSeconds = 10,
                                bool autoRegisterNPCs = true, bool silentOnError = true)
        {
            Host             = host;
            Port             = port;
            TimeoutSeconds   = timeoutSeconds;
            AutoRegisterNPCs = autoRegisterNPCs;
            SilentOnError    = silentOnError;
        }
    }

    // -------------------------------------------------------------------------
    // Result types (plain C# — no Unity dependency)
    // -------------------------------------------------------------------------

    /// <summary>Result of a /query call to WyrdHTTPServer.</summary>
    public sealed class WyrdQueryResult
    {
        public bool   Success      { get; }
        public string PersonaId    { get; }
        public string Response     { get; }
        public string ErrorMessage { get; }

        public WyrdQueryResult(bool success, string personaId,
                               string response, string errorMessage = null)
        {
            Success      = success;
            PersonaId    = personaId;
            Response     = response ?? string.Empty;
            ErrorMessage = errorMessage;
        }

        public static WyrdQueryResult Ok(string personaId, string response)
            => new(true,  personaId, response, null);

        public static WyrdQueryResult Failure(string personaId, string error)
            => new(false, personaId, string.Empty, error);
    }

    /// <summary>A single WYRD ECS fact: key → value.</summary>
    public sealed class WyrdFact
    {
        public string Key   { get; }
        public string Value { get; }
        public WyrdFact(string key, string value) { Key = key; Value = value; }
    }
}
