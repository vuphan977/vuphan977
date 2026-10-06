"""Local rotating SQLite backups. Copy these off the host separately."""
import os
import sys
import time
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def snapshot(keep=28):
    if not server.DB.is_file():
        raise FileNotFoundError('Application database is not initialized')
    folder = server.DB.parent / 'backups'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = folder / f'roomly-{time.time_ns()}.db'
    try:
        server.backup(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    # Delete only worker-created backups, after the new backup passed integrity checks.
    older = sorted((p for p in folder.glob('roomly-*.db') if re.fullmatch(r'roomly-[0-9]+\.db', p.name)), key=lambda p: p.name, reverse=True)
    for path in older[keep:]:
        path.unlink()
    return target


if __name__ == '__main__':
    interval = int(os.environ.get('BACKUP_INTERVAL', '21600'))
    keep = int(os.environ.get('BACKUP_KEEP', '28'))
    if interval < 60 or keep < 2:
        raise ValueError('BACKUP_INTERVAL >= 60 and BACKUP_KEEP >= 2 are required')
    while True:
        try:
            snapshot(keep)
        except Exception:
            print('Backup failed; previous backups retained. Check storage and permissions.', file=sys.stderr, flush=True)
        time.sleep(interval)
