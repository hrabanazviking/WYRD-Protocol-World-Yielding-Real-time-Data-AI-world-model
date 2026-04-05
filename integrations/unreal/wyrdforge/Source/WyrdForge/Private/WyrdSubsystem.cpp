// WyrdSubsystem.cpp — UE5 Game Instance Subsystem implementation.
// Uses UE's IHttpRequest (HTTP module) for async HTTP calls.

#include "WyrdSubsystem.h"
#include "WyrdHelpers.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"

void UWyrdSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    UE_LOG(LogTemp, Log, TEXT("[WyrdForge] Subsystem initialised. Host=%s Port=%d"),
           *Config.Host, Config.Port);
}

void UWyrdSubsystem::Deinitialize()
{
    Super::Deinitialize();
}

// ---------------------------------------------------------------------------
// QueryNPC
// ---------------------------------------------------------------------------

void UWyrdSubsystem::QueryNPC(const FString& PersonaId, const FString& UserInput,
                               const FOnWyrdQueryComplete& OnComplete)
{
    FString Body = WyrdHelpers::BuildQueryBody(PersonaId, UserInput);

    PostAsync(TEXT("/query"), Body, [this, PersonaId, OnComplete, Config = this->Config]
    (bool bOk, FString ResponseBody)
    {
        if (bOk)
        {
            FString Text = WyrdHelpers::ParseResponse(ResponseBody, Config.FallbackResponse);
            OnComplete.ExecuteIfBound(true, Text);
        }
        else
        {
            LastError = ResponseBody;
            FString Reply = Config.bSilentOnError ? Config.FallbackResponse : ResponseBody;
            OnComplete.ExecuteIfBound(!Config.bSilentOnError ? false : true, Reply);
        }
    });
}

// ---------------------------------------------------------------------------
// Fire-and-forget events
// ---------------------------------------------------------------------------

void UWyrdSubsystem::PushObservation(const FString& Title, const FString& Summary)
{
    PostAsync(TEXT("/event"), WyrdHelpers::BuildObservationBody(Title, Summary),
        [this](bool bOk, FString Err)
        {
            if (!bOk) LastError = Err;
        });
}

void UWyrdSubsystem::PushFact(const FString& SubjectId,
                               const FString& Key,
                               const FString& Value)
{
    PostAsync(TEXT("/event"), WyrdHelpers::BuildFactBody(SubjectId, Key, Value),
        [this](bool bOk, FString Err)
        {
            if (!bOk) LastError = Err;
        });
}

void UWyrdSubsystem::SyncEntity(const FString& PersonaId,
                                 const TArray<FWyrdFact>& Facts)
{
    for (const FWyrdFact& Fact : Facts)
        PushFact(PersonaId, Fact.Key, Fact.Value);
}

// ---------------------------------------------------------------------------
// HealthCheckAsync
// ---------------------------------------------------------------------------

void UWyrdSubsystem::HealthCheckAsync(TFunction<void(bool)> OnResult)
{
    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req =
        FHttpModule::Get().CreateRequest();

    Req->SetURL(Config.BaseUrl() + TEXT("/health"));
    Req->SetVerb(TEXT("GET"));
    Req->SetTimeout(Config.TimeoutSeconds);

    Req->OnProcessRequestComplete().BindLambda(
    [OnResult](FHttpRequestPtr, FHttpResponsePtr Response, bool bConnected)
    {
        OnResult(bConnected && Response.IsValid() &&
                 Response->GetResponseCode() >= 200 &&
                 Response->GetResponseCode() < 300);
    });

    Req->ProcessRequest();
}

// ---------------------------------------------------------------------------
// PostAsync
// ---------------------------------------------------------------------------

void UWyrdSubsystem::PostAsync(const FString& Path, const FString& Body,
                                TFunction<void(bool, FString)> OnDone)
{
    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req =
        FHttpModule::Get().CreateRequest();

    Req->SetURL(Config.BaseUrl() + Path);
    Req->SetVerb(TEXT("POST"));
    Req->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Req->SetContentAsString(Body);
    Req->SetTimeout(Config.TimeoutSeconds);

    Req->OnProcessRequestComplete().BindLambda(
    [OnDone](FHttpRequestPtr, FHttpResponsePtr Response, bool bConnected)
    {
        if (bConnected && Response.IsValid() &&
            Response->GetResponseCode() >= 200 &&
            Response->GetResponseCode() < 300)
        {
            OnDone(true, Response->GetContentAsString());
        }
        else
        {
            FString Err = bConnected && Response.IsValid()
                ? FString::Printf(TEXT("HTTP %d"), Response->GetResponseCode())
                : TEXT("Connection failed");
            OnDone(false, Err);
        }
    });

    Req->ProcessRequest();
}
