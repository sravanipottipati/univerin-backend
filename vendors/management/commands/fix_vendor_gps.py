import requests
from django.core.management.base import BaseCommand
from vendors.models import Vendor

class Command(BaseCommand):
    help = 'Fix GPS coordinates for vendors without location'

    def handle(self, *args, **kwargs):
        vendors = Vendor.objects.filter(status='approved', latitude__isnull=True)
        self.stdout.write(f'Found {vendors.count()} vendors without GPS')
        for v in vendors:
            try:
                query = f"{v.address or ''}, {v.town or ''}, India"
                url = f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(query)}&key=AIzaSyCS_YRu6O61LCZn_QlypzjcjSdeRqbQaDI"
                res = requests.get(url, timeout=5)
                data = res.json()
                if data['status'] == 'OK':
                    loc = data['results'][0]['geometry']['location']
                    v.latitude = loc['lat']
                    v.longitude = loc['lng']
                    v.save()
                    self.stdout.write(f'OK {v.shop_name}: {loc["lat"]}, {loc["lng"]}')
                else:
                    self.stdout.write(f'FAIL {v.shop_name}: {data["status"]}')
            except Exception as e:
                self.stdout.write(f'ERROR {v.shop_name}: {e}')
