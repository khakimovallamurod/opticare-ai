"""
Gemini eye analysis service for OptiCare.
"""

import json
import logging
import time
from django.conf import settings

logger = logging.getLogger(__name__)

# Module-level import so tests can patch 'scans.services.gemini.genai'
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Prompt (edit this constant to adjust AI behaviour)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Siz bolalar ko'z salomatligini tahlil qilish bo'yicha AI yordamchisiz (OptiCare tizimi).
Muhim: Siz shifokor emassiz va hech qachon aniq tibbiy tashxis qo'ymaysiz.
Hech qachon kasallik nomini aniq haqiqat sifatida aytmang.
Noaniqlik bo'lsa, har doim yuqori darajadagi e'tibor sinfini tanlang (xavfsizlik printsipi).
Faqat Uzbek (lotin) tilida javob bering.
Faqat JSON formatida javob bering – boshqa matn yo'q.
"""

ANALYSIS_PROMPT_TEMPLATE = """Quyidagi rasm – bola yuzining yoki ko'z sohasining fotosuratidir.
{age_info}

VAZIFA:
1. Rasmda inson yuzi yoki ko'z sohasini aniqlang.
2. Agar rasm yaroqsiz bo'lsa (yuz/ko'z ko'rinmasa, juda xira/qorong'i bo'lsa), "valid": false qaytaring.
3. Agar rasm yaroqli bo'lsa, quyidagi JSON sxemasiga ko'ra tahlil qiling:

JSON sxemasi:
{{
  "valid": true yoki false,
  "invalid_reason": "agar valid=false bo'lsa, o'zbek tilida sabab",
  "class": "normal" | "attention" | "consult",
  "confidence": 0.0 dan 1.0 gacha float son,
  "observations": ["ko'rilgan belgi 1", "belgi 2", ...],
  "recommendations": ["tavsiya 1", "tavsiya 2", ...],
  "summary": "ota-onalar uchun 1-2 jumlali qisqacha xulosa"
}}

SINFLAR:
- "normal": ko'rinadigan patologik belgilar yo'q
- "attention": engil belgilar (biroz qizillik, quruqlik, charchash, engil shish, biroz yoshlanish, qovoq taranglanishi)
- "consult": yaqqol belgilar (kuchli qizillik, shish, ajralma, qovoq osib tushishi/ptoz, ko'z tartibsizligi/strabizm shubhasi, loyqa qorachiq, shikast)

QOIDALAR:
- Matnda "skrining", "dastlabki", "tashxis" so'zlarini ishlatmang; "tahlil", "baholash", "kuzatilmoqda" kabi neytral iboralar ishlating
- "observations": faqat ko'rinadigan belgilarni yozing, max 5 ta, o'zbek tilida
- "recommendations": 3-5 ta amaliy tavsiya, o'zbek tilida, ekran vaqti, 20-20-20 qoidasi, yorug'lik, dam olish, gigiena, shifokorga murojaat
- "summary": ota-onalar tushuna oladigan oddiy til, o'zbek tilida
- Ehtiyotkorlik bilan, "belgilar kuzatilmoqda" kabi iboralar ishlating
- Noaniq holatlarda yuqori sinf (consult) tanlang

FAQAT JSON qaytaring, boshqa matn yo'q.
"""


def _get_age_info(age):
    """Build age context string for the prompt."""
    if age:
        return f"Bolaning yoshi: {age} yosh."
    return ""


def _parse_response(text: str) -> dict:
    """Parse JSON from Gemini response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def analyze_eye_image(image_bytes: bytes, mime_type: str, age: int = None) -> dict:
    """
    Send eye image to Gemini and return structured analysis dict.

    Returns dict with keys: valid, invalid_reason, class, confidence,
    observations, recommendations, summary, raw_text.
    On error returns: {valid: False, error: True, error_message: str}
    """
    api_key = settings.GEMINI_API_KEY
    model_name = settings.GEMINI_MODEL

    if not api_key:
        logger.error("GEMINI_API_KEY sozlanmagan.")
        return {
            "valid": False,
            "error": True,
            "error_message": "AI xizmati sozlanmagan. Iltimos, administratorga murojaat qiling.",
        }

    if genai is None:
        logger.error("google-genai paketi o'rnatilmagan.")
        return {
            "valid": False,
            "error": True,
            "error_message": "AI xizmati mavjud emas. Iltimos, administratorga murojaat qiling.",
        }

    age_info = _get_age_info(age)
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(age_info=age_info)

    client = genai.Client(api_key=api_key)

    max_attempts = 3
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    genai_types.Part.from_text(text=prompt),
                ],
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )

            raw_text = response.text or ""
            result = _parse_response(raw_text)
            result["raw_text"] = raw_text

            # Validate required fields
            if "valid" not in result:
                result["valid"] = True
            if result.get("valid") and "class" not in result:
                result["class"] = "attention"

            logger.info(
                "Gemini tahlil tugadi: valid=%s, class=%s, confidence=%s",
                result.get("valid"),
                result.get("class"),
                result.get("confidence"),
            )
            return result

        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning("Gemini JSON parse xatosi (urinish %d): %s", attempt, exc)
            if attempt < max_attempts:
                time.sleep(1.5 * attempt)

        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Gemini API xatosi (urinish %d): %s", attempt, exc)
            if attempt < max_attempts:
                time.sleep(2.0 * attempt)

    logger.error("Gemini tahlili muvaffaqiyatsiz tugadi. Oxirgi xato: %s", last_error)
    return {
        "valid": False,
        "error": True,
        "error_message": (
            "AI tahlili amalga oshmadi. Internet ulanishini tekshiring va qayta urinib ko'ring. "
            f"Texnik ma'lumot: {str(last_error)[:100]}"
        ),
    }
