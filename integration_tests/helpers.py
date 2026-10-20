import zlib

from django.contrib.auth.models import User

from merchant_app.models import Restaurant
from rider_app.models import Rider


def make_user(username, **kwargs):
    return User.objects.create_user(
        username=username, password='pw12345678', **kwargs
    )


def make_merchant_restaurant(owner, name):
    return Restaurant.objects.create(
        owner=owner,
        name=name,
        email=f'{name}@example.com'.replace(' ', '').lower(),
        contact_number='9876543210',
        address='1 Main Road',
        city='Testville',
    )


def make_rider(username, approved=True, available=True, **rider_kwargs):
    user = make_user(username)
    aadhar = str(10_000_000_000 + zlib.crc32(username.encode()) % 10**11)
    defaults = dict(
        phone='9876543210',
        # Rider.gender is a max_length=1 choice field (M/F/O). 'Male' is
        # only tolerated by SQLite; PostgreSQL rejects it.
        gender='M',
        aadhar_number=aadhar,
        driving_license=f'DL-{username}'[:20],
        address='1 Test Street',
        area='Test Area',
        pincode='123456',
        profile_photo='riders/profiles/p.jpg',
        aadhar_front='riders/aadhar/f.jpg',
        license_copy='riders/license/l.jpg',
        is_approved=approved,
        is_available=available,
    )
    defaults.update(rider_kwargs)
    return Rider.objects.create(user=user, **defaults)
