
def auto_geocode(address, town):
    """Convert address to GPS coordinates using Google Geocoding API"""
    import requests
    try:
        query = f"{address}, {town}, India"
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(query)}&key=AIzaSyCS_YRu6O61LCZn_QlypzjcjSdeRqbQaDI"
        res = requests.get(url, timeout=5)
        data = res.json()
        if data['status'] == 'OK':
            loc = data['results'][0]['geometry']['location']
            return loc['lat'], loc['lng']
    except Exception as e:
        print(f"Geocoding error: {e}")
    return None, None

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Vendor, Product, Wishlist
from .serializers import (VendorSerializer, VendorRegisterSerializer,
                          ProductSerializer, AddProductSerializer)
import math


class VendorRegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if hasattr(request.user, 'vendor'):
            return Response(
                {'error': 'You already have a shop registered'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if request.user.user_type != 'vendor':
            return Response(
                {'error': 'Only vendor accounts can register a shop'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = VendorRegisterSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            vendor = serializer.save()
            return Response({
                'message': 'Shop registered successfully!',
                'vendor':  VendorSerializer(vendor, context={'request': request}).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── NEARBY SHOPS — WITH BUYER RADIUS + VENDOR DELIVERY RADIUS ───────────────
class NearbyShopsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        town      = request.query_params.get('town', '')
        category  = request.query_params.get('category', '')
        buyer_lat = request.query_params.get('lat', None)
        buyer_lng = request.query_params.get('lng', None)

        # ── Buyer search radius — default 10 km, max 50 km ───────────────────
        try:
            buyer_radius = float(request.query_params.get('radius', 10.0))
            if buyer_radius > 50: buyer_radius = 50.0
            if buyer_radius < 1:  buyer_radius = 1.0
        except (ValueError, TypeError):
            buyer_radius = 10.0

        shops = Vendor.objects.filter(status='approved')
        # Swiggy style — if GPS available, skip town filter
        has_gps = request.query_params.get('lat') and request.query_params.get('lng')
        if town and not has_gps:
            shops = shops.filter(town__icontains=town)
        if category:
            shops = shops.filter(category=category)

        shops = list(shops)

        if buyer_lat and buyer_lng:
            try:
                blat = float(buyer_lat)
                blng = float(buyer_lng)

                def get_distance(v):
                    if not v.latitude or not v.longitude:
                        return 0.0
                    R    = 6371
                    dlat = math.radians(v.latitude - blat)
                    dlon = math.radians(v.longitude - blng)
                    a    = (math.sin(dlat/2)**2 +
                            math.cos(math.radians(blat)) *
                            math.cos(math.radians(v.latitude)) *
                            math.sin(dlon/2)**2)
                    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)), 1)

                filtered = []
                for s in shops:
                    dist = get_distance(s)

                    # Condition 1 — Shop within buyer's search radius
                    within_buyer_radius = dist <= buyer_radius

                    # Condition 2 — Buyer within vendor's delivery radius
                    vendor_delivery_radius = s.delivery_radius if s.delivery_radius is not None else 5.0
                    within_vendor_radius   = dist <= vendor_delivery_radius

                    # Both must be true for shop to show
                    if within_buyer_radius and within_vendor_radius:
                        s._distance = dist
                        filtered.append(s)

                # Sort by distance — nearest first
                filtered.sort(key=lambda s: s._distance)
                shops = filtered

            except (ValueError, TypeError):
                pass

        serializer = VendorSerializer(
            shops, many=True,
            context={'request': request}
        )
        return Response({
            'count':        len(shops),
            'buyer_radius': buyer_radius,
            'shops':        serializer.data
        })


class ShopDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, vendor_id):
        try:
            vendor     = Vendor.objects.get(id=vendor_id, status='approved')
            serializer = VendorSerializer(vendor, context={'request': request})
            return Response(serializer.data)
        except Vendor.DoesNotExist:
            return Response(
                {'error': 'Shop not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class AddProductView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            vendor = request.user.vendor
        except Exception:
            return Response(
                {'error': 'You do not have a shop yet'},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = AddProductSerializer(data=request.data)
        if serializer.is_valid():
            product = serializer.save(vendor=vendor)
            return Response({
                'message': 'Product added successfully',
                'product': ProductSerializer(product).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ShopProductsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, vendor_id):
        try:
            vendor   = Vendor.objects.get(id=vendor_id)
            products = Product.objects.filter(vendor=vendor)
            serializer = ProductSerializer(products, many=True)
            return Response({
                'shop':     vendor.shop_name,
                'count':    products.count(),
                'products': serializer.data
            })
        except Vendor.DoesNotExist:
            return Response(
                {'error': 'Shop not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class MyShopView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            vendor     = request.user.vendor
            serializer = VendorSerializer(vendor, context={'request': request})
            return Response(serializer.data)
        except Exception:
            return Response(
                {'error': 'You do not have a shop yet'},
                status=status.HTTP_404_NOT_FOUND
            )

    def patch(self, request):
        try:
            vendor = request.user.vendor
        except Exception:
            return Response({'error': 'You do not have a shop yet'}, status=404)
        allowed_fields = ['shop_name', 'address', 'town', 'phone_number', 'description', 'delivery_radius', 'latitude', 'longitude', 'category', 'min_order']
        # Auto-geocode if no GPS provided
        if not data.get('latitude') and not data.get('longitude'):
            addr = data.get('address', vendor.address or '')
            town = data.get('town', vendor.town or '')
            if addr or town:
                lat, lng = auto_geocode(addr, town)
                if lat and lng:
                    data._mutable = True if hasattr(data, '_mutable') else None
                    try:
                        data = data.copy()
                        data['latitude'] = lat
                        data['longitude'] = lng
                    except:
                        pass
        for field in allowed_fields:
            if field in request.data:
                setattr(vendor, field, request.data[field])
        vendor.save()
        return Response({
            'message': 'Shop updated successfully',
            'vendor': VendorSerializer(vendor, context={'request': request}).data
        })


class ToggleShopView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            vendor         = Vendor.objects.get(user=request.user)
            vendor.is_open = not vendor.is_open
            vendor.save()
            return Response({
                'is_open': vendor.is_open,
                'message': 'Shop is now Open!' if vendor.is_open else 'Shop is now Closed!'
            })
        except Vendor.DoesNotExist:
            return Response({'error': 'Vendor not found'}, status=404)


class EditProductView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id, vendor=request.user.vendor)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)
        serializer = AddProductSerializer(product, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            # Update base price to lowest variant price if variants exist
            min_price = ProductVariant.objects.filter(product=product).order_by('price').values_list('price', flat=True).first()
            if min_price:
                Product.objects.filter(id=product.id).update(price=min_price)
                product.refresh_from_db()
            return Response({
                'message': 'Product updated',
                'product': ProductSerializer(product).data
            })
        return Response(serializer.errors, status=400)

    def delete(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id, vendor=request.user.vendor)
            product.delete()
            return Response({'message': 'Product deleted'})
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)


# ─── SEARCH WITH FILTERS + SORT ───────────────────────────────────────────────
class SearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        q         = request.query_params.get('q', '').strip()
        town      = request.query_params.get('town', '').strip()
        min_price = request.query_params.get('min_price', None)
        max_price = request.query_params.get('max_price', None)
        sort_by   = request.query_params.get('sort_by', 'relevant')

        if not q:
            return Response({'shops': [], 'products': []})

        # ── Shops ──────────────────────────────────────────────────────────────
        shops = Vendor.objects.filter(status='approved')
        if town:
            shops = shops.filter(town__icontains=town)
        shops = shops.filter(shop_name__icontains=q)
        if sort_by == 'rating':
            shops = shops.order_by('-rating')
        elif sort_by == 'name':
            shops = shops.order_by('shop_name')
        else:
            shops = shops.order_by('-rating')

        shop_data = VendorSerializer(
            shops, many=True, context={'request': request}
        ).data

        # ── Products ───────────────────────────────────────────────────────────
        products = Product.objects.filter(is_available=True)
        if buyer_lat and buyer_lng and 'nearby_ids' in dir():
            products = products.filter(vendor__id__in=nearby_ids)
        elif town:
            products = products.filter(vendor__town__icontains=town)
        products = products.filter(name__icontains=q)

        if min_price:
            try:
                products = products.filter(price__gte=float(min_price))
            except ValueError:
                pass
        if max_price:
            try:
                products = products.filter(price__lte=float(max_price))
            except ValueError:
                pass

        if sort_by == 'price_low':
            products = products.order_by('price')
        elif sort_by == 'price_high':
            products = products.order_by('-price')
        elif sort_by == 'rating':
            products = products.order_by('-vendor__rating')
        elif sort_by == 'name':
            products = products.order_by('name')
        else:
            products = products.order_by('name')

        product_data = []
        for p in products:
            product_data.append({
                'id':                    str(p.id),
                'name':                  p.name,
                'price':                 str(p.price),
                'category':              p.category,
                'description':           p.description or '',
                'image_url':             p.image.url if p.image else None,
                'shop_name':             p.vendor.shop_name,
                'shop_id':               str(p.vendor.id),
                'town':                  p.vendor.town,
                'rating':                str(p.vendor.rating),
                'estimated_delivery_time': p.vendor.estimated_delivery_time or 30,
            })

        return Response({'shops': shop_data, 'products': product_data})


# ─── WISHLIST ─────────────────────────────────────────────────────────────────
class WishlistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = Wishlist.objects.filter(
            user=request.user
        ).select_related('product__vendor')
        data = [{
            'id':           str(w.id),
            'product_id':   str(w.product.id),
            'name':         w.product.name,
            'price':        str(w.product.price),
            'shop_name':    w.product.vendor.shop_name,
            'shop_id':      str(w.product.vendor.id),
            'town':         w.product.vendor.town,
            'is_available': w.product.is_available,
            'added_at':     w.created_at.isoformat(),
        } for w in items]
        return Response({'count': len(data), 'wishlist': data})

    def post(self, request):
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id required'}, status=400)
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)

        wishlist, created = Wishlist.objects.get_or_create(
            user=request.user, product=product
        )
        if created:
            return Response({'message': 'Added to wishlist', 'wishlisted': True}, status=201)
        else:
            wishlist.delete()
            return Response({'message': 'Removed from wishlist', 'wishlisted': False})


# ─── PRODUCT VARIANT VIEWS ────────────────────────────────────────────────────
from .models import ProductVariant
from .serializers import AddVariantSerializer, ProductVariantSerializer

class ProductVariantView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        try:
            product  = Product.objects.get(id=product_id)
            variants = ProductVariant.objects.filter(product=product, is_available=True)
            return Response({
                'product_id':   str(product.id),
                'product_name': product.name,
                'base_price':   str(product.price),
                'variants':     ProductVariantSerializer(variants, many=True).data
            })
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)

    def post(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id, vendor=request.user.vendor)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)
        serializer = AddVariantSerializer(data=request.data)
        if serializer.is_valid():
            variant = serializer.save(product=product)
            # Update product base price to lowest variant price
            min_price = ProductVariant.objects.filter(product=product).order_by('price').values_list('price', flat=True).first()
            if min_price:
                Product.objects.filter(id=product.id).update(price=min_price)
            return Response({
                'message': 'Variant added successfully',
                'variant': ProductVariantSerializer(variant).data
            }, status=201)
        return Response(serializer.errors, status=400)


class EditVariantView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, variant_id):
        try:
            variant = ProductVariant.objects.get(
                id=variant_id, product__vendor=request.user.vendor
            )
        except ProductVariant.DoesNotExist:
            return Response({'error': 'Variant not found'}, status=404)
        serializer = AddVariantSerializer(variant, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            # Update product base price to lowest variant price
            product = variant.product
            min_price = ProductVariant.objects.filter(product=product).order_by('price').values_list('price', flat=True).first()
            if min_price:
                Product.objects.filter(id=product.id).update(price=min_price)
            return Response({
                'message': 'Variant updated',
                'variant': ProductVariantSerializer(variant).data
            })
        return Response(serializer.errors, status=400)

    def delete(self, request, variant_id):
        try:
            variant = ProductVariant.objects.get(
                id=variant_id, product__vendor=request.user.vendor
            )
            variant.delete()
            return Response({'message': 'Variant deleted'})
        except ProductVariant.DoesNotExist:
            return Response({'error': 'Variant not found'}, status=404)

# ── Popular Products — for Home Screen ───────────────────────────────────────
class PopularProductsView(APIView):
    permission_classes = []
    def get(self, request):
        from orders.models import OrderItem
        from django.db.models import Count, Case, When, IntegerField
        from datetime import datetime, timedelta

        town     = request.query_params.get('town', '')
        category = request.query_params.get('category', '')
        buyer_lat = request.query_params.get('lat', None)
        buyer_lng = request.query_params.get('lng', None)
        buyer_radius = float(request.query_params.get('radius', 20.0))

        vendors = Vendor.objects.filter(status='approved')
        if buyer_lat and buyer_lng:
            try:
                blat = float(buyer_lat)
                blng = float(buyer_lng)
                nearby_ids = []
                for v in vendors:
                    if v.latitude and v.longitude:
                        dlat = math.radians(v.latitude - blat)
                        dlon = math.radians(v.longitude - blng)
                        a = math.sin(dlat/2)**2 + math.cos(math.radians(blat)) * math.cos(math.radians(v.latitude)) * math.sin(dlon/2)**2
                        dist = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                        if dist <= buyer_radius:
                            nearby_ids.append(v.id)
                vendors = vendors.filter(id__in=nearby_ids)
            except (ValueError, TypeError):
                if town:
                    vendors = vendors.filter(town__icontains=town)
        elif town:
            vendors = vendors.filter(town__icontains=town)
        if category:
            vendors = vendors.filter(category=category)

        last_30_days = datetime.now() - timedelta(days=30)
        popular_ids = list(OrderItem.objects.filter(
            order__vendor__in=vendors,
            order__created_at__gte=last_30_days,
            order__status='delivered',
        ).values('product_id').annotate(
            order_count=Count('id')
        ).order_by('-order_count').values_list('product_id', flat=True)[:20])

        products = []
        if popular_ids:
            preserved = Case(
                *[When(id=pk, then=pos) for pos, pk in enumerate(popular_ids)],
                output_field=IntegerField()
            )
            products = list(Product.objects.filter(
                id__in=popular_ids,
                is_available=True,
            ).select_related('vendor').order_by(preserved))

        if not products:
            products = list(Product.objects.filter(
                vendor__in=vendors,
                is_available=True,
            ).select_related('vendor').order_by('?')[:12])

        data = []
        for i, p in enumerate(products):
            data.append({
                'id':           str(p.id),
                'name':         p.name,
                'price':        str(p.price),
                'category':     p.category,
                'image_url':    p.image.url if p.image else None,
                'vendor_id':    str(p.vendor.id),
                'shop_name':    p.vendor.shop_name,
                'is_available': p.is_available,
                'order_count':  i + 1,
            })
        return Response(data)
