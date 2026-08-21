"""
Custom static file collector — bypasses a bug where Django's built-in
`collectstatic` command reports "0 static files copied" even though files
genuinely need collecting. Manual saving via the storage API works correctly,
so this script does that directly instead of using the collectstatic command.

Run with: python manage.py shell < collect_static_manual.py
Or adapted into a proper management command if this becomes a long-term fix.
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'univerin_backend.settings')
django.setup()

from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles.finders import get_finders

count = 0
errors = 0

for finder in get_finders():
    for path, storage in finder.list(None):
        try:
            if staticfiles_storage.exists(path):
                staticfiles_storage.delete(path)
            with storage.open(path) as source_file:
                staticfiles_storage.save(path, source_file)
            count += 1
        except Exception as e:
            print(f"ERROR saving {path}: {type(e).__name__}: {e}")
            errors += 1

print(f"Done. {count} files copied, {errors} errors.")