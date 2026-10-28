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
SYSTEM_PROMPT = """Siz OptiCare tizimining bolalar ko'z sohasini vizual baholovchi AI yordamchisisiz.
Vazifangiz — ota-onaga rasmda KO'RINADIGAN belgilar asosida tushunarli, ehtiyotkor va amaliy yo'l-yo'riq berish.

Qat'iy qoidalar:
- Siz shifokor emassiz: tashxis qo'ymang, kasallik nomini haqiqat sifatida aytmang, dori yoki tomchi nomini tavsiya qilmang.
- Faqat rasmda ko'rinib turgan narsani yozing; taxmin qilmang, ko'rinmagan belgini o'ylab topmang.
- Noaniqlik bo'lsa — yuqoriroq e'tibor sinfi va yuqoriroq tavsiya darajasini tanlang (xavfsizlik printsipi).
- Javob faqat o'zbek tilida (lotin yozuvi), sodda va ota-ona tushunadigan tilda bo'lsin.
- Faqat bitta JSON obyekt qaytaring — undan oldin yoki keyin hech qanday matn bo'lmasin.
"""

ANALYSIS_PROMPT_TEMPLATE = """Rasm — bola yuzi yoki ko'z sohasining fotosurati.
{age_info}

1-QADAM. RASM YAROQLILIGI — FAQAT JIDDIY HOLATDA RAD ETING
"valid": false FAQAT quyidagi holatlarda qaytariladi:
- rasmda inson yuzi yoki ko'z umuman yo'q (masalan, narsa, hayvon, manzara, matn);
- ikkala ko'z ham to'liq yumuq yoki to'liq to'silgan;
- rasm shunchalik qorong'i yoki xiraki, ko'z sohasini umuman ajratib bo'lmaydi.
Bunda "invalid_reason"da sababni va qanday qayta suratga olishni 1–2 jumlada yozing.

Quyidagi holatlarda rad ETMANG — tahlilni davom ettiring:
- yuz biroz burilgan, faqat bitta ko'z yaxshi ko'rinadi (ko'ringan ko'zni baholang);
- ko'zoynak, yaltirash yoki soya qisman to'sgan;
- rasm uzoqdan olingan, o'rtacha xira yoki yorug'lik ideal emas.
Bunday hollarda ko'ringan qismni baholang, "observations"ning birinchi bandida rasm sifati cheklovini qisqa yozing
(masalan: "Rasm sifati: yuz burilgan, chap ko'z to'liq ko'rinmaydi"), "confidence"ni 0.4–0.7 oralig'ida pasaytiring
va tavsiyalarga sifatliroq rasm bilan qayta tekshirishni "tavsiya" darajasida qo'shing.

2-QADAM. HAR BIR KO'ZNI TIZIMLI KO'RIB CHIQING (o'ng va chap ko'z alohida)
- Ko'z oq qismi (sklera, konyunktiva): qizarish, tomirlar ko'rinishi, sarg'ayish, qon quyilishi.
- Qovoqlar: shish, qizarish, qobiq/po'stloq, arpa ko'z kabi bo'rtma, qovoq osilishi (ptoz).
- Ajralma va yoshlanish: yiring, shilliq, ko'p yosh oqishi.
- Shox parda va qorachiq: xiralik, loyqalik, oq dog', qorachiqda oq yoki kulrang aks (leykokoriya), qorachiqlar o'lchami farqi.
- Ko'zlar simmetriyasi va qarash yo'nalishi: bir ko'z boshqa tomonga qarashi (g'ilaylik shubhasi).
- Shikast belgilari: tirnalish, ko'kargan joy, begona jism.

3-QADAM. NATIJA SINFI ("class")
- "normal": ko'rinadigan o'zgarish yo'q.
- "attention": engil, xavfsiz ko'rinadigan belgilar — engil qizarish, charchoq, quruqlik, engil shish yoki yoshlanish.
- "consult": yaqqol belgilar — kuchli qizarish, sezilarli shish, yiringli ajralma, ptoz, g'ilaylik shubhasi, shox parda xiraligi, shikast.

4-QADAM. TAVSIYA DARAJASI ("urgency") — ANIQ VA BIR XIL BELGILANG
- "past"        — 1-daraja. Faqat "normal" sinf. Profilaktika yetarli, yiliga 1 marta rejali ko'rik.
- "orta"        — 2-daraja. Faqat "attention" sinf. Uyda kuzatish, 1–2 hafta ichida yaxshilanmasa shifokorga.
- "yuqori"      — 3-daraja. "consult" sinf. 2–3 kun ichida bolalar oftalmologiga.
- "shoshilinch" — 4-daraja. "consult" sinf + xavfli belgi: qorachiqda oq aks, ko'z shikasti/begona jism,
                  ko'z atrofida kuchli shish va qizarish, ko'p yiringli ajralma, to'satdan paydo bo'lgan g'ilaylik yoki ptoz.
                  Bugunoq (24 soat ichida) shifokorga.
"urgency_reason"da aynan qaysi kuzatilgan belgi sababli shu daraja tanlanganini 1 jumlada yozing.
"doctor_visit"da shifokorga qachon borish kerakligini aniq muddat bilan yozing (masalan: "2–3 kun ichida bolalar oftalmologiga").

5-QADAM. TAVSIYALAR ("recommendations") — 3 tadan 6 tagacha
Har bir tavsiya obyekt: {{"text": "...", "priority": "muhim" | "tavsiya" | "qoshimcha"}}
- "muhim"     — darhol bajarilishi kerak bo'lgan qadam (2–4 daraja uchun birinchi tavsiya doim shifokor bilan bog'liq va muddatli bo'lsin).
- "tavsiya"   — kundalik parvarish va kuzatish bo'yicha amaliy qadam.
- "qoshimcha" — profilaktik maslahat (ekran vaqti, 20-20-20 qoidasi, yorug'lik, uyqu, ovqatlanish, gigiena).
Tavsiyalar aniq bo'lsin: nima qilish, qancha vaqt, nimaga e'tibor berish. Umumiy gaplardan qoching.
Muhimlik bo'yicha tartiblang: avval "muhim", keyin "tavsiya", oxirida "qoshimcha".
Holat yomonlashsa nima qilishni ham yozing (masalan: "Og'riq, ko'rish xiralashishi yoki shish kuchaysa — zudlik bilan shifokorga").

6-QADAM. ISHONCH ("confidence")
0.0–1.0. Rasm sifati, yorug'lik va ikkala ko'z ko'rinishiga qarab baholang. Rasm o'rtacha bo'lsa 0.75 dan oshirmang.

JAVOB SXEMASI (faqat shu JSON):
{{
  "valid": true,
  "invalid_reason": "",
  "class": "normal" | "attention" | "consult",
  "urgency": "past" | "orta" | "yuqori" | "shoshilinch",
  "urgency_reason": "tanlangan daraja sababi, 1 jumla",
  "doctor_visit": "shifokorga borish muddati",
  "confidence": 0.0,
  "observations": ["o'ng ko'z: ...", "chap ko'z: ...", "..."],
  "recommendations": [{{"text": "...", "priority": "muhim"}}],
  "summary": "ota-ona uchun 2 jumla: nima ko'rindi va hozir nima qilish kerak"
}}

USLUB:
- "skrining", "dastlabki", "tashxis" so'zlarini ishlatmang; "kuzatilmoqda", "belgilar ko'rinmoqda" kabi neytral iboralar ishlating.
- "observations": faqat ko'rinadigan belgilar, eng ko'pi 5 ta; normal holatda ham nima tekshirilganini qisqa yozing.
- Ota-onani qo'rqitmang, lekin xavfli belgini yashirmang.
"""


def _get_age_info(age):
    """Build age context string for the prompt."""
    if age:
        return f"Bolaning yoshi: {age} yosh. Tavsiyalarni shu yoshga moslang."
    return "Bolaning yoshi ko'rsatilmagan."


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
    return normalized[:6]


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

    result["observations"] = [str(o).strip() for o in result.get("observations") or [] if str(o).strip()][:5]
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
                    temperature=0.1,
                    response_mime_type="application/json",
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
                time.sleep(1.5 * attempt)

        except Exception as exc:  # noqa: BLE001
            last_error = exc
            retryable, error_message = _describe_api_error(exc)
            logger.warning("Gemini API xatosi (urinish %d): %s", attempt, exc)
            if not retryable:
                break
            if attempt < max_attempts:
                time.sleep(2.0 * attempt)

    logger.error("Gemini tahlili muvaffaqiyatsiz tugadi. Oxirgi xato: %s", last_error)
    if isinstance(last_error, json.JSONDecodeError):
        error_message = "AI javobini o'qib bo'lmadi. Qayta urinib ko'ring."
    return {
        "valid": False,
        "error": True,
        "error_message": error_message,
        "technical_detail": str(last_error)[:300],
    }
