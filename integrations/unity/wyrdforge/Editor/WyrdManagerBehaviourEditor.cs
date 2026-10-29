using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;

namespace WyrdForge.Unity.Editor
{
    /// <summary>
    /// WyrdManagerBehaviourEditor — the WyrdForge editor inspector (E3).
    ///
    /// Select the GameObject carrying WyrdManagerBehaviour and this
    /// inspector shows:
    ///   - the connection settings (host / port / timeout / behaviour
    ///     toggles / fallback text), editable as usual;
    ///   - live status: whether a manager exists yet, the last health
    ///     result, the registered-entity count and persona list, and
    ///     the last error;
    ///   - actions the existing client API honestly supports: a health
    ///     check and a test query against WyrdHTTPServer.
    ///
    /// The actions work in edit mode too: they build a throwaway
    /// WyrdManager from the values currently shown (the client is plain
    /// C# over HttpClient, so nothing here needs play mode). In play
    /// mode they use the behaviour's live manager instead.
    ///
    /// NOT VERIFIED IN UNITY: authored on a machine with no Unity
    /// installation (see README.md in this package). It compiles only
    /// inside the Unity editor.
    /// </summary>
    [CustomEditor(typeof(WyrdManagerBehaviour))]
    public sealed class WyrdManagerBehaviourEditor : UnityEditor.Editor
    {
        private string _testPersonaId = "sigrid_npc";
        private string _testInput = "What is the current world state?";
        private string _actionStatus = "No action run yet this session.";
        private string _queryResult = string.Empty;
        private bool _actionPending;

        public override void OnInspectorGUI()
        {
            serializedObject.Update();

            EditorGUILayout.LabelField("Connection", EditorStyles.boldLabel);
            DrawProperty("host");
            DrawProperty("port");
            DrawProperty("timeoutSeconds");

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Behaviour", EditorStyles.boldLabel);
            DrawProperty("autoRegisterNPCs");
            DrawProperty("silentOnError");
            DrawProperty("persistAcrossScenes");
            DrawProperty("checkHealthOnStart");

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Fallback", EditorStyles.boldLabel);
            DrawProperty("fallbackResponse");

            serializedObject.ApplyModifiedProperties();

            var behaviour = (WyrdManagerBehaviour)target;
            DrawStatus(behaviour);
            DrawActions(behaviour);
        }

        private void DrawProperty(string propertyName)
        {
            SerializedProperty property = serializedObject.FindProperty(propertyName);
            if (property != null)
                EditorGUILayout.PropertyField(property);
        }

        private void DrawStatus(WyrdManagerBehaviour behaviour)
        {
            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Status", EditorStyles.boldLabel);

            WyrdManager manager = behaviour.Manager;
            if (manager == null)
            {
                EditorGUILayout.HelpBox(
                    "No live manager yet. The manager is created in Awake " +
                    "(play mode). The actions below still work in edit " +
                    "mode: they use a throwaway manager built from the " +
                    "settings above.",
                    MessageType.Info);
            }
            else
            {
                EditorGUILayout.LabelField("Base URL", manager.Options.BaseUrl());
                EditorGUILayout.LabelField("Status", behaviour.StatusText);
                EditorGUILayout.LabelField(
                    "Last health check",
                    behaviour.LastHealthOk.HasValue
                        ? (behaviour.LastHealthOk.Value ? "OK" : "Failed")
                        : "Not run yet");
                EditorGUILayout.LabelField(
                    "Registered entities", manager.EntityCount.ToString());

                var ids = manager.RegisteredPersonaIds;
                if (ids.Count > 0)
                    EditorGUILayout.LabelField(
                        "Personas", string.Join(", ", ids));

                if (!string.IsNullOrEmpty(manager.LastError))
                    EditorGUILayout.HelpBox(
                        "Last error: " + manager.LastError, MessageType.Warning);
            }

            EditorGUILayout.LabelField("Last action", _actionStatus);
        }

        private void DrawActions(WyrdManagerBehaviour behaviour)
        {
            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Actions", EditorStyles.boldLabel);

            using (new EditorGUI.DisabledScope(_actionPending))
            {
                if (GUILayout.Button("Test Connection (Health Check)"))
                    RunHealthCheck(behaviour);

                EditorGUILayout.Space();
                _testPersonaId = EditorGUILayout.TextField("Test persona_id", _testPersonaId);
                _testInput = EditorGUILayout.TextField("Test query", _testInput);
                if (GUILayout.Button("Send Test Query"))
                    RunTestQuery(behaviour);
            }

            if (!string.IsNullOrEmpty(_queryResult))
            {
                EditorGUILayout.LabelField("Query response");
                EditorGUILayout.TextArea(_queryResult, GUILayout.MinHeight(48));
            }
        }

        // Use the live manager in play mode; in edit mode build a
        // throwaway one from the values currently shown in the inspector.
        private WyrdManager ManagerForActions(WyrdManagerBehaviour behaviour)
        {
            if (Application.isPlaying && behaviour.Manager != null)
                return behaviour.Manager;
            return new WyrdManager(behaviour.BuildOptions());
        }

        private void RunHealthCheck(WyrdManagerBehaviour behaviour)
        {
            _actionPending = true;
            _actionStatus = "Health check running...";
            WyrdManager manager = ManagerForActions(behaviour);
            Task<bool> task = manager.HealthCheckAsync();
            AwaitInEditor(task, ok =>
            {
                _actionPending = false;
                _actionStatus = ok
                    ? "Health check: server reachable at " + manager.Options.BaseUrl() + "."
                    : "Health check: server unreachable (" +
                      (manager.LastError ?? "no details") + ").";
            });
        }

        private void RunTestQuery(WyrdManagerBehaviour behaviour)
        {
            _actionPending = true;
            _actionStatus = "Test query running...";
            WyrdManager manager = ManagerForActions(behaviour);
            Task<WyrdQueryResult> task = manager.QueryAsync(_testPersonaId, _testInput);
            AwaitInEditor(task, result =>
            {
                _actionPending = false;
                _actionStatus = result.Success
                    ? "Test query succeeded."
                    : "Test query failed: " + result.ErrorMessage;
                _queryResult = result.Success ? result.Response : string.Empty;
            });
        }

        // Poll a task from the editor update loop and repaint when done.
        private void AwaitInEditor<T>(Task<T> task, System.Action<T> onDone)
        {
            EditorApplication.update += Poll;

            void Poll()
            {
                if (!task.IsCompleted)
                    return;
                EditorApplication.update -= Poll;
                if (task.IsFaulted)
                {
                    _actionPending = false;
                    _actionStatus = "Action faulted: " +
                        (task.Exception != null
                            ? task.Exception.GetBaseException().Message
                            : "unknown error");
                }
                else
                {
                    onDone(task.Result);
                }
                Repaint();
            }
        }
    }
}
