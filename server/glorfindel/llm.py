"""Optionale LLM-Unterstützung über eine OpenAI-kompatible Schnittstelle (ScaDS.AI, Heft §5.10).

Jede Funktion ist abschaltbar und hat einen stillen Fallback. Gesendet werden ausschließlich Texte.
Rate-Limits (429) werden mit Wartezeit einmal wiederholt (Erfahrung aus anderen Repos mit ScaDS).
"""
from __future__ import annotations

import json
import re
import time

from .config import Settings, scads_credentials

# bevorzugte Modelle je Funktion (erstes verfügbares gewinnt)
PREFERRED = {
    "transcript_fix": ["zai-org/GLM-5.3-Flash", "deepseek-ai/DeepSeek-V4.1-Flash", "openai/gpt-oss-120b"],
    "name_check": ["zai-org/GLM-5.3-Flash", "deepseek-ai/DeepSeek-V4.1-Flash"],
    "image_suggest": ["zai-org/GLM-5.3-Flash", "deepseek-ai/DeepSeek-V4.1-Flash"],
    "map_suggest": ["zai-org/GLM-5.3", "deepseek-ai/DeepSeek-V4.1-Flash"],
    "scene_titles": ["zai-org/GLM-5.3", "deepseek-ai/DeepSeek-V4.1-Flash"],
}

SYSTEM = ("Du hilfst beim Erstellen deutscher Video-Kommentare zur Serie „Die Ringe der Macht“ "
          "(Tolkiens Mittelerde). Antworte knapp und ausschließlich im verlangten Format.")


class Llm:
    def __init__(self, settings: Settings, client=None):
        self.settings = settings
        self._client = client
        self._models: list[str] | None = None
        self.last_error = ""

    # ---- Verfügbarkeit ----
    def enabled(self, feature: str) -> bool:
        s = self.settings.llm
        return s.enabled and s.features.get(feature, False) and bool(self.client)

    @property
    def client(self):
        if self._client is None:
            key, url = scads_credentials()
            if not key:
                return None
            from openai import OpenAI
            self._client = OpenAI(api_key=key, base_url=self.settings.llm.base_url or url,
                                  timeout=60, max_retries=0)
        return self._client

    def models(self) -> list[str]:
        if self._models is None:
            try:
                self._models = [m.id for m in self.client.models.list().data]
            except Exception as e:  # noqa: BLE001
                self.last_error = str(e)[:200]
                self._models = []
        return self._models

    def model_for(self, feature: str) -> str | None:
        chosen = self.settings.llm.models.get(feature)
        if chosen:
            return chosen
        avail = self.models()
        for m in PREFERRED.get(feature, []):
            if m in avail:
                return m
        return avail[0] if avail else None

    # ---- Aufruf ----
    def chat(self, feature: str, prompt: str, system: str = SYSTEM, max_tokens: int = 1500) -> str | None:
        if not self.enabled(feature):
            return None
        model = self.model_for(feature)
        if not model:
            return None
        for attempt in range(2):
            try:
                r = self.client.chat.completions.create(
                    model=model, max_tokens=max_tokens, temperature=0.2,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
                text = r.choices[0].message.content or ""
                return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
            except Exception as e:  # noqa: BLE001
                self.last_error = str(e)[:300]
                if "429" in str(e) and attempt == 0:
                    m = re.search(r"(\d+)\s*s", str(e))
                    time.sleep(min(70, float(m[1]) + 1) if m else 65)
                    continue
                return None
        return None

    def chat_json(self, feature: str, prompt: str, **kw):
        text = self.chat(feature, prompt + "\nAntworte nur mit gültigem JSON.", **kw)
        if not text:
            return None
        m = re.search(r"(\{.*\}|\[.*\])", text, flags=re.S)
        try:
            return json.loads(m.group(1)) if m else None
        except json.JSONDecodeError:
            return None

    # ---- Funktionen ----
    def fix_transcript(self, text: str, glossary: str) -> str:
        """Eigennamen im Whisper-Transkript korrigieren; Wortanzahl muss erhalten bleiben."""
        out = self.chat("transcript_fix",
                        f"Korrigiere nur falsch erkannte Eigennamen und Orte in diesem Transkript. "
                        f"Ändere nichts sonst, füge nichts hinzu, behalte die Wortanzahl.\nGlossar: {glossary}\n\n{text}")
        if out and abs(len(out.split()) - len(text.split())) <= max(2, len(text.split()) // 20):
            return out
        return text

    def check_names(self, text: str) -> list[dict]:
        r = self.chat_json("name_check",
                           "Finde falsch geschriebene Tolkien-Namen/-Orte im Text. Format: "
                           '[{"falsch": "...", "richtig": "..."}]. Leere Liste, wenn alles stimmt.\n\n' + text)
        return [x for x in (r or []) if isinstance(x, dict) and x.get("falsch") and x.get("richtig")]

    def suggest_search_terms(self, text: str) -> list[str]:
        r = self.chat_json("image_suggest",
                           "Leite aus dem Kommentartext 3-8 Suchbegriffe für Artwork/Bilder ab (Figuren, Orte, "
                           'Ereignisse). Format: {"begriffe": ["..."]}.\n\n' + text)
        return [str(t) for t in (r or {}).get("begriffe", [])][:8] if isinstance(r, dict) else []

    def suggest_map(self, text: str, map_names: list[str]) -> dict | None:
        r = self.chat_json("map_suggest",
                           f"Wähle die passendste Karte aus {json.dumps(map_names, ensure_ascii=False)} und nenne "
                           'die zu markierenden Orte. Format: {"karte": "...", "orte": ["..."]}.\n\n' + text)
        return r if isinstance(r, dict) and r.get("karte") in map_names else None

    def scene_title(self, transcript: str) -> str | None:
        out = self.chat("scene_titles", "Gib einen kurzen deutschen Szenentitel (max. 6 Wörter) für diese "
                        "Szene. Nur der Titel.\n\n" + transcript[:3000], max_tokens=40)
        return out.strip('"„“ \n') if out else None
