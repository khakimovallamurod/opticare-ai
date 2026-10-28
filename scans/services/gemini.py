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
# Urgency levels (tavsiya darajasi). Each result class allows a range of levels;
# the final level is never lower than the class minimum (safety first).
# ---------------------------------------------------------------------------
URGENCY_LEVELS = {
    "past": 1,
    "orta": 2,
    "yuqori": 3,
    "shoshilinch": 4,
}
CLASS_MIN_URGENCY = {"normal": "past", "attention": "orta", "consult": "yuqori"}
URGENCY_TO_CLASS = {"past": "normal", "orta": "attention", "yuqori": "consult", "shoshilinch": "consult"}
DEFAULT_DOCTOR_VISIT = {
    "past": "Rejali profilaktik ko'rik — yiliga 1 marta",
    "orta": "Holatni 3–7 kun kuzating; yaxshilanmasa 1–2 hafta ichida oftalmologga boring",
    "yuqori": "2–3 kun ichida bolalar oftalmologiga uchrashing",
    "shoshilinch": "Bugunoq (24 soat ichida) shifokorga yoki tez yordamga murojaat qiling",
}
RECOMMENDATION_PRIORITIES = ("muhim", "tavsiya", "qoshimcha")

# ---------------------------------------------------------------------------
# Prompt (edit these constants to adjust AI behaviour)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Siz OptiCare demo tizimining bolalar ko'z sohasini vizual baholovchi AI yordamchisisiz.
Tashxis qo'ymang, kasallik va dori nomini aytmang. Faqat rasmda ko'ringan narsani yozing.
Noaniq bo'lsa yuqoriroq sinf va darajani tanlang. Javob qisqa, o'zbek tilida (lotin), faqat JSON.
"""

ANALYSIS_PROMPT_TEMPLATE = """Rasm — bola yuzi yoki ko'z sohasi. {age_info}

Rad etish ("valid": false) faqat: rasmda yuz/ko'z yo'q, ikkala ko'z yopiq/to'silgan yoki umuman ko'rinmaydigan darajada qorong'i/xira.
Burilgan yuz, ko'zoynak, uzoqdan olingan rasm — rad etmang, ko'ringan qismni baholang va "confidence"ni pasaytiring.

