namespace WyrdForge.Unity
{
    /// <summary>
    /// WyrdNPC — plain-C# wrapper that registers an entity with WyrdManager.
    ///
    /// This class is deliberately Unity-free so it can be unit-tested with
    /// plain dotnet. The Unity host layer is WyrdNPCBehaviour (E3), a real
    /// MonoBehaviour in this same Runtime folder: attach it to an NPC
    /// GameObject, fill in its Inspector fields, and it builds one of these
    /// and registers it on Start.
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
