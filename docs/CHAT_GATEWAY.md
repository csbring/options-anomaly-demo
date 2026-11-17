# Connecting an existing chat gateway

This is a transport contract, not a bundled WhatsApp bot. The demo does not authenticate to, receive from, or send to WhatsApp. The user's historical chat integration was not confirmed in the available source.

Run the same analysis from your own authenticated gateway:

```python
import json
import subprocess
import tempfile

from options_demo.analysis import parse_symbol

def analyze_chat_message(text: str):
    symbol = parse_symbol(text)  # Rejects extra commands, paths and shell text.
    with tempfile.TemporaryDirectory() as out:
        result = subprocess.run(
            ["options-demo", symbol, "--source", "synthetic", "--out", out],
            capture_output=True, text=True, check=True, timeout=90,
        )
        report = json.loads(result.stdout)
        # Read the image before the temporary directory is removed.
        from pathlib import Path
        image = Path(report["chart_path"]).read_bytes()
        return report["summary"], image
```

The gateway owns its user authentication, rate limits, channel credentials and attachment delivery. It should send the returned summary and PNG only to the requesting user. Do not interpolate message text into a shell command. Change the explicit source to `tws` only in your own local runtime with TWS configured. Serialize broker scans to avoid client-ID collisions and market-data limits.

For browser follow-ups, the local `/api/chat` response contains a `report_id`. Send it back with a supported follow-up. IDs are random, memory-only, expire after 30 minutes, and are not a substitute for authentication on a publicly hosted service.
