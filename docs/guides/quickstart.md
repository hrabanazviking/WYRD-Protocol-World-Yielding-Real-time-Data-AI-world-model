# Quickstart

Get WYRD Protocol running in 5 minutes.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) (for the LLM turn loop) — optional for the HTTP API

## Install

```bash
git clone https://github.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model
cd WYRD-Protocol
pip install -e .
```

## Start the server

```bash
python -m wyrdforge.server --port 8765
# → [WyrdForge] WyrdHTTPServer listening on http://localhost:8765
```

## Load a world

```bash
python wyrd_chat_cli.py --world configs/worlds/thornholt.yaml --entity sigrid
```

## Query from any language

=== "Python"

    ```python
    import requests

    r = requests.post("http://localhost:8765/query", json={
        "persona_id": "sigrid",
        "user_input": "Where am I?",
    })
    print(r.json()["response"])
    ```

=== "JavaScript"

    ```javascript
    const { WyrdClient } = require("wyrdforge-js");
    const client = new WyrdClient({ host: "localhost", port: 8765 });
    const result = await client.query("sigrid", "Where am I?");
    console.log(result.response);
    ```

=== "C#"

    ```csharp
    var client = new WyrdForge.Client.WyrdClient();
    var result = await client.QueryAsync("sigrid", "Where am I?");
    Console.WriteLine(result.Response);
    ```

=== "curl"

    ```bash
    curl -X POST http://localhost:8765/query \
      -H "Content-Type: application/json" \
      -d '{"persona_id":"sigrid","user_input":"Where am I?"}'
    ```

## Push world events

```bash
# Tell WYRD something happened
curl -X POST http://localhost:8765/event \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "observation",
    "payload": {
      "title": "Army sighted",
      "summary": "Scouts report 300 warriors crossing the northern river."
    }
  }'
```

## Open the TUI editor

```bash
python tools/wyrd_tui.py --world configs/worlds/thornholt.yaml
```

## Next steps

- [Your first world YAML](first-world.md)
- [Integrate with your game engine](../integrations/overview.md)
- [HTTP API reference](../api/http-api.md)
