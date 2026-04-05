# WYRD World Editor TUI

A Rich-based terminal UI for live inspection and editing of WYRD world state.

## Installation

```bash
pip install rich
```

## Usage

```bash
# Connect to a running WyrdHTTPServer
python tools/wyrd_tui.py --host localhost --port 8765

# Offline mode — load a world YAML directly
python tools/wyrd_tui.py --offline --world configs/worlds/thornholt.yaml

# Custom server
python tools/wyrd_tui.py --host 192.168.1.50 --port 8765
```

## Panels

The TUI is divided into four live panels:

| Panel | Content |
|---|---|
| **World State** | Server status, world name, entity/location counts, zones |
| **Entity List** | All entities with ID, name, location, status |
| **Memory Log** | Recent facts from the last `/facts` query |
| **Query/Log** | Last query result + command history |

## Commands

| Command | Description |
|---|---|
| `/who [location]` | List entities at a location |
| `/where <entity>` | Show entity's location |
| `/facts <subject>` | Load and display facts for a subject |
| `/query <persona> <text>` | Query WYRD for world context |
| `/push obs <title> <summary>` | Push an observation event |
| `/refresh` | Refresh all panels from server |
| `/world` | Show world summary |
| `/clear` | Clear the command log |
| `/help` | Show command reference |
| `/quit` | Exit the TUI |

## Keyboard shortcuts

| Key | Action |
|---|---|
| `r` | Refresh all panels |
| `q` | Quit |
| `/` | Enter command mode |
| `Ctrl-C` | Force quit |

## Fallback mode

If `rich` is not installed, the TUI falls back to a simple line-by-line CLI with the same commands.
