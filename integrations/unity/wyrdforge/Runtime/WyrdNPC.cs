namespace WyrdForge.Unity
{
    /// <summary>
    /// WyrdNPC — MonoBehaviour component that registers this GameObject as a
    /// WYRD entity on Start() and exposes dialogue query helpers.
    ///
    /// ─── WIRE-UP GUIDE ───────────────────────────────────────────────────────
    ///
    /// 1. Attach WyrdNPC to any NPC GameObject.
    /// 2. Fill in EntityData (EntityId, Name, SceneName, Role).
    /// 3. Ensure a WyrdManager singleton exists in the scene.
    /// 4. In a dialogue trigger:
    ///
    ///    void OnPlayerInteract(string playerInput)
    ///    {
    ///        StartCoroutine(npc.QueryCoroutine(playerInput, reply =>
    ///        {
    ///            dialogueBubble.text = reply;
    ///        }));
    ///    }
    ///
    /// ─── FULL MONOBEHAVIOUR IMPLEMENTATION ───────────────────────────────────
    ///
    ///   using UnityEngine;
    ///   using UnityEngine.Networking;
    ///   using System.Collections;
    ///
    ///   public class WyrdNPCBehaviour : MonoBehaviour
    ///   {
    ///       public WyrdEntityData EntityData;
    ///
    ///       void Start()
    ///       {
    ///           if (WyrdManager.Instance.Options.AutoRegisterNPCs)
    ///               WyrdManager.Instance.RegisterEntity(EntityData);
    ///       }
    ///
    ///       public IEnumerator QueryCoroutine(string input, System.Action&lt;string&gt; onComplete)
    ///       {
    ///           string personaId = WyrdEntityData.NormalizePersonaId(EntityData.Name);
    ///           string body      = WyrdEntityData.BuildQueryBody(personaId, input);
    ///
    ///           var req = new UnityWebRequest(
    ///               WyrdManager.Instance.Options.BaseUrl() + "/query", "POST");
    ///           req.uploadHandler   = new UploadHandlerRaw(
    ///               System.Text.Encoding.UTF8.GetBytes(body));
    ///           req.downloadHandler = new DownloadHandlerBuffer();
    ///           req.SetRequestHeader("Content-Type", "application/json");
    ///
    ///           yield return req.SendWebRequest();
    ///
    ///           if (req.result == UnityWebRequest.Result.Success)
    ///               onComplete(WyrdEntityData.ParseResponse(req.downloadHandler.text));
    ///           else
    ///               onComplete(WyrdManager.Instance.Options.FallbackResponse);
    ///       }
    ///   }
    ///
    /// ─────────────────────────────────────────────────────────────────────────
    /// </summary>
    public sealed class WyrdNPC
    {
        /// <summary>Entity data for this NPC — fill before calling Register().</summary>
        public WyrdEntityData EntityData { get; }

        public WyrdNPC(WyrdEntityData entityData)
        {
            EntityData = entityData
                ?? throw new System.ArgumentNullException(nameof(entityData));
        }

        /// <summary>
        /// Register this NPC with WyrdManager.
        /// In a real MonoBehaviour, call this from Start().
        /// </summary>
        public void Register(WyrdManager manager)
            => manager.RegisterEntity(EntityData);

        /// <summary>Resolved persona_id for this NPC.</summary>
        public string PersonaId
            => string.IsNullOrWhiteSpace(EntityData.EntityId)
               ? WyrdEntityData.NormalizePersonaId(EntityData.Name)
               : EntityData.EntityId;
    }
}
