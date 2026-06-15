web: python manage.py migrate && python manage.py shell -c "
from users.models import User
try:
    if not User.objects.filter(phone_number='9999999999').exists():
        u = User(phone_number='9999999999', full_name='Admin', is_staff=True, is_superuser=True)
        u.set_password('admin123')
        u.save()
        print('Admin created!')
    else:
        print('Already exists!')
except Exception as e:
    print('Error:', e)
" && gunicorn univerin_backend.wsgi --log-file -
