#pragma once

#include "CoreMinimal.h"
#include "WyrdTypes.generated.h"

// ---------------------------------------------------------------------------
// FWyrdConfig — connection settings for WyrdHTTPServer
// ---------------------------------------------------------------------------

USTRUCT(BlueprintType)
struct WYRDFORGE_API FWyrdConfig
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "WyrdForge")
    FString Host = TEXT("localhost");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "WyrdForge")
    int32 Port = 8765;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "WyrdForge")
    float TimeoutSeconds = 10.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "WyrdForge")
    bool bSilentOnError = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "WyrdForge")
    FString FallbackResponse = TEXT("The spirits whisper nothing of note.");

    FString BaseUrl() const
    {
        return FString::Printf(TEXT("http://%s:%d"), *Host, Port);
    }
};

// ---------------------------------------------------------------------------
// FWyrdFact — a single ECS key/value pair
// ---------------------------------------------------------------------------

USTRUCT(BlueprintType)
struct WYRDFORGE_API FWyrdFact
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite, Category = "WyrdForge")
    FString Key;

    UPROPERTY(BlueprintReadWrite, Category = "WyrdForge")
    FString Value;

    FWyrdFact() {}
    FWyrdFact(FString InKey, FString InValue)
        : Key(MoveTemp(InKey)), Value(MoveTemp(InValue)) {}
};

// ---------------------------------------------------------------------------
// FWyrdQueryResult — result of a /query call
// ---------------------------------------------------------------------------

USTRUCT(BlueprintType)
struct WYRDFORGE_API FWyrdQueryResult
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "WyrdForge")
    bool bSuccess = false;

    UPROPERTY(BlueprintReadOnly, Category = "WyrdForge")
    FString PersonaId;

    UPROPERTY(BlueprintReadOnly, Category = "WyrdForge")
    FString Response;

    UPROPERTY(BlueprintReadOnly, Category = "WyrdForge")
    FString ErrorMessage;

    static FWyrdQueryResult Ok(const FString& InPersonaId, const FString& InResponse)
    {
        FWyrdQueryResult R;
        R.bSuccess  = true;
        R.PersonaId = InPersonaId;
        R.Response  = InResponse;
        return R;
    }

    static FWyrdQueryResult Failure(const FString& InPersonaId, const FString& InError)
    {
        FWyrdQueryResult R;
        R.bSuccess     = false;
        R.PersonaId    = InPersonaId;
        R.ErrorMessage = InError;
        return R;
    }
};
