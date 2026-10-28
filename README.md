# OptiCare — Bolalar Ko'z Salomatligi AI Tahlili

**OptiCare** — bolalarda ko'z salomatligini sun'iy intellekt yordamida tahlil qilish xizmati. Ota-onalar smartfon kamerasidan foydalanib yoki galereyadagi fotosuratni yuklab, ko'z sohasidagi ko'rinadigan belgilar (qizarish, quruqlik, qovoq va ko'z holati, shish, yoshlanish) bo'yicha tezkor xulosa olishlari mumkin.

Tizim tahlil natijasini 3 ta toifadan biriga ajratadi:
1. **Yaxshi holat** — ko'rinadigan patologik belgilar aniqlanmagan.
2. **Kuzatuv talab etadi** — engil charchoq, qizarish yoki quruqlik alomatlari bor.
3. **Shifokorga murojaat qiling** — yaqqol alomatlar kuzatilib, mutaxassis ko'rigi zarur.

Har bir tekshiruv uchun amaliy profilaktik tavsiyalar beriladi va barcha yozuvlar shaxsiy kabinet tarixida saqlanadi.

> **Tibbiy eslatma:** OptiCare tashxis qo'ymaydi va shifokor ko'rigini almashtirmaydi. Natija shubhali bo'lsa, oftalmologga murojaat qiling.

---

## Tizim imkoniyatlari

- **Rasm orqali tahlil:** Smartfon kamerasidan suratga olish yoki galereyadan tanlash.
- **Xavfsiz qayta ishlash:** Rasmlardan GPS ma'lumotlari tozalanadi va xavfsiz formatda saqlanadi.
- **Natijalar tarixi:** Har bir tahlil hisoboti saqlanib, dinamikani kuzatish imkoniyati taqdim etiladi.
- **Tahliliy statistika:** Oylar bo'yicha ko'rsatkichlar va toifalar taqsimoti.
- **Moslashuvchan interfeys:** Mobil telefonlar va kompyuterlar uchun qulay boshqaruv paneli.

---

## O'rnatish va ishga tushirish

### 1. Repozitoriy papkasiga o'tish

```bash
cd opticare-ai
```

### 2. Virtual muhitni faollashtirish

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Zarur kutubxonalarni o'rnatish

```bash
pip install -r requirements.txt
```

### 4. Muhit o'zgaruvchilarini sozlash

`.env` faylini yarating va zarur kalitlarni kiriting:
```bash
cp .env.example .env
```

### 5. Ma'lumotlar bazasini tayyorlash

```bash
python manage.py migrate
```

### 6. Demo foydalanuvchini yaratish

```bash
python manage.py seed_demo
```

Login va parol `.env` dagi `DEMO_USERNAME` / `DEMO_PASSWORD` dan olinadi (standart: `admin2026` / `123456`).
Tekshiruvlar tarixi bo'sh qoladi. Namuna tekshiruvlar kerak bo'lsa: `python manage.py seed_demo --with-scans`.

### 7. Serverni ishga tushirish

```bash
python manage.py runserver
```

Brauzerda quyidagi manzilni oching: **http://127.0.0.1:8000/**

---

## Huquqlar

© 2026 OptiCare. Barcha huquqlar himoyalangan.