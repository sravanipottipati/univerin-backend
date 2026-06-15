import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'univerin_backend.settings')
django.setup()
from users.models import User
try:
    if not User.objects.filter(phone_number='9999999999').exists():
        User.objects.create_superuser(
            phone_number='9999999999',
            password='admin123',
            full_name='Admin'
        )
        print('Admin created!')
    else:
        print('Already exists!')
except Exception as e:
    print('Error creating admin:', e)
