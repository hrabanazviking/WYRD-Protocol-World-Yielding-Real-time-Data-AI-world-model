// WyrdForge.Build.cs — Unreal Engine 5 module build rules (Phase 13B).

using UnrealBuildTool;

public class WyrdForge : ModuleRules
{
    public WyrdForge(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicIncludePaths.AddRange(new string[] { });
        PrivateIncludePaths.AddRange(new string[] { });

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "HTTP",          // UE HTTP module — IHttpRequest / FHttpModule
            "Json",          // UE JSON utilities
            "JsonUtilities",
        });

        PrivateDependencyModuleNames.AddRange(new string[] { });

        // Enable C++20 for std::string_view and if constexpr
        CppStandard = CppStandardVersion.Cpp20;
    }
}
