using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace WyrdForge.Unity
{
    /// <summary>
    /// WyrdNPCBehaviour — the real Unity host layer for a single NPC (E3).
    ///
    /// Attach to any NPC GameObject and fill in the Inspector fields. On
    /// Start it builds a <see cref="WyrdEntityData"/>, wraps it in the
    /// plain-C# <see cref="WyrdNPC"/>, and registers it with the scene's
    /// WyrdManagerBehaviour — provided that manager's AutoRegisterNPCs
    /// option is on (it is by default); otherwise call RegisterNow().
    ///
    /// The plain-C# WyrdNPC/WyrdEntityData classes are unchanged; this
    /// behaviour is only the Unity-facing shell (serialized fields,
    /// lifecycle, coroutines).
    ///
    /// NOT VERIFIED IN UNITY: authored on a machine with no Unity
    /// installation (see README.md in this package).
    /// </summary>
    [AddComponentMenu("WyrdForge/Wyrd NPC")]
    public sealed class WyrdNPCBehaviour : MonoBehaviour
    {
        /// <summary>One custom fact row (Unity cannot serialize Dictionary fields).</summary>
        [Serializable]
        public sealed class FactEntry
        {
            public string Key;
            public string Value;
        }

        [Header("Identity")]
        [SerializeField] private string entityId;
        [SerializeField] private string displayName;
        [SerializeField] private bool useGameObjectName = true;

        [Header("Context")]
        [SerializeField] private string sceneName;
        [SerializeField] private string role;
        [SerializeField] private List<FactEntry> customFacts = new List<FactEntry>();

        /// <summary>The plain-C# NPC wrapper built from the fields above.</summary>
        public WyrdNPC Npc { get; private set; }

        /// <summary>True once this NPC has been registered with a manager.</summary>
        public bool IsRegistered { get; private set; }

        /// <summary>Resolved persona_id (EntityId if set, else normalized name).</summary>
        public string PersonaId => Npc != null ? Npc.PersonaId : string.Empty;

        /// <summary>Build the entity data from the current serialized fields.</summary>
        public WyrdEntityData BuildEntityData()
        {
            string name = !string.IsNullOrWhiteSpace(displayName)
                ? displayName
                : (useGameObjectName ? gameObject.name : string.Empty);

            Dictionary<string, string> facts = null;
            if (customFacts != null && customFacts.Count > 0)
            {
                facts = new Dictionary<string, string>();
                foreach (FactEntry entry in customFacts)
                    if (entry != null && !string.IsNullOrEmpty(entry.Key))
                        facts[entry.Key] = entry.Value;
            }

            return new WyrdEntityData(entityId, name, sceneName, role, facts);
        }

        private void Start()
        {
            Npc = new WyrdNPC(BuildEntityData());

            WyrdManagerBehaviour managerBehaviour =
                FindObjectOfType<WyrdManagerBehaviour>();
            WyrdManager manager = managerBehaviour != null
                ? managerBehaviour.Manager
                : WyrdManager.Instance;

            if (manager != null && manager.Options.AutoRegisterNPCs)
                RegisterWith(manager);
        }

        /// <summary>Register this NPC with the given manager now.</summary>
        public void RegisterWith(WyrdManager manager)
        {
            if (Npc == null)
                Npc = new WyrdNPC(BuildEntityData());
            Npc.Register(manager);
            IsRegistered = true;
        }

        /// <summary>Register with the scene's manager (or the lazy singleton).</summary>
        public void RegisterNow()
        {
            WyrdManagerBehaviour managerBehaviour =
                FindObjectOfType<WyrdManagerBehaviour>();
            RegisterWith(managerBehaviour != null
                ? managerBehaviour.Manager
                : WyrdManager.Instance);
        }

        /// <summary>
        /// Ask WYRD about this NPC. Delegates to the scene's
        /// WyrdManagerBehaviour when one exists, otherwise polls the
        /// shared WyrdManager directly.
        /// </summary>
        public IEnumerator QueryCoroutine(string playerInput,
                                          Action<string> onComplete)
        {
            WyrdManagerBehaviour managerBehaviour =
                FindObjectOfType<WyrdManagerBehaviour>();
            if (managerBehaviour != null)
            {
                yield return managerBehaviour.QueryCoroutine(
                    PersonaId, playerInput, onComplete);
                yield break;
            }

            TaskQueryFallback(playerInput, onComplete);
            yield break;
        }

        // Direct-manager path used when no WyrdManagerBehaviour is in the
        // scene: poll the async query and invoke the callback from a
        // coroutine started here.
        private void TaskQueryFallback(string playerInput, Action<string> onComplete)
        {
            StartCoroutine(PollQuery(playerInput, onComplete));
        }

        private IEnumerator PollQuery(string playerInput, Action<string> onComplete)
        {
            System.Threading.Tasks.Task<WyrdQueryResult> task =
                WyrdManager.Instance.QueryAsync(PersonaId, playerInput);
            while (!task.IsCompleted)
                yield return null;

            if (task.IsFaulted || !task.Result.Success)
            {
                onComplete?.Invoke(WyrdManager.Instance.Options.FallbackResponse);
                yield break;
            }
            onComplete?.Invoke(task.Result.Response);
        }
    }
}
