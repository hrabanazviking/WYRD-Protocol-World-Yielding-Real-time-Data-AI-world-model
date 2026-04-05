#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Interfaces/IHttpRequest.h"
#include "WyrdTypes.h"
#include "WyrdSubsystem.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(
    FOnWyrdQueryComplete, bool, bSuccess, const FString&, Response);

/**
 * UWyrdSubsystem — Game Instance Subsystem for WyrdForge.
 *
 * Accessible from any Blueprint or C++ code via:
 *   UWyrdSubsystem* Wyrd = GetGameInstance()->GetSubsystem<UWyrdSubsystem>();
 *
 * ─── BLUEPRINT NODES ─────────────────────────────────────────────────────────
 *
 *   "Wyrd Query NPC"    → async HTTP POST /query → OnQueryComplete delegate
 *   "Wyrd Push Event"   → fire-and-forget HTTP POST /event
 *   "Wyrd Health Check" → sync HTTP GET /health → bool
 *
 * ─── C++ USAGE ───────────────────────────────────────────────────────────────
 *
 *   // In BeginPlay or dialogue trigger:
 *   auto* Wyrd = GetGameInstance()->GetSubsystem<UWyrdSubsystem>();
 *   Wyrd->QueryNPC("sigrid_npc", PlayerInput,
 *       FOnWyrdQueryComplete::CreateUObject(this, &AMyActor::OnWyrdReply));
 *
 *   void AMyActor::OnWyrdReply(bool bSuccess, const FString& Response)
 *   {
 *       DialogueBubble->SetText(FText::FromString(Response));
 *   }
 *
 * ─── ENTITY JOIN HOOK ────────────────────────────────────────────────────────
 *
 *   // In AGameMode::PostLogin:
 *   Wyrd->PushObservation(TEXT("Player joined"),
 *       FString::Printf(TEXT("%s entered the level."), *NewPlayer->GetName()));
 *   Wyrd->SyncEntity(NormalizedId, EntityMapper.ToFacts(...));
 *
 * ─────────────────────────────────────────────────────────────────────────────
 */
UCLASS()
class WYRDFORGE_API UWyrdSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    // USubsystem interface
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    // -------------------------------------------------------------------------
    // Configuration
    // -------------------------------------------------------------------------

    UPROPERTY(BlueprintReadWrite, Category = "WyrdForge")
    FWyrdConfig Config;

    UFUNCTION(BlueprintCallable, Category = "WyrdForge")
    void SetConfig(const FWyrdConfig& NewConfig) { Config = NewConfig; }

    // -------------------------------------------------------------------------
    // Query (async)
    // -------------------------------------------------------------------------

    /**
     * Query WYRD world context for a persona. Async — fires OnQueryComplete when done.
     * Blueprint-callable node: "Wyrd Query NPC".
     */
    UFUNCTION(BlueprintCallable, Category = "WyrdForge",
              meta = (DisplayName = "Wyrd Query NPC"))
    void QueryNPC(const FString& PersonaId, const FString& UserInput,
                  const FOnWyrdQueryComplete& OnComplete);

    // -------------------------------------------------------------------------
    // Fire-and-forget events
    // -------------------------------------------------------------------------

    /** Push an observation event. Blueprint node: "Wyrd Push Observation". */
    UFUNCTION(BlueprintCallable, Category = "WyrdForge",
              meta = (DisplayName = "Wyrd Push Observation"))
    void PushObservation(const FString& Title, const FString& Summary);

    /** Push a fact. Blueprint node: "Wyrd Push Fact". */
    UFUNCTION(BlueprintCallable, Category = "WyrdForge",
              meta = (DisplayName = "Wyrd Push Fact"))
    void PushFact(const FString& SubjectId, const FString& Key, const FString& Value);

    /** Sync an entity by pushing all its facts. */
    UFUNCTION(BlueprintCallable, Category = "WyrdForge")
    void SyncEntity(const FString& PersonaId, const TArray<FWyrdFact>& Facts);

    // -------------------------------------------------------------------------
    // Health
    // -------------------------------------------------------------------------

    /** Check WyrdHTTPServer health. Async — returns result via lambda. */
    void HealthCheckAsync(TFunction<void(bool)> OnResult);

    UFUNCTION(BlueprintPure, Category = "WyrdForge")
    FString GetLastError() const { return LastError; }

private:
    void PostAsync(const FString& Path, const FString& Body,
                   TFunction<void(bool, FString)> OnDone);

    FString LastError;
};
