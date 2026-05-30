from django.db import migrations

def update_categories(apps, schema_editor):
    Vendor = apps.get_model('vendors', 'Vendor')
    Vendor.objects.filter(category='vegetables').update(category='veg_fruits')
    Vendor.objects.filter(category='fruits').update(category='veg_fruits')
    Vendor.objects.filter(category='fast_food').update(category='restaurant')
    Vendor.objects.filter(category='chinese').update(category='restaurant')
    Vendor.objects.filter(category='dairy').update(category='supermarket')
    Vendor.objects.filter(category='grocery').update(category='supermarket')

class Migration(migrations.Migration):
    dependencies = [
        ('vendors', '0020_alter_vendor_category'),
    ]
    operations = [
        migrations.RunPython(update_categories),
    ]
