# Umsetzungsplan (entspricht Meilensteinen 1–8 des Heftes)
Reihenfolge, jeweils mit Tests (TDD) und Commit:
1. Gerüst: uv-Projekt, config/paths/store/models, API-Grundlage, Tests.
2. Medien: ffprobe, Proxy, Stills, Thumbnails; Quellen-API.
3. Szenen-Editor: Szenen/Segmente/Kommentare/Längenampel, weiche Sperren, Web-UI mit Player und I/O-Shortcuts.
4. Word-Export/-Rückimport.
5. Zeitmodell + Ankerpunkte + Doppelansicht + Conform (ffmpeg) + Kontrollansicht.
6. Strang-Board (PySceneDetect), Sortierung.
7. Aufnahme-Abgleich (Whisper, Alignment, Retakes) + LLM-Nachkorrektur.
8. Rohschnitt: schnitt.json, Stills, FCP-XML, Panel-Skelett, Vorlagen/Rezepte (.prfpset-Parser).
9. Bilder (XMP-Index, Credits, Konturfarbe, Web-Import), Karten-Proxy.
10. Feinschliff: Installer, README, Update-Check, Änderungsprotokoll; End-to-End-Test mit S2-E7-Ausschnitt.
