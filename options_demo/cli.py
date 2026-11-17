import argparse
import base64
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="Chat to an options anomaly demo or export a report.")
    parser.add_argument("message", nargs="?", help="Ticker or command, e.g. 'flow AAPL'")
    parser.add_argument("--serve", action="store_true", help="Open the local browser chat server")
    parser.add_argument("--port", type=int, default=8781)
    parser.add_argument("--source", choices=["synthetic", "tws"], default="synthetic")
    parser.add_argument("--scenario", choices=["call_activity", "put_activity", "wide_spreads"], default="call_activity")
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    if args.serve:
        os.environ["OPTIONS_SOURCE"] = args.source
        import uvicorn
        uvicorn.run("options_demo.app:app", host="127.0.0.1", port=args.port)
        return
    from .analysis import analyze, parse_symbol
    if not args.message:
        parser.error("Provide a ticker, or use --serve for the chat interface.")
    try:
        with redirect_stdout(sys.stderr):
            report = analyze(parse_symbol(args.message), args.scenario, args.source)
        args.out.mkdir(parents=True, exist_ok=True)
        symbol = report["symbol"]
        chart = args.out / f"{symbol}-anomalies.png"
        csv = args.out / f"{symbol}-quotes.csv"
        chart.write_bytes(base64.b64decode(report.pop("chart")))
        csv.write_text(report.pop("csv"))
        report["chart_path"] = str(chart.resolve())
        report["csv_path"] = str(csv.resolve())
        (args.out / f"{symbol}-report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
        print(json.dumps(report, allow_nan=False))
    except Exception:
        print(json.dumps({"error": "Analysis failed. Check ticker, TWS settings or output permissions. Try --source synthetic."}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
