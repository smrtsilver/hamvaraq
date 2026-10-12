"""بکاپ دیتابیس (Postgres با pg_dump، SQLite با API رسمی sqlite3) و اختیاری پوشه‌ی media."""

import shutil
import sqlite3
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


def backup_sqlite(name, target):
    """کپی سازگار با API رسمی sqlite3 (حتی وقتی سایت داره می‌نویسه)؛ اتصال جدا از اتصال جنگو."""
    src = sqlite3.connect(str(name), uri=str(name).startswith("file:"))
    dst = sqlite3.connect(str(target))
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()


class Command(BaseCommand):
    help = "بکاپ دیتابیس تو BACKUP_DIR با نگه‌داشتن آخرین BACKUP_KEEP تا؛ برای cron"

    def add_arguments(self, parser):
        parser.add_argument("--media", action="store_true", help="پوشه‌ی media (عکس‌ها) هم آرشیو بشه")
        parser.add_argument("--dir", help="پوشه‌ی مقصد (پیش‌فرض BACKUP_DIR)")

    def handle(self, *args, **opts):
        dest = Path(opts["dir"] or settings.BACKUP_DIR)
        dest.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        db = settings.DATABASES["default"]

        if connection.vendor == "sqlite":
            target = dest / f"db-{stamp}.sqlite3"
            backup_sqlite(db["NAME"], target)
        elif connection.vendor == "postgresql":
            if not shutil.which("pg_dump"):
                raise CommandError("pg_dump نصب نیست (postgresql-client).")
            target = dest / f"db-{stamp}.dump"
            env = {"PGPASSWORD": db.get("PASSWORD") or "", "PATH": "/usr/bin:/bin:/usr/local/bin"}
            cmd = ["pg_dump", "-Fc", "-h", db.get("HOST") or "localhost", "-p", str(db.get("PORT") or 5432),
                   "-U", db.get("USER") or "postgres", "-f", str(target), db["NAME"]]
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if result.returncode:
                target.unlink(missing_ok=True)
                raise CommandError(f"pg_dump شکست خورد: {result.stderr.strip()}")
        else:
            raise CommandError(f"دیتابیس {connection.vendor} پشتیبانی نمی‌شه.")
        self.stdout.write(f"دیتابیس: {target} ({target.stat().st_size // 1024} KB)")

        if opts["media"] and Path(settings.MEDIA_ROOT).exists():
            media_target = dest / f"media-{stamp}.tar.gz"
            with tarfile.open(media_target, "w:gz") as tar:
                tar.add(settings.MEDIA_ROOT, arcname="media")
            self.stdout.write(f"media: {media_target} ({media_target.stat().st_size // 1024} KB)")

        self._prune(dest, "db-*", settings.BACKUP_KEEP)
        self._prune(dest, "media-*", settings.BACKUP_KEEP)

    def _prune(self, dest, pattern, keep):
        files = sorted(dest.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            old.unlink()
            self.stdout.write(f"حذف بکاپ قدیمی: {old.name}")
