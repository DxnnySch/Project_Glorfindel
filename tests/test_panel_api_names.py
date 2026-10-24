"""Jeder Premiere-Aufruf im Panel muss in den offiziellen Typdeklarationen (premierepro-26.5.d.ts) vorkommen – fängt Tippfehler und Erfindungen."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DTS = ROOT / "docs" / "bridge" / "premierepro-26.5.d.ts"

# Eigene Funktionen und JavaScript/Node-Bordmittel, die keine Premiere-API sind
OWN = {
    "tx", "tt", "guarded", "norm", "errText", "sleep", "walkItems", "asClip", "say", "emit", "countOk", "add", "step", "build", "visit", "find", "plan",
    "runPlan", "trackItemAt", "findSequenceItem", "ensureBin", "importFiles", "mediaByPath", "allMedia", "swapMedia", "listComponents", "findComponent",
    "paramList", "findParam", "toPproValue", "setParam", "addEffect", "builtin", "setMotion", "setFade", "addCrop", "plainValue", "projectDump",
    "readComponents", "sequenceDump", "methodsOf", "introspect", "selftest", "makeHandlers", "findServer", "projectInfo", "session", "onMessage",
    "run", "stop", "safe", "fn", "addAction", "ensureBin", "handlers", "log", "onStatus", "send", "start", "setStatus", "show", "setup",
    "projectDump", "fetchImpl", "fetch", "WebSocketImpl", "mediaByPath", "hostInfo", "WS",
}
JS = {
    "map", "filter", "find", "findIndex", "includes", "push", "slice", "join", "split", "replace", "startsWith", "endsWith", "toLowerCase", "toFixed",
    "stringify", "parse", "keys", "entries", "from", "isArray", "abs", "min", "max", "round", "floor", "has", "get", "set", "add", "forEach", "some", "every",
    "all", "then", "catch", "now", "toLocaleTimeString", "toString", "getOwnPropertyNames", "getPrototypeOf", "test", "flat", "concat", "at", "sort", "reverse",
    "removeChild", "prepend", "createElement", "getElementById", "setTimeout", "addEventListener", "encodeURIComponent", "close", "setAttribute", "toLowerCase",
    "padStart", "trim", "length", "json", "ok", "isNaN", "Number", "String", "Object", "Array", "Error", "Promise", "Map", "Set", "JSON", "Math", "Date",
    "require", "super", "constructor", "on", "preventDefault", "resolve", "reject", "fill", "reduce", "values", "assign", "freeze", "pop", "shift", "unshift",
    "lastIndexOf", "indexOf", "charAt", "substring", "toUpperCase", "isInteger", "parseInt", "parseFloat", "getTime", "toISOString", "call", "apply", "bind",
    "exec", "match", "matchAll", "search", "isFinite", "floor", "ceil", "sign", "pow", "sqrt", "remove", "append", "after", "before", "replaceChildren",
    "querySelector", "querySelectorAll", "classList", "contains", "toggle", "dispatchEvent", "stopPropagation", "getAttribute", "removeAttribute", "clear",
    "delete", "next", "done", "entries", "clone", "splice", "findLast", "isSequence", "flatMap",
}


def test_every_premiere_call_exists_in_the_official_typings():
    dts = DTS.read_text(encoding="utf-8")
    api = set(re.findall(r"\b([A-Za-z_]\w*)\s*[(:?]", dts)) | set(re.findall(r"\breadonly\s+(\w+)", dts))
    unknown: dict[str, set[str]] = {}
    for f in sorted((ROOT / "premiere-panel" / "lib").glob("*.js")):
        src = re.sub(r"//.*", "", f.read_text(encoding="utf-8"))
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        for name in re.findall(r"\.([A-Za-z_]\w*)\s*\(", src):
            if name in api or name in OWN or name in JS:
                continue
            unknown.setdefault(name, set()).add(f.name)
    assert not unknown, f"Aufrufe ohne Entsprechung in der Premiere-API: {unknown}"


def test_properties_used_on_api_objects_exist():
    dts = DTS.read_text(encoding="utf-8")
    for prop in ("displayName", "position", "seconds", "guid", "type", "name", "path", "red", "green", "blue", "alpha", "value", "x", "y"):
        assert re.search(rf"\b{prop}\b", dts), prop
    for const in ("MARKER_TYPE_COMMENT", "TYPE_BIN", "CLIP"):
        assert const in dts
