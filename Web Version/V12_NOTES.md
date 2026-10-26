# Salt Combat Analytics Desktop v12 — Import Reliability

This release builds on the v11 Python desktop analyzer. It does **not** replace HCS v12.5 or package a Windows .exe.

## Changes
- Log imports run on a background thread. `/api/import` and `/api/import/upload` return HTTP 202 and `/api/import/status` reports state and lines scanned.
- File uploads stream to a temporary file in chunks before background parsing, avoiding one huge in-memory upload.
- Import errors are exposed in the UI and console.
- **Enable live refresh** monitors the selected local file every eight seconds and reloads it when it changes. **This is a full reparse**, not yet true incremental parsing; large logs may take time. Uploaded logs have no watchable source path.
- Existing combat, enemy, and gear screens are preserved.

## Usage
Run `Start-Heroes-Analyzer.bat`, open Import Log, and prefer **Load path** for live monitoring. After loading, click **Enable live refresh**. Leave HCS v12.5 installed separately in WoW.

## Known limitations
- No SQLite history or standalone EXE yet.
- No byte-accurate parse progress; the UI reports lines scanned.
- The initial bundled example log still parses synchronously at startup, as in v11.
- Avoid clearing/deleting an actively importing log; wait until the import completes.
