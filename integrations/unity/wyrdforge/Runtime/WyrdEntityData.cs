using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace WyrdForge.Unity
{
    /// <summary>
    /// Data container for a WYRD-tracked Unity entity (NPC or player).
    ///
    /// Attach to any GameObject alongside WyrdNPC to auto-register on Start().
    /// Or build manually and pass to WyrdManager.RegisterEntity().
    /// </summary>
    [Serializable]
    public sealed class WyrdEntityData
    {
        /// <summary>Unique identifier within WYRD (auto-normalised from Name if empty).</summary>
        public string EntityId;

        /// <summary>Display name of the NPC/character.</summary>
        public string Name;

        /// <summary>Optional scene or location name.</summary>
        public string SceneName;

        /// <summary>Optional NPC role or type tag.</summary>
        public string Role;

        /// <summary>Extra custom key→value facts.</summary>
        public Dictionary<string, string> CustomFacts;

        public WyrdEntityData() { }

        public WyrdEntityData(string entityId, string name,
                              string sceneName = null, string role = null,
                              Dictionary<string, string> customFacts = null)
        {
            EntityId    = entityId;
            Name        = name;
            SceneName   = sceneName;
            Role        = role;
            CustomFacts = customFacts;
        }

        // -------------------------------------------------------------------------
        // Persona ID normalisation
        // -------------------------------------------------------------------------

        private static readonly Regex _nonAlnum  = new(@"[^a-z0-9_]", RegexOptions.Compiled);
        private static readonly Regex _multiUnder = new(@"_+",          RegexOptions.Compiled);

        /// <summary>
        /// Normalize a display name to a WYRD persona_id.
        /// Lowercase, replace non-alphanumeric with '_', collapse '__+',
        /// strip leading/trailing '_', truncate to 64 characters.
        /// </summary>
        public static string NormalizePersonaId(string name)
        {
            if (string.IsNullOrEmpty(name)) return string.Empty;
            var result = _nonAlnum.Replace(name.ToLowerInvariant(), "_");
            result = _multiUnder.Replace(result, "_").Trim('_');
            return result.Length > 64 ? result[..64] : result;
        }

        // -------------------------------------------------------------------------
        // Fact list
        // -------------------------------------------------------------------------

        /// <summary>
        /// Build a list of WYRD facts from this entity's data.
        /// Null/empty values are omitted.
        /// </summary>
        public IEnumerable<WyrdFact> ToFacts()
        {
            if (!string.IsNullOrEmpty(Name))
                yield return new WyrdFact("name", Name);

            if (!string.IsNullOrEmpty(EntityId))
                yield return new WyrdFact("entity_id", EntityId);

            if (!string.IsNullOrEmpty(SceneName))
                yield return new WyrdFact("scene", SceneName);

            if (!string.IsNullOrEmpty(Role))
                yield return new WyrdFact("role", Role);

            if (CustomFacts != null)
                foreach (var kv in CustomFacts)
                    if (!string.IsNullOrEmpty(kv.Key) && kv.Value != null)
                        yield return new WyrdFact(kv.Key, kv.Value);
        }

        // -------------------------------------------------------------------------
        // JSON body builders (no external library)
        // -------------------------------------------------------------------------

        /// <summary>Build the JSON body for POST /query.</summary>
        public static string BuildQueryBody(string personaId, string userInput)
        {
            if (string.IsNullOrWhiteSpace(userInput))
                userInput = "What is the current world state?";
            return $"{{\"persona_id\":\"{EscapeJson(personaId)}\","
                 + $"\"user_input\":\"{EscapeJson(userInput)}\","
                 + $"\"use_turn_loop\":false}}";
        }

        /// <summary>Build the JSON body for POST /event (observation).</summary>
        public static string BuildObservationBody(string title, string summary)
            => $"{{\"event_type\":\"observation\","
             + $"\"payload\":{{\"title\":\"{EscapeJson(title)}\","
             + $"\"summary\":\"{EscapeJson(summary)}\"}}}}";

        /// <summary>Build the JSON body for POST /event (fact).</summary>
        public static string BuildFactBody(string subjectId, string key, string value)
            => $"{{\"event_type\":\"fact\","
             + $"\"payload\":{{\"subject_id\":\"{EscapeJson(subjectId)}\","
             + $"\"key\":\"{EscapeJson(key)}\","
             + $"\"value\":\"{EscapeJson(value)}\"}}}}";

        /// <summary>
        /// Extract the "response" field from a WyrdHTTPServer /query JSON reply.
        /// Returns fallback text when the field is absent or blank.
        /// </summary>
        public static string ParseResponse(string json,
            string fallback = "The spirits whisper nothing of note.")
        {
            if (string.IsNullOrWhiteSpace(json)) return fallback;

            // Minimal extraction — find "response":"<value>"
            var match = Regex.Match(json, @"""response""\s*:\s*""((?:[^""\\]|\\.)*)""");
            if (!match.Success) return fallback;

            var value = match.Groups[1].Value
                .Replace("\\\"", "\"")
                .Replace("\\\\", "\\")
                .Replace("\\n",  "\n")
                .Replace("\\r",  "\r")
                .Replace("\\t",  "\t");

            return string.IsNullOrWhiteSpace(value) ? fallback : value;
        }

        /// <summary>Escape a string for embedding in a JSON string value.</summary>
        public static string EscapeJson(string s)
        {
            if (s is null) return string.Empty;
            return s.Replace("\\", "\\\\")
                    .Replace("\"", "\\\"")
                    .Replace("\b", "\\b")
                    .Replace("\f", "\\f")
                    .Replace("\n", "\\n")
                    .Replace("\r", "\\r")
                    .Replace("\t", "\\t");
        }
    }
}
