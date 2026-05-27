
import requests
from vendors.models import Vendor

def geocode(address, town):
    try:
        query = f"{address}, {town}, India"
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(query)}&key=AIzaSyCS_YRu6O61LCZn_QlypzjcjSdeRqbQaDI"
        res = requests.get(url, timeout=5)
        data = res.json()
        if data["status"] == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except Exception as e:
        print(f"Error: {e}")
    return None, None

vendors = Vendor.objects.filter(status="approved", latitude__isnull=True)
print(f"Found {vendors.count()} vendors without GPS")
for v in vendors:
    lat, lng = geocode(v.address or "", v.town or "")
    if lat and lng:
        v.latitude = lat
        v.longitude = lng
        v.save()
        print(f"✅ {v.shop_name}: {lat}, {lng}")
    else:
        print(f"❌ {v.shop_name}: Could not geocode")
