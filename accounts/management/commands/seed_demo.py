"""
Management command: seed_demo
Creates demo user and ~12 realistic past scan records.
Idempotent – safe to run multiple times.
"""

import os
import random
import io
from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.files.base import ContentFile

# Avoid importing Pillow at module level so tests can still import without Pillow
try:
    from PIL import Image as PILImage
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


CHILD_NAMES = [
    "Aziz Karimov", "Malika Toshmatova", "Jasur Yusupov",
    "Nilufar Rahimova", "Doniyor Ergashev", "Sarvar Mirzayev",
    "Zulfiya Nazarova", "Bobur Komilov", "Umida Xoliqova", "Sanjar Abdullayev",
    "Kamola Tursunova", "Asilbek Hamidov",
]

OBSERVATIONS_BY_CLASS = {
    "normal": [
        ["Ko'z oq qismi toza va ​​och rang", "Ko'z gavhari shaffof ko'rinadi", "Qovoq normal holatda", "Ko'z yoshi kanali yaxshi ishlaydi"],
        ["Ko'z sog'lom ko'rinadi", "Qizillik belgilari yo'q", "Ko'z harakati simmetrik", "Konyunktiva tozaligi normal"],
        ["Ko'z ichi bosimi belgilari yo'q", "Qovoq va kirajarlar normal", "Ko'z gavhari shaffof", "Yallig'lanish belgilari aniqlanmadi"],
    ],
    "attention": [
        ["Engil qizillik kuzatilmoqda", "Ko'z yoshlanishi biroz ko'paygan", "Qovoq biroz shishgan", "Ko'z qurishi belgilari bor"],
        ["Konyunktivada engil taranglik", "Ko'z charchash belgilari ko'rinadi", "Engil yallig'lanish belgilari", "Ko'z o'ti biroz kamaygan"],
        ["Ko'z yopish-ochishda sust harakat", "Biroz atipikal ko'z harakati", "Qovoq qizarishi", "Ko'z havzasi biroz shishgan"],
    ],
    "consult": [
        ["Belirgin qizillik va shish", "Ko'zdan ajralma (ifrozot) bor", "Qovoq osib tushgan (ptoz belgilari)", "Ko'z gavharing loyqalanishi kuzatilmoqda"],
        ["Ko'z tartibsiz harakati (strabizm belgilari)", "Kuchli yallig'lanish belgilari", "Ko'z oq qismida qo'ng'ir dog'", "Ko'z ichi bosimi belgilari ko'rinadi"],
        ["Shiddatli qizillik va ajralma", "Qovoq spazmi kuzatilmoqda", "Ko'z qorachig'i noaniq ko'rinadi", "Ko'z to'r pardasi sohasida o'zgarish shubhasi"],
    ],
}

RECOMMENDATIONS_BY_CLASS = {
    "normal": [
        "Ko'z mashqlarini kundalik bajarib boring (20-20-20 qoidasi).",
        "Ekran oldida har 20 daqiqada 20 soniya tanaffus oling, 20 metr uzoqlikka qarang.",
        "Yaxshi yoritilgan xonada o'qing va yozing.",
        "Ko'z salomatligini saqlash uchun yil da bir marta ko'z shifokoriga boring.",
        "Meva-sabzavot ko'p iste'mol qiling, ayniqsa A vitamini boyligi bor mahsulotlarni.",
    ],
    "attention": [
        "Ekran vaqtini cheklang: bolalar uchun kuniga 2 soatdan ko'p bo'lmasin.",
        "Ko'z dam olish mashqlari: ko'zni 5 soniya yumib, 5 soniya oching – 10 marta takrorlang.",
        "Ko'zni ishqalamang, chunki bu holat yomonlashishi mumkin.",
        "Xona harorati va namligiga e'tibor bering – quruq havo ko'zni quritadi.",
        "Yaqin vaqt ichida (1-2 hafta) ko'z shifokoriga murojaat qilishni ko'rib chiqing.",
        "Bolaning uyqu tartibini to'g'rilang: yetarli uyqu ko'z salomatligiga foyda beradi.",
    ],
    "consult": [
        "Imkon qadar tez ko'z shifokori (oftalmolog)ga murojaat qiling.",
        "Ko'zni ishqalamang – ajralmalar va yallig'lanish kuchayishi mumkin.",
        "Ko'z tomchilarini mutaxassis tayinlamasdan ishlatmang.",
        "Bolani yorqin nurdan va ekrandan uzoq tuting.",
        "Shifokor ko'rigiga borishdan oldin ko'zni iliq toza suv bilan ehtiyotkorlik bilan yuvib turish mumkin.",
    ],
}

