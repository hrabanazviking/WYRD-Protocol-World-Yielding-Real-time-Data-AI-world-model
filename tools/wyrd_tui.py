#!/usr/bin/env python
"""WYRD World Inspector TUI — tools shim (Phase E4).

The implementation lives in ``src/wyrdforge/inspector_tui.py``,
promoted into the engine's supported surface in Phase E4 (roadmap
§3.8) and launched by the ``wyrd-inspect tui`` console script. This
file remains so the historical invocation ::

    python tools/wyrd_tui.py [--world YAML] [--host H] [--port P]

keeps working exactly as before — including from a bare checkout,
because the shim puts ``src/`` on ``sys.path`` itself when the
package is not installed. (Pattern: the Phase E2 root CLI shims.)
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from wyrdforge.inspector_tui import *  # noqa: F401,F403 — re-export surface
    from wyrdforge.inspector_tui import (
        EntityInfo,
        InspectorContext,
        MemoryEntry,
        TuiState,
        WorldSummary,
        WyrdRelayClient,
        build_command_help,
        format_uptime,
        handle_tui_command,
        main,
        normalize_persona_id,
        parse_facts_response,
        parse_world_response,
        run_tui,
    )
except ImportError:  # bare checkout — package not installed
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from wyrdforge.inspector_tui import *  # noqa: F401,F403
    from wyrdforge.inspector_tui import (
        EntityInfo,
        InspectorContext,
        MemoryEntry,
        TuiState,
        WorldSummary,
        WyrdRelayClient,
        build_command_help,
        format_uptime,
        handle_tui_command,
        main,
        normalize_persona_id,
        parse_facts_response,
        parse_world_response,
        run_tui,
    )

if __name__ == "__main__":
    main()
