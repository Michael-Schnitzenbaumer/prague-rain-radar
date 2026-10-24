# Prague Rain Radar

Automatisches, langfristiges Archiv echter Radarmessungen des Tschechischen
Hydrometeorologischen Instituts (ČHMÚ) für die Region westlich von Prag bis
östlich von Prag.

## Was tatsächlich läuft

- Alle 15 Minuten liest GitHub Actions das offizielle ČHMÚ-Verzeichnis ein.
- Gespeichert wird das numerische Produkt **PseudoCAPPI 2 km** (HDF5/ODIM),
  nicht ein Screenshot einer Webseite.
- Verpasste Läufe werden beim nächsten Lauf innerhalb des verfügbaren
  ČHMÚ-Quellfensters nachgeholt.
- Pro UTC-Tag entsteht ein unverändertes Rohdatenarchiv in einem monatlichen
  GitHub Release `data-YYYY-MM`.
- Am 2. jedes Monats wird aus dem Vormonat ein MP4 mit lokaler Prager Zeit und
  UTC-Zeit erzeugt.
- Der neue Film wird lokal geprüft, hochgeladen und erneut per SHA-256 geprüft.
  Erst danach löscht die Automation den vorherigen Film.

Der regionale Ausschnitt ist konfigurierbar. Die Standardgrenzen sind:

```text
West  13.40° E    Ost  15.50° E
Süd   49.60° N    Nord 50.50° N
```

Damit bleiben die numerischen Messwerte für spätere West–Prag–Ost-Analysen
erhalten. Videos sind nur eine abgeleitete Darstellung.

## Datenquelle und Lizenz

Quelle: [ČHMÚ Open Data – PseudoCAPPI 2 km](https://opendata.chmi.cz/meteorology/weather/radar/composite/pseudocappi2km/hdf5/)

Die offenen Daten des ČHMÚ stehen unter
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Bei Weitergabe oder
Darstellung bitte angeben: **„Datenquelle: Český hydrometeorologický ústav
(ČHMÚ), CC BY 4.0“**.

Das Radarprodukt hat laut offizieller Beschreibung 1-km-Bodenauflösung,
5-Minuten-Zeitschritte und verwendet EPSG:3857. Dieses Projekt archiviert
davon bewusst nur jeden dritten Zeitschritt (15 Minuten).

## Speicher und Kosten

Das Projekt ist für ein **öffentliches** Repository ausgelegt:

- Standard-GitHub-Actions-Runner sind dort kostenlos.
- Actions-Artefakte sind ausdrücklich nicht das Langzeitarchiv; sie würden
  nach spätestens 90 Tagen verfallen.
- Die Rohdaten liegen stattdessen als Release-Assets. GitHub dokumentiert pro
  Datei ein Limit von 2 GiB und kein Gesamt- oder Bandbreitenlimit pro Release.
- Bei den am 24.10.2026 beobachteten Quelldateien von meist 20–40 kB sind grob
  60–120 MB Rohdaten pro Monat zu erwarten. Starke Niederschläge können größere
  Dateien erzeugen. Rechne zunächst mit etwa 1–2 GB pro Jahr plus Videos.

Release-Assets haben laut GitHub kein automatisches Ablaufdatum. „Dauerhaft“
bedeutet hier: Die Automation löscht sie nicht. Es ist keine Garantie gegen
Kontolöschung, GitHub-Ausfälle oder künftige Richtlinienänderungen. Für ein
wissenschaftlich belastbares Langzeitarchiv sollte später zusätzlich ein
zweites, unabhängiges Backup eingerichtet werden.

## Automationen

### Viertelstündliche Erfassung

`.github/workflows/capture.yml` läuft bei Minute 07, 22, 37 und 52 jeder
Stunde. Der Versatz vermeidet die besonders belastete volle Stunde und gibt
ČHMÚ Zeit, den jeweiligen Messwert bereitzustellen. Der Lauf verarbeitet den
aktuellen und den vorherigen UTC-Tag und ergänzt nur fehlende Viertelstunden.

### Monatliches Video

`.github/workflows/monthly-video.yml` läuft am 2. des Monats um 06:17 UTC und
verarbeitet den vollständigen Vormonat. Manuelle Starts sind ebenfalls
möglich; optional kann dabei ein Monat `YYYY-MM` angegeben werden.

### Überwachung

Fehlgeschlagene Läufe sind unter **Actions** sichtbar und lösen die normalen
GitHub-Benachrichtigungen aus. `status/latest-day.txt` wird höchstens einmal pro
Tag aktualisiert. Das hält den öffentlichen Zeitplan aktiv und zeigt zugleich,
bis zu welchem UTC-Tag erfolgreich archiviert wurde.

## Lokal testen

Benötigt werden Python 3.11+ und ffmpeg. Danach:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
python -m prague_rain_radar.collect --day 2026-10-24 --output /tmp/radar-2026-10-24.tar.gz
```

Ein Video aus entpackten HDF5-Dateien:

```bash
python -m prague_rain_radar.render --input-dir raw --month 2026-10 --output prague-radar-2026-10.mp4
```

## Hinweise zur Interpretation

PseudoCAPPI 2 km ist Radarreflektivität in 2 km Höhe, aus der ČHMÚ operativ
Niederschlagsintensität am Boden schätzt. Es ist kein Regenmesser am Boden.
Abschattung, nicht-meteorologische Echos und die vertikale Struktur der
Atmosphäre können Abweichungen verursachen.

