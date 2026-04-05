#pragma once

#include "CoreMinimal.h"
#include "WyrdTypes.h"

/**
 * WyrdHelpers — pure static helper functions for WyrdForge UE5 plugin.
 *
 * All functions operate on FString / TArray — no HTTP or engine-runtime
 * dependency. Testable in isolation via Python mirror tests.
 */
class WYRDFORGE_API WyrdHelpers
{
public:
    WyrdHelpers() = delete;

    /**
     * Normalize a display name to a WYRD persona_id.
     * Lowercase, non-alphanumeric → '_', collapse '_+', strip leading/trailing '_', truncate 64.
     */
    static FString NormalizePersonaId(const FString& Name);

    /** Escape a string for embedding inside a JSON string literal. */
    static FString EscapeJson(const FString& Str);

    /** Build the JSON body for POST /query. */
    static FString BuildQueryBody(const FString& PersonaId, const FString& UserInput);

    /** Build the JSON body for POST /event (observation). */
    static FString BuildObservationBody(const FString& Title, const FString& Summary);

    /** Build the JSON body for POST /event (fact). */
    static FString BuildFactBody(const FString& SubjectId, const FString& Key, const FString& Value);

    /**
     * Extract the "response" string from a WyrdHTTPServer /query JSON reply.
     * Returns Fallback when the field is absent or blank.
     */
    static FString ParseResponse(const FString& JsonBody,
                                 const FString& Fallback = TEXT("The spirits whisper nothing of note."));

    /** Build a fact list from entity data. */
    static TArray<FWyrdFact> ToFacts(const FString& EntityName, const FString& EntityId,
                                     const FString& LevelName,
                                     const TMap<FString, FString>& CustomFacts);
};
