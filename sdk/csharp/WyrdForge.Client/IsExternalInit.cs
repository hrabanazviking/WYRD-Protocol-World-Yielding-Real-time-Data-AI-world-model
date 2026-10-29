// IsExternalInit shim for the netstandard targets (Phase E2).
//
// The shipped models use C# 9 records and `init` accessors
// (see WyrdClientOptions / QueryOptions in WyrdClient.cs). The
// compiler requires the System.Runtime.CompilerServices.IsExternalInit
// marker type for those constructs; it ships in the framework from
// .NET 5 onward but does not exist in netstandard2.0/2.1, so it is
// supplied here for those targets only. This is the standard
// documented shim; it adds no runtime behaviour.
#if !NET5_0_OR_GREATER
namespace System.Runtime.CompilerServices
{
    internal static class IsExternalInit
    {
    }
}
#endif
