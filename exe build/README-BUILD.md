# Salt Combat Analytics — Windows EXE Build Kit

Based on **Desktop v12 Background Import**. HCS v12.8 is a separate in-game addon and is **not replaced** by this package.

## Build on Windows 10/11 or Windows Server

1. Install **64-bit Python 3.11 or 3.12** from python.org and enable the Python launcher `py`.
2. Extract this ZIP to a writable folder, e.g. `C:\SaltBuild`.
3. Double-click **Build-Windows.bat**. An internet connection is needed once to install PyInstaller.
4. After successful compilation, launch `dist\SaltCombatAnalytics\SaltCombatAnalytics.exe`.
5. The app opens `http://127.0.0.1:8765` in your browser.
6. To distribute, ZIP the **entire** `dist\SaltCombatAnalytics` folder. Do not distribute the `.exe` by itself.

## Configuration

For automatic HCS gear synchronization, create `wow_path.txt` next to the built EXE, containing only the WoW installation directory (the folder containing `WTF` and `Logs`). Example:

```text
D:\Games\HeroesWoW
```

The launcher checks each WoW account's SavedVariables every 3 seconds. The WoW client flushes SavedVariables on reload/logout; snapshots cannot be forced to disk from a WoW addon.

Import your combat log via **Load path**. No sample combat log or personal profile data is included.

## Known limitations

- This is a **build kit**, not a precompiled Windows executable: compilation must happen on Windows.
- The v12 backend still reparses the entire combat log on changes. SQLite persistence and truly incremental parsing are not included.
- Local web UI uses `127.0.0.1:8765`; only one analyzer instance can bind that port.
- The console window must remain open.
- The bundled app runs from a writable directory because it stores gear history and configuration next to its files.
- This package has not been executed on Windows or tested with your WoW installation.
