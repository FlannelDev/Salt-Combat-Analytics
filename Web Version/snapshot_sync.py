"""Copy HeroesCombatSnapshot SavedVariables into the WoW Logs directory.
WoW addons cannot write files directly; this companion runs outside the game.
"""
import argparse
import os
import shutil
import time
from pathlib import Path

NAME = 'HeroesCombatSnapshot.lua'

def candidates(wow):
    root = wow / 'WTF' / 'Account'
    if not root.is_dir():
        return []
    return [p for p in root.glob('*/SavedVariables/' + NAME) if p.is_file()]

def synchronize(wow, quiet=False):
    sources = candidates(wow)
    if not sources:
        if not quiet:
            print('No SavedVariables found. Use /reload or log out after inspection.')
        return False
    changed = False
    for src in sources:
        # Preserve every WoW account rather than silently choosing one account.
        account = src.parent.parent.name
        dst = wow / 'Logs' / 'HeroesCombatSnapshots' / account / NAME
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.stat().st_mtime_ns == src.stat().st_mtime_ns and dst.stat().st_size == src.stat().st_size:
            continue
        tmp = dst.with_name(dst.name + '.tmp')
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
        print(f'Snapshot synchronized: {src} -> {dst}')
        changed = True
    return changed

def main():
    ap = argparse.ArgumentParser(description='Sync Heroes WoW snapshots into the Logs folder')
    ap.add_argument('--wow', required=True, type=Path, help='WoW installation directory (containing WTF and Logs)')
    ap.add_argument('--watch', action='store_true', help='Keep syncing every 3 seconds')
    args = ap.parse_args()
    wow = args.wow.expanduser().resolve()
    if not (wow / 'WTF').is_dir():
        ap.error(f'WTF folder not found under {wow}')
    if args.watch:
        print(f'Watching {wow} (Ctrl+C to stop). Save in-game with /reload or logout.')
        try:
            while True:
                synchronize(wow, quiet=True)
                time.sleep(3)
        except KeyboardInterrupt:
            pass
    else:
        synchronize(wow)

if __name__ == '__main__':
    main()
