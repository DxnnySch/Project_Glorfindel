"""Liest alle .prfpset-Vorgaben eines Ordners und schreibt vorlagen/effekt_bibliothek.json (Stand zum Mitliefern).

Aufruf: python scripts/import_presets.py "F:\OneDrive\Videomaterial\Programm-Vorgaben\PremierePro"
Beim Bau liest das Tool den Ordner direkt (Einstellung premiere.presets_dir); diese Datei ist nur der Rückfall, wenn er fehlt.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from glorfindel import prfpset  # noqa: E402

if __name__ == "__main__":
    lib = prfpset.effect_library(sys.argv[1])
    dst = Path(__file__).resolve().parents[1] / "vorlagen" / "effekt_bibliothek.json"
    dst.write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(lib)} Effekte -> {dst}: {', '.join(lib)}")
