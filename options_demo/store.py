"""Private, bounded last-successful-run storage, outside the repository."""
import json
import os
from pathlib import Path
import tempfile

from .analysis import parse_symbol


class ReportStore:
    def __init__(self, directory: str | None):
        self.directory = Path(directory) if directory else None
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    def save(self, report: dict):
        if not self.directory or report["source"] != "tws":
            return
        symbol = parse_symbol(report["symbol"])
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".report-")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(report, f, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.directory / f"{symbol}.json")
        finally:
            if os.path.exists(name):
                os.unlink(name)
        for path in sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[50:]:
            path.unlink()

    def load(self, symbol: str | None = None):
        if not self.directory:
            return None
        paths = [self.directory / f"{parse_symbol(symbol)}.json"] if symbol else sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths:
            try:
                report = json.loads(path.read_text())
                if report["source"] == "tws" and report["symbol"] == path.stem:
                    return report
            except (OSError, ValueError, KeyError):
                continue
        return None
