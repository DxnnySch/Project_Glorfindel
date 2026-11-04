# Credit-Vorlagen (editierbarer Text in Premiere)

Liegt hier eine Vorlage, setzt die Bridge den Credit als **echten Textclip** (Essential Graphics) statt als PNG – der Text bleibt in
Premiere frei änderbar (Schrift, Farbe, Ort, Schatten). Ohne Vorlage kommt für diese Art weiter das PNG.

## Einmalig einrichten (ca. 1 Minute je Vorlage)
1. In deinem fertigen Schnitt (z. B. `Mythen - S2 E7_1.prproj`) einen Credit-Textclip auswählen.
2. Fenster → **Essential Graphics** → Rechtsklick auf die Grafik → **Als Vorlage für Bewegungsgrafiken exportieren** …
   (Ziel: lokal, Name wie unten). Der Text muss ein **bearbeitbarer Textparameter** der Vorlage sein (im Bereich „Bearbeiten“ ein Textfeld anlegen).
3. Die Datei hierher legen:

| Datei | Wofür |
|---|---|
| `Credit Amazon.mogrt` | „© amazon studios“ (unten links) |
| `Credit Artwork.mogrt` | „© Künstler“ am Artwork |
| `Credit Musik.mogrt` | Musik-Credit (unten rechts) |

Es genügt, die Arten anzulegen, die du willst. Die Vorlage trägt Schrift und Ort selbst; nur bei Doppelbild-Layouts verschiebt die Bridge sie seitlich.
Nach dem ersten Bau zeigt der **Selbsttest** in der Panel-Ansicht („Text-Vorlage (MOGRT)“), ob Premiere den Text so annimmt.

## Voraussetzung: Premiere ab 27.0 (Beta)
Premiere 26.x erlaubt per Skript nur das *Einsetzen* einer Vorlage, nicht das Ändern ihres Texts (Adobe-Entwicklerforum, Stand Herbst 2026). Den Text
setzen kann die Schnittstelle erst ab **Premiere 27.0** (zurzeit Beta, in der Creative-Cloud-App unter „Betaversionen“). Dort erscheint die Vorlage mit einer
Komponente „AE.ADBE Capsule“, deren Textwert `setText` kennt. Mit 26.x setzt die Bridge die Credits automatisch als PNG.
