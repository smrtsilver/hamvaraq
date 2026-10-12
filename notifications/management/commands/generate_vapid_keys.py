import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "جفت کلید VAPID برای Web Push می‌سازه؛ خروجی رو تو .env بذار (یک‌بار، و بعدش عوضش نکن)"

    def handle(self, *args, **opts):
        key = ec.generate_private_key(ec.SECP256R1())
        private = key.private_numbers().private_value.to_bytes(32, "big")
        public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.stdout.write(f"VAPID_PUBLIC_KEY={_b64(public)}\nVAPID_PRIVATE_KEY={_b64(private)}\nVAPID_SUBJECT=mailto:you@example.com")
