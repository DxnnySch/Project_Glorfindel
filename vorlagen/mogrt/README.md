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

## So kommt der Text in den Credit
Premiere lässt den Text einer eingesetzten Grafik per Skript nicht setzen (auch nicht in 27.x). Deshalb schreibt der Server vor dem Einsetzen eine **Kopie der Vorlage mit dem richtigen Text**
(`server/glorfindel/mogrt_text.py`, Ablage im Cache der Folge unter `premiere/mogrt/`) und das Panel setzt diese Datei ein. Das geht mit jeder Premiere-Version, die die Vorlage importiert.

* Gibt es mehrere Exporte einer Art (`Credit Amazon.mogrt`, `Credit Amazon v2.mogrt`), gilt die **höchste Nummer**.
* Die Vorlage braucht ein freigegebenes Textfeld (Essential Graphics → Bearbeiten), sonst bleibt der Credit ein PNG.
* Nach einem Neuexport einfach die neue Datei mit höherer Nummer hier ablegen.
* Ist die Datei anders aufgebaut als erwartet, meldet der Bau das nicht als Fehler: der Credit kommt dann als PNG.
