# Tool-Vergleich: beets vs Picard vs fpcalc+Script

Ticket: [#3](https://github.com/Crimvel/TuneSort/issues/3). Pipeline: Scan >20k MP3, Identify (Tags+Dateiname+AcoustID), Dedupe (beste Qualität behalten), Copy+Rename in neuen Ordner nach Schema, Original unangetastet, Review-Workflow für unsichere Matches.

## beets

- **Scan/Identify**: `beet import` mit MusicBrainz-Autotagger; `fromfilename`-Plugin füllt fehlende Tags aus Dateinamen, bevor MB-Match läuft. [Docs](https://beets.readthedocs.io/en/stable/plugins/fromfilename.html)
- **AcoustID-Fingerprint**: `chroma`-Plugin nutzt `fpcalc`/Chromaprint, liefert MB-Kandidaten über Fingerprint statt/zusätzlich zu Tags. Fingerprints werden in der Library-DB gespeichert (Caching, kein Re-Fingerprinting bei erneutem Lauf). [Docs](https://beets.readthedocs.io/en/stable/plugins/chroma.html)
- **Duplicate Detection**: `duplicates`-Plugin, Matching per MBID/Tags oder eigenem Checksum-Feld; Tiebreak wählbar (z.B. Bitrate) um beste Version zu behalten; Aktionen: move/copy/delete/tag — non-destruktiv möglich. [Docs](https://beets.readthedocs.io/en/stable/plugins/duplicates.html)
- **Non-destruktiver Copy-Mode**: `import.copy: yes` (Default) kopiert in Library-Ordner, Original bleibt unberührt; alternativ move/link/hardlink/reflink. [Docs](https://beets.readthedocs.io/en/stable/reference/config.html)
- **Pfadschema**: `paths:`-Config mit Template-Strings (`$artist/$album/$track $title`), Query-basierte Sonderfälle (z.B. Soundtracks) möglich.
- **Batch/Scriptability**: CLI-first, headless-fähig, `-q`/`--quiet`/Config-Flags für unbeaufsichtigten Import, Python-Plugin-API für Sonderfälle.
- **Review-Workflow**: Interaktiver Import-Prompt zeigt Score/Kandidaten bei unsicheren Matches; per Threshold (`match: strong_rec_thresh` etc.) autoconfirm vs. manuelle Entscheidung steuerbar; unsichere Fälle landen in Queue statt automatisch committed zu werden.
- **AcoustID Rate-Limit/Caching**: AcoustID-API begrenzt auf 3 req/s pro API-Key (kostenlos, non-commercial); beets fragt Key einmal ab und cached Fingerprints lokal in der DB, kein wiederholtes Fingerprinting bei erneutem Import. [AcoustID Webservice](https://acoustid.org/webservice)
- **Arch-Paket**: `beets` in `extra` (2.13.1-1, Stand 2026-07-30) — `pacman -S beets`. [archlinux.org](https://archlinux.org/packages/?q=beets)

## MusicBrainz Picard

- **Scan/Identify**: Cluster- und Lookup-Workflow über MB-Tags; kein natives "from filename"-Plugin im Kern (nur via NGS/Scripting-Plugins der Community).
- **AcoustID-Fingerprint**: Nativ integriert, nutzt `fpcalc` direkt, "Scan"-Button pro Datei/Batch. [Picard AcoustID Tutorial](https://picard-docs.musicbrainz.org/en/latest/tutorials/acoustid.html)
- **Duplicate Detection**: Kein eingebautes Duplikat-über-Fingerprint-Feature auf Library-Ebene — Picard tagged/organisiert Dateien, vergleicht sie aber nicht gegeneinander auf Doubletten.
- **Non-destruktiver Copy-Mode**: **Nicht vorhanden.** Picard kennt nur "Move files when saving" (verschiebt in Zielordner nach Naming-Script) oder Tags in-place schreiben. Ein "Original behalten, Kopie mit Tags speichern"-Modus ist ein offenes Feature-Request seit Jahren ([PICARD-183](https://tickets.metabrainz.org/browse/PICARD-183)), nicht Teil des Produkts.
- **Batch/Scriptability**: Command-Line-Optionen (`-e`, Single-Instance-Steuerung) erlauben Batch-Aufruf, aber Kern-Workflow ist GUI-zentriert (Cluster-Review vor Save). [Docs](https://picard-docs.musicbrainz.org/en/v2.13/appendices/command_line.html)
- **Review-Workflow**: Gut — Cluster-Ansicht zeigt Matches/Scores vor dem Schreiben, explizit für manuelle Kontrolle designt.
- **Arch-Paket**: `picard` in `extra` (2.13.3-3, Stand 2026-01-10) — `pacman -S picard`. [archlinux.org](https://archlinux.org/packages/?q=picard)

## Eigenbau (fpcalc + MusicBrainz-Script)

- Deckt jeden Punkt nur ab, wenn man ihn selbst baut: Scan-Loop, fpcalc-Aufruf, AcoustID-Lookup, Tag-Parsing, Dedupe-Logik, Copy+Rename, Review-UI — alles Marginalkosten on top von dem, was beets schon liefert.
- Rate-Limit/Caching müssten selbst implementiert werden (naive Scripts laufen schnell in die 3 req/s-Grenze).
- Einziger Vorteil: volle Kontrolle über Pfadschema/Dedupe-Heuristik — aber genau das deckt beets über Config + Plugin-API bereits ab.
- Klare YAGNI-Verletzung laut Map-Notiz ("fertige Tools vor Eigenbau; Scripts nur Klebstoff").

## Empfehlung

**beets**, mit `chroma`+`fromfilename`+`duplicates`-Plugins, `import.copy: yes`, Pfad-Template `Artist/Album/NN - Titel.mp3` aus Map-Entscheidung, und Import-Thresholds so gesetzt, dass unsichere Matches im interaktiven Prompt landen statt auto-committed zu werden.

**Begründung**: beets ist die einzige Kandidaten-Lösung, die alle fünf Punkte nativ abdeckt — Tags+Dateiname+Fingerprint-Identifikation, Fingerprint-Dedupe mit konfigurierbarem Tiebreak, echter non-destruktiver Copy-Modus, Templating, und Batch/CLI-Skriptbarkeit für >20k Dateien ohne GUI-Interaktion pro Track. Picard scheitert am zentralen Nicht-Verhandelbaren: kein natives "kopieren statt verschieben" (PICARD-183 offen), macht es für "Original unangetastet" ungeeignet ohne selbstgebauten Wrapper. Eigenbau baut nur nach, was beets schon hat, bei zusätzlichem Wartungsaufwand für Rate-Limiting/Caching. Beide Pakete (beets, picard) sind in Arch `extra` verfügbar, kein AUR nötig.
