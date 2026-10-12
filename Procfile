web: python manage.py migrate && python collect_static_manual.py && gunicorn univerin_backend.wsgi --timeout 120 --log-file -
worker: python manage.py run_delivery_offer_worker