Sinf va tavsiya darajasi (bir-biriga mos bo'lsin):
- "normal"    + "past"        — o'zgarish ko'rinmaydi.
- "attention" + "orta"        — engil qizarish, charchoq, quruqlik, engil shish yoki yoshlanish.
- "consult"   + "yuqori"      — kuchli qizarish, shish, yiringli ajralma, qovoq osilishi, g'ilaylik shubhasi, xiralik.
- "consult"   + "shoshilinch" — qorachiqda oq aks, shikast, kuchli shish va ko'p yiring.

Qisqa yozing: observations ko'pi bilan 3 ta, recommendations aynan 3 ta, har biri bitta qisqa jumla.
Birinchi tavsiya shifokorga borish muddati bilan bog'liq bo'lsin (normal holatda — profilaktika).

JSON:
{{
  "valid": true,
  "invalid_reason": "",
  "class": "normal|attention|consult",
  "urgency": "past|orta|yuqori|shoshilinch",
  "urgency_reason": "1 qisqa jumla",
  "doctor_visit": "aniq muddat, masalan: 2–3 kun ichida oftalmologga",
  "confidence": 0.0,
  "observations": ["..."],
  "recommendations": [{{"text": "...", "priority": "muhim|tavsiya|qoshimcha"}}],
  "summary": "1 jumla: nima ko'rindi va nima qilish kerak"
}}
"""


def _get_age_info(age):
    """Build age context string for the prompt."""
    if age:
        return f"Bolaning yoshi: {age} yosh."
    return ""


def _normalize_recommendations(items) -> list:
    """Coerce recommendations to [{text, priority}] sorted by priority."""
    normalized = []
    for item in items or []:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            priority = str(item.get("priority", "tavsiya")).strip().lower().replace("'", "")
        else:
            text = str(item).strip()
            priority = "tavsiya"
        if not text:
            continue
        if priority not in RECOMMENDATION_PRIORITIES:
            priority = "tavsiya"
        normalized.append({"text": text, "priority": priority})
    normalized.sort(key=lambda r: RECOMMENDATION_PRIORITIES.index(r["priority"]))
    return normalized[:3]


def _normalize_result(result: dict) -> dict:
    """Make class, urgency, confidence and lists consistent (safety first)."""
    if "valid" not in result:
        result["valid"] = True
    if not result.get("valid"):
        return result

    result_class = result.get("class")
    if result_class not in CLASS_MIN_URGENCY:
        result_class = "attention"

    urgency = str(result.get("urgency", "")).strip().lower().replace("'", "")
    if urgency not in URGENCY_LEVELS:
        urgency = CLASS_MIN_URGENCY[result_class]
    # Never below the class minimum; a higher urgency raises the class
    min_urgency = CLASS_MIN_URGENCY[result_class]
    if URGENCY_LEVELS[urgency] < URGENCY_LEVELS[min_urgency]:
        urgency = min_urgency
    result_class = URGENCY_TO_CLASS[urgency]

    result["class"] = result_class
    result["urgency"] = urgency
    result["urgency_level"] = URGENCY_LEVELS[urgency]
    result["doctor_visit"] = str(result.get("doctor_visit") or DEFAULT_DOCTOR_VISIT[urgency]).strip()
    result["urgency_reason"] = str(result.get("urgency_reason") or "").strip()

    try:
        confidence = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1.0:
        confidence /= 100.0
    result["confidence"] = max(0.0, min(confidence, 1.0))

    result["observations"] = [str(o).strip() for o in result.get("observations") or [] if str(o).strip()][:3]
    result["recommendations"] = _normalize_recommendations(result.get("recommendations"))
    return result


def _parse_response(text: str) -> dict:
    """Parse JSON from Gemini response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _describe_api_error(exc: Exception):
    """Return (retryable, user_message) for a Gemini API exception."""
    code = getattr(exc, "code", None)
    text = str(exc).lower()
    if code == 403 and ("billing" in text or "outstanding" in text):
        return False, (
            "AI xizmati vaqtincha ishlamayapti: Google Cloud hisobida to'lov muammosi bor. "
            "Administrator billing hisobini tekshirishi kerak."
        )
    if code in (401, 403) or "api key" in text or "api_key" in text:
        return False, "AI xizmatiga kirish rad etildi: API kalit noto'g'ri yoki ruxsat yo'q. Administratorga murojaat qiling."
    if code == 404:
        return False, "AI modeli topilmadi. Administrator GEMINI_MODEL sozlamasini tekshirishi kerak."
    if code == 400:
        return False, "AI xizmati so'rovni qabul qilmadi. Boshqa rasm bilan qayta urinib ko'ring."
    if "timeout" in text or "timed out" in text or "deadline" in text:
        return False, "AI javobi juda uzoq kechikdi. Birozdan so'ng qayta urinib ko'ring."
    if code == 429:
        return True, "AI xizmati hozir band yoki limit tugagan. Birozdan so'ng qayta urinib ko'ring."
    return True, "AI tahlili amalga oshmadi. Internet ulanishini tekshiring va qayta urinib ko'ring."


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

    client = genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(timeout=settings.GEMINI_TIMEOUT_SECONDS * 1000),
    )

    # One retry at most: the whole request must finish well within the web worker timeout
    max_attempts = 2
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
                    temperature=0.1,
                    max_output_tokens=700,
                    response_mime_type="application/json",
                    thinking_config=genai_types.ThinkingConfig(
                        thinking_level=settings.GEMINI_THINKING_LEVEL,
                    ),
                ),
            )

            raw_text = response.text or ""
            result = _parse_response(raw_text)
            result["raw_text"] = raw_text

            result = _normalize_result(result)

            logger.info(
                "Gemini tahlil tugadi: valid=%s, class=%s, urgency=%s, confidence=%s",
                result.get("valid"),
                result.get("class"),
                result.get("urgency"),
                result.get("confidence"),
            )
            return result

        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning("Gemini JSON parse xatosi (urinish %d): %s", attempt, exc)
            if attempt < max_attempts:
                time.sleep(0.5)

        except Exception as exc:  # noqa: BLE001
            last_error = exc
            retryable, error_message = _describe_api_error(exc)
            logger.warning("Gemini API xatosi (urinish %d): %s", attempt, exc)
            if not retryable:
                break
            if attempt < max_attempts:
                time.sleep(1.0)

    logger.error("Gemini tahlili muvaffaqiyatsiz tugadi. Oxirgi xato: %s", last_error)
    if isinstance(last_error, json.JSONDecodeError):
        error_message = "AI javobini o'qib bo'lmadi. Qayta urinib ko'ring."
    return {
        "valid": False,
        "error": True,
        "error_message": error_message,
        "technical_detail": str(last_error)[:300],
    }
