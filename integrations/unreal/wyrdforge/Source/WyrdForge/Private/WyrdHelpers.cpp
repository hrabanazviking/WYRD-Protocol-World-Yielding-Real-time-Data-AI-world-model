// WyrdHelpers.cpp — Pure helper implementations for WyrdForge UE5 plugin.
// No HTTP or UObject dependency — all pure string manipulation.

#include "WyrdHelpers.h"

// ---------------------------------------------------------------------------
// NormalizePersonaId
// ---------------------------------------------------------------------------

FString WyrdHelpers::NormalizePersonaId(const FString& Name)
{
    if (Name.IsEmpty()) return FString();

    FString Result = Name.ToLower();
    FString Out;
    Out.Reserve(Result.Len());

    bool bLastWasUnderscore = false;

    for (TCHAR Ch : Result)
    {
        bool bIsAlnum = (Ch >= 'a' && Ch <= 'z') || (Ch >= '0' && Ch <= '9') || Ch == '_';
        if (bIsAlnum)
        {
            Out.AppendChar(Ch);
            bLastWasUnderscore = (Ch == '_');
        }
        else if (!bLastWasUnderscore)
        {
            Out.AppendChar('_');
            bLastWasUnderscore = true;
        }
    }

    // Strip leading underscores
    while (Out.Len() > 0 && Out[0] == '_')
        Out.RemoveAt(0, 1);

    // Strip trailing underscores
    while (Out.Len() > 0 && Out[Out.Len() - 1] == '_')
        Out.RemoveAt(Out.Len() - 1, 1);

    // Truncate at 64
    if (Out.Len() > 64)
        Out = Out.Left(64);

    return Out;
}

// ---------------------------------------------------------------------------
// EscapeJson
// ---------------------------------------------------------------------------

FString WyrdHelpers::EscapeJson(const FString& Str)
{
    FString Out;
    Out.Reserve(Str.Len() + 8);

    for (TCHAR Ch : Str)
    {
        switch (Ch)
        {
            case '"':  Out += TEXT("\\\""); break;
            case '\\': Out += TEXT("\\\\"); break;
            case '\b': Out += TEXT("\\b");  break;
            case '\f': Out += TEXT("\\f");  break;
            case '\n': Out += TEXT("\\n");  break;
            case '\r': Out += TEXT("\\r");  break;
            case '\t': Out += TEXT("\\t");  break;
            default:
                if (Ch < 0x20)
                    Out += FString::Printf(TEXT("\\u%04x"), (int32)Ch);
                else
                    Out.AppendChar(Ch);
                break;
        }
    }
    return Out;
}

// ---------------------------------------------------------------------------
// JSON body builders
// ---------------------------------------------------------------------------

FString WyrdHelpers::BuildQueryBody(const FString& PersonaId, const FString& UserInput)
{
    FString Input = UserInput.TrimStartAndEnd().IsEmpty()
        ? TEXT("What is the current world state?")
        : UserInput;

    return FString::Printf(
        TEXT("{\"persona_id\":\"%s\",\"user_input\":\"%s\",\"use_turn_loop\":false}"),
        *EscapeJson(PersonaId), *EscapeJson(Input));
}

FString WyrdHelpers::BuildObservationBody(const FString& Title, const FString& Summary)
{
    return FString::Printf(
        TEXT("{\"event_type\":\"observation\","
             "\"payload\":{\"title\":\"%s\",\"summary\":\"%s\"}}"),
        *EscapeJson(Title), *EscapeJson(Summary));
}

FString WyrdHelpers::BuildFactBody(const FString& SubjectId,
                                   const FString& Key,
                                   const FString& Value)
{
    return FString::Printf(
        TEXT("{\"event_type\":\"fact\","
             "\"payload\":{\"subject_id\":\"%s\",\"key\":\"%s\",\"value\":\"%s\"}}"),
        *EscapeJson(SubjectId), *EscapeJson(Key), *EscapeJson(Value));
}

// ---------------------------------------------------------------------------
// ParseResponse
// ---------------------------------------------------------------------------

FString WyrdHelpers::ParseResponse(const FString& JsonBody, const FString& Fallback)
{
    if (JsonBody.TrimStartAndEnd().IsEmpty()) return Fallback;

    // Find "response":"<value>"
    int32 KeyIdx = JsonBody.Find(TEXT("\"response\""));
    if (KeyIdx == INDEX_NONE) return Fallback;

    int32 ColonIdx = JsonBody.Find(TEXT(":"), ESearchCase::IgnoreCase,
                                   ESearchDir::FromStart, KeyIdx);
    if (ColonIdx == INDEX_NONE) return Fallback;

    int32 QuoteStart = JsonBody.Find(TEXT("\""), ESearchCase::IgnoreCase,
                                     ESearchDir::FromStart, ColonIdx + 1);
    if (QuoteStart == INDEX_NONE) return Fallback;
    QuoteStart++; // skip opening quote

    // Find closing unescaped quote
    int32 QuoteEnd = QuoteStart;
    while (QuoteEnd < JsonBody.Len())
    {
        if (JsonBody[QuoteEnd] == '"' &&
            (QuoteEnd == 0 || JsonBody[QuoteEnd - 1] != '\\'))
            break;
        QuoteEnd++;
    }
    if (QuoteEnd >= JsonBody.Len()) return Fallback;

    FString Value = JsonBody.Mid(QuoteStart, QuoteEnd - QuoteStart);
    Value.TrimStartAndEndInline();

    return Value.IsEmpty() ? Fallback : Value;
}

// ---------------------------------------------------------------------------
// ToFacts
// ---------------------------------------------------------------------------

TArray<FWyrdFact> WyrdHelpers::ToFacts(const FString& EntityName,
                                        const FString& EntityId,
                                        const FString& LevelName,
                                        const TMap<FString, FString>& CustomFacts)
{
    TArray<FWyrdFact> Facts;

    if (!EntityName.IsEmpty()) Facts.Add(FWyrdFact(TEXT("name"),      EntityName));
    if (!EntityId.IsEmpty())   Facts.Add(FWyrdFact(TEXT("entity_id"), EntityId));
    if (!LevelName.IsEmpty())  Facts.Add(FWyrdFact(TEXT("level"),     LevelName));

    for (const auto& Pair : CustomFacts)
        if (!Pair.Key.IsEmpty() && !Pair.Value.IsEmpty())
            Facts.Add(FWyrdFact(Pair.Key, Pair.Value));

    return Facts;
}
