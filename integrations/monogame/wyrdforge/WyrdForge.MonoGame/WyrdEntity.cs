// WyrdEntity — a game object registered with WyrdSystem.
//
// Represents a game entity (player, NPC, item) that should have a
// corresponding record in WYRD's ECS world model.
//
// Usage:
//   var entity = new WyrdEntity { EntityId = "sigrid", Name = "Sigrid" };
//   entity.LocationId = "mead_hall";
//   entity.CustomFacts["role"] = "völva";
//   wyrdSystem.RegisterEntity(entity);
//   await wyrdSystem.SyncEntityAsync("sigrid");

namespace WyrdForge.MonoGame;

/// <summary>
/// A game entity whose state should be kept in sync with WYRD's ECS world model.
/// </summary>
public sealed class WyrdEntity
{
    /// <summary>Unique WYRD entity / persona ID. Should be snake_case.</summary>
    public string EntityId { get; set; } = string.Empty;

    /// <summary>Display name of the entity.</summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>Current Yggdrasil location ID, if known.</summary>
    public string? LocationId { get; set; }

    /// <summary>Classification tags (e.g. "npc", "player", "hostile").</summary>
    public List<string> Tags { get; set; } = [];

    /// <summary>
    /// Arbitrary key/value facts to push to WYRD (e.g. "role" → "blacksmith").
    /// Null values are omitted on sync.
    /// </summary>
    public Dictionary<string, string?> CustomFacts { get; set; } = [];

    /// <summary>
    /// Enumerate all facts that should be pushed to WYRD for this entity.
    /// Yields (key, value) pairs. Omits null/empty values.
    /// </summary>
    public IEnumerable<(string Key, string Value)> ToFacts()
    {
        if (!string.IsNullOrEmpty(Name))
            yield return ("name", Name);

        if (!string.IsNullOrEmpty(LocationId))
            yield return ("location", LocationId);

        if (Tags.Count > 0)
            yield return ("tags", string.Join(",", Tags));

        foreach (var kvp in CustomFacts)
        {
            if (!string.IsNullOrEmpty(kvp.Key) && !string.IsNullOrEmpty(kvp.Value))
                yield return (kvp.Key, kvp.Value!);
        }
    }
}
