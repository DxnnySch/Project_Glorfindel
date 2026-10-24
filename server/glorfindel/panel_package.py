"""Premiere-Panel verpacken (.ccx) und über den Creative-Cloud-Installer einrichten."""
from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

PANEL_DIR = Path(__file__).resolve().parents[2] / "premiere-panel"
UPIA = Path(r"C:\Program Files\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe")


def build_ccx(dst: Path) -> Path:
    """Panel ohne Tests als Installationspaket (zip mit manifest.json im Stamm)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((PANEL_DIR / "manifest.json").read_text(encoding="utf-8"))
    tmp = dst.with_suffix(".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PANEL_DIR.rglob("*")):
            rel = f.relative_to(PANEL_DIR)
            if f.is_dir() or rel.parts[0] in ("test", "node_modules") or f.suffix == ".md":
                continue
            z.write(f, rel.as_posix())
    tmp.replace(dst)
    return dst


def installer_available() -> bool:
    return sys.platform == "win32" and UPIA.exists()


def install(ccx: Path) -> dict:
    """Startet den Installer von Creative Cloud (zeigt ggf. einen Bestätigungsdialog). Rückgabe: Hinweistext."""
    if installer_available():
        subprocess.Popen([str(UPIA), "/install", str(ccx)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        return {"gestartet": True, "text": "Der Creative-Cloud-Installer wurde gestartet. Danach Premiere neu starten und Fenster → Erweiterungen → „Glorfindel Bridge“ öffnen."}
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(ccx)])
        return {"gestartet": True, "text": "Die Datei wurde geöffnet. Danach Premiere neu starten und Fenster → Erweiterungen → „Glorfindel Bridge“ öffnen."}
    return {"gestartet": False, "text": f"Installer nicht gefunden. Datei per Doppelklick öffnen oder im UXP Developer Tool laden: {ccx}"}