SUMMARIES_BY_CLASS = {
    "normal": [
        "Bolaning ko'z sohasida hozircha ko'rinadigan muammo aniqlanmadi. Profilaktika sifatida yillik tekshiruvni o'tkazib boring.",
        "Ko'z holati yaxshi ko'rinadi. Sog'lom ko'z odatlarini davom ettiring va rejalashtirilgan tekshiruvlarni o'tkazib boring.",
        "Tahlil bo'yicha ko'zdagi belgilar normal doirada. Ekran vaqtini nazorat qiling va dam olishni ta'minlang.",
    ],
    "attention": [
        "Bolaning ko'zida engil belgilar kuzatilmoqda. Ekran vaqtini cheklash va ko'z dam olish mashqlarini bajarish tavsiya etiladi.",
        "Biroz charchash va qurish belgilari bor. Profilaktik choralar qabul qiling va holat yaxshilanmasa shifokorga murojaat qiling.",
        "Ko'z sohasida diqqatga sazovor engil o'zgarishlar bor. 1-2 hafta ichida ko'z shifokoriga murojaat qilishni o'ylab ko'ring.",
    ],
    "consult": [
        "Bolaning ko'zida shifokor ko'rigini talab qiladigan belgilar kuzatilmoqda. Imkon qadar tez oftalmologga murojaat qiling.",
        "Ko'zda aniq o'zgarishlar bor. Bu sun'iy intellekt tahlili bo'lib, aniq xulosa uchun mutaxassis ko'rigini o'tkazing.",
        "Bir nechta belgilar aniqlanib, professional ko'rik zarur. Bolaning ko'z sog'lig'i uchun shifokorga murojaat kechiktirmang.",
    ],
}


def _make_placeholder_image():
    """Create a small placeholder JPEG image for demo scans."""
    if not HAS_PILLOW:
        # Return minimal valid JPEG bytes
        return _minimal_jpeg()

    img = PILImage.new("RGB", (200, 200), color=(200, 220, 210))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _minimal_jpeg():
    """Minimal valid JPEG bytes (1×1 white pixel)."""
    return bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4,
        0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7,
        0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA,
        0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2, 0xE3,
        0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5,
        0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00,
        0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xFF, 0xD9,
    ])


class Command(BaseCommand):
    help = "Create demo user and seed realistic scan records. Idempotent."

    def handle(self, *args, **options):
        from scans.models import Scan

        # --- Create or get demo user ---
        user, created = User.objects.get_or_create(
            username="demo",
            defaults={
                "first_name": "Ibodat",
                "last_name": "Musurmonova",
                "email": "demo@opticare.uz",
            },
        )
        if not created and (user.first_name != "Ibodat" or user.last_name != "Musurmonova"):
            user.first_name = "Ibodat"
            user.last_name = "Musurmonova"
            user.save()

        if created:
            user.set_unusable_password()
            user.save()
            self.stdout.write(self.style.SUCCESS("Demo foydalanuvchi yaratildi: demo"))
        else:
            self.stdout.write("Demo foydalanuvchi allaqachon mavjud.")

        # --- Seed scans if fewer than 12 ---
        existing = Scan.objects.filter(user=user).count()
        if existing >= 12:
            self.stdout.write(f"Allaqachon {existing} ta tekshiruv mavjud. Yangi qo'shilmadi.")
            return

        now = timezone.now()
        records_created = 0
        class_distribution = ["normal"] * 5 + ["attention"] * 4 + ["consult"] * 3
        random.shuffle(class_distribution)

        image_bytes = _make_placeholder_image()

        for i, result_class in enumerate(class_distribution):
            days_ago = random.randint(i * 5, i * 5 + 15)
            created_at = now - timedelta(days=days_ago, hours=random.randint(0, 12))

            observations = random.choice(OBSERVATIONS_BY_CLASS[result_class])
            recommendations = RECOMMENDATIONS_BY_CLASS[result_class]
            summary = random.choice(SUMMARIES_BY_CLASS[result_class])
            confidence = round(random.uniform(0.72, 0.97), 2)
            child_name = random.choice(CHILD_NAMES)
            child_age = random.randint(4, 15)

            scan = Scan(
                user=user,
                child_name=child_name,
                child_age=child_age,
                notes="Demo tekshiruv yozuvi.",
                status="ok",
                result_class=result_class,
                confidence=confidence,
                summary=summary,
                observations=observations,
                recommendations=recommendations,
                raw_response={},
            )
            # Save image file
            filename = f"demo_scan_{i + 1}.jpg"
            scan.image.save(filename, ContentFile(image_bytes), save=False)
            scan.save()

            # Manually set created_at (auto_now_add prevents direct assignment)
            Scan.objects.filter(pk=scan.pk).update(created_at=created_at)
            records_created += 1

        self.stdout.write(self.style.SUCCESS(f"{records_created} ta tekshiruv yozuvi yaratildi."))
