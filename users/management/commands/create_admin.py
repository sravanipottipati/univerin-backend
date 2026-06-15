from django.core.management.base import BaseCommand
from users.models import User

class Command(BaseCommand):
    help = 'Create admin user'

    def handle(self, *args, **kwargs):
        try:
            if not User.objects.filter(phone_number='9999999999').exists():
                User.objects.create_user(
                    phone_number='9999999999',
                    password='admin123',
                    full_name='Admin',
                    is_staff=True,
                    is_admin=True,
                )
                self.stdout.write('Admin created!')
            else:
                self.stdout.write('Admin already exists!')
        except Exception as e:
            self.stdout.write(f'Error: {e}')
