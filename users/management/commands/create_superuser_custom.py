from django.core.management.base import BaseCommand
from users.models import User

class Command(BaseCommand):
    help = "Create superuser for Django admin"

    def handle(self, *args, **kwargs):
        phone = "9876543210"
        password = "admin@univerin2024"
        if User.objects.filter(phone_number=phone).exists():
            user = User.objects.get(phone_number=phone)
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()
            self.stdout.write(f"Updated {phone} as superuser!")
        else:
            user = User.objects.create_superuser(
                phone_number=phone,
                password=password,
                full_name="Admin"
            )
            self.stdout.write(f"Created superuser {phone}!")
