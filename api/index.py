from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import date, datetime, timedelta
import requests

app = FastAPI(
    title="AstroAgent MVP API (Vercel)",
    version="1.0.0",
    description="Ежедневный персональный прогноз: западная астрология (Aztro) + простые правила ведической/нумерологии, RU/EN."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # для MVP; позже можно ограничить доменом сайта
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PredictRequest(BaseModel):
    name: str = Field(..., description="Имя пользователя")
    birth_date: date = Field(..., description="YYYY-MM-DD")
    birth_time: Optional[str] = Field(None, description="HH:MM (опционально)")
    birth_place: Optional[str] = Field(None, description="Место рождения (опционально)")
    language: str = Field("ru", pattern="^(ru|en)$", description="Язык ответа: ru | en")
    sign: Optional[str] = Field(None, description="Знак зодиака (en/ru). Если не передан — определим по дате рождения.")

class LuckyDate(BaseModel):
    iso: str
    human: str
    reason: str

class PredictResponse(BaseModel):
    date: str
    user: Dict[str, str]
    zodiac: Dict[str, str]
    sources: Dict[str, str]
    forecast: Dict[str, str]
    lucky_dates: List[LuckyDate]
    questions: List[str]

ZODIAC_EN_RU = {
    "aries": "Овен", "taurus": "Телец", "gemini": "Близнецы", "cancer": "Рак",
    "leo": "Лев", "virgo": "Дева", "libra": "Весы", "scorpio": "Скорпион",
    "sagittarius": "Стрелец", "capricorn": "Козерог", "aquarius": "Водолей", "pisces": "Рыбы",
}
ZODIAC_RU_EN = {v.lower(): k for k, v in ZODIAC_EN_RU.items()}

FAVORABLE_WEEKDAYS = {
    "aries": [1], "taurus": [4], "gemini": [2], "cancer": [0], "leo": [6],
    "virgo": [2], "libra": [4], "scorpio": [1], "sagittarius": [3],
    "capricorn": [5], "aquarius": [5], "pisces": [3],
}
WEEKDAY_NAMES_RU = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
WEEKDAY_NAMES_EN = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

ADVICE_BANK = {
    "ru": {
        "work": [
            "Сфокусируйтесь на одном приоритетном деле и доведите его до результата.",
            "Завершите начатые задачи — новые начинания перенесите на вторую половину дня.",
            "Согласуйте ожидания с коллегами письменным списком из 3 пунктов."
        ],
        "love": [
            "Назовите партнёру одну вещь, за которую вы сегодня благодарны.",
            "Избегайте резких формулировок — уточняйте намерения вопросами.",
            "Планируйте короткую совместную активность (30–40 минут) вечером."
        ],
        "energy": [
            "Сделайте 10‑минутную прогулку без телефона для перезагрузки.",
            "Выпейте чистой воды и сделайте лёгкую разминку спины и шеи.",
            "Отключите уведомления на 45 минут и поработайте в глубоком фокусе."
        ],
    },
    "en": {
        "work": [
            "Pick one priority and finish it before lunch.",
            "Close ongoing tasks; start new ones in the afternoon.",
            "Align expectations with a 3‑point written checklist."
        ],
        "love": [
            "Tell your partner one thing you’re grateful for today.",
            "Avoid sharp wording — clarify intentions with questions.",
            "Plan a short 30–40 min shared activity in the evening."
        ],
        "energy": [
            "Take a 10‑minute phone‑free walk to reset.",
            "Drink water and do a light neck & back stretch.",
            "Mute notifications for 45 minutes of deep focus."
        ],
    }
}

def zodiac_from_date(d: date) -> str:
    y = d.year
    ranges = [
        ("capricorn",  (date(y,12,22), date(y+1,1,19))),
        ("aquarius",   (date(y,1,20),  date(y,2,18))),
        ("pisces",     (date(y,2,19),  date(y,3,20))),
        ("aries",      (date(y,3,21),  date(y,4,19))),
        ("taurus",     (date(y,4,20),  date(y,5,20))),
        ("gemini",     (date(y,5,21),  date(y,6,20))),
        ("cancer",     (date(y,6,21),  date(y,7,22))),
        ("leo",        (date(y,7,23),  date(y,8,22))),
        ("virgo",      (date(y,8,23),  date(y,9,22))),
        ("libra",      (date(y,9,23),  date(y,10,22))),
        ("scorpio",    (date(y,10,23), date(y,11,21))),
        ("sagittarius",(date(y,11,22), date(y,12,21))),
    ]
    for sign, (start, end) in ranges:
        if start.month == 12:
            if d >= start or d <= end:
                return sign
        else:
            if start <= d <= end:
                return sign
    return "capricorn"

def normalize_sign(s: Optional[str], d: date) -> str:
    if not s or not s.strip():
        return zodiac_from_date(d)
    s_low = s.strip().lower()
    if s_low in ZODIAC_EN_RU:
        return s_low
    if s_low in ZODIAC_RU_EN:
        return ZODIAC_RU_EN[s_low]
    s_low = s_low.replace("ё","е").replace(" ","")
    if s_low in ZODIAC_RU_EN:
        return ZODIAC_RU_EN[s_low]
    raise HTTPException(status_code=400, detail="Unknown zodiac sign")

def reduce_digit_sum(n: int) -> int:
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n

def weekday_name(idx: int, lang: str) -> str:
    return WEEKDAY_NAMES_RU[idx] if lang == "ru" else WEEKDAY_NAMES_EN[idx]

def lucky_dates(bd: date, sign_en: str, lang: str, count: int = 3) -> List[LuckyDate]:
    lp = reduce_digit_sum(bd.year) + reduce_digit_sum(bd.month) + reduce_digit_sum(bd.day)
    fav_wd = set(FAVORABLE_WEEKDAYS.get(sign_en, []))
    today = date.today()
    found: List[LuckyDate] = []
    i = 1
    while len(found) < count and i <= 90:
        day = today + timedelta(days=i)
        ds = reduce_digit_sum(day.day + day.month)
        reason = None
        if ds == reduce_digit_sum(lp):
            reason = "Нумерология совпала" if lang == "ru" else "Numerology match"
        if reason is None and day.weekday() in fav_wd:
            reason = "Благоприятный день недели" if lang == "ru" else "Favorable weekday"
        if reason:
            human = f"{day.strftime('%d.%m.%Y')} ({weekday_name(day.weekday(), lang)})"
            found.append(LuckyDate(iso=day.isoformat(), human=human, reason=reason))
        i += 1
    return found

def pick_advice(lang: str) -> Dict[str, str]:
    import random
    bank = ADVICE_BANK[lang]
    return {"work":random.choice(bank["work"]),
            "love":random.choice(bank["love"]),
            "energy":random.choice(bank["energy"])}

def get_western_horoscope_aztro(sign_en: str) -> Optional[Dict[str, str]]:
    url = "https://aztro.sameerkumar.website/"
    try:
        r = requests.post(url, params={"sign": sign_en, "day": "today"}, timeout=8)
        if r.status_code == 200:
            data = r.json()
            return {
                "summary": data.get("description", ""),
                "compatibility": data.get("compatibility", ""),
                "mood": data.get("mood", ""),
                "color": data.get("color", ""),
                "lucky_number": str(data.get("lucky_number", "")),
                "lucky_time": data.get("lucky_time", ""),
            }
        return None
    except requests.RequestException:
        return None

def local_summary(lang: str, sign_en: str) -> str:
    return ("День подходит для аккуратного продвижения в делах и спокойного общения."
            if lang == "ru"
            else "A steady day for focused progress and calm communication.")

@app.get("/health")
def health():
    return {"ok": True, "timestamp": datetime.utcnow().isoformat() + "Z"}

@app.get("/zodiac")
def zodiac(birth_date: date = Query(..., description="YYYY-MM-DD"), lang: str = Query("ru", pattern="^(ru|en)$")):
    sign_en = zodiac_from_date(birth_date)
    sign_ru = ZODIAC_EN_RU[sign_en]
    return {"sign_en": sign_en, "sign_ru": sign_ru if lang == "ru" else sign_en}

@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    sign_en = normalize_sign(req.sign, req.birth_date)
    sign_ru = ZODIAC_EN_RU[sign_en]
    west = get_western_horoscope_aztro(sign_en)
    summary = west["summary"] if (west and west.get("summary")) else local_summary(req.language, sign_en)
    adv = pick_advice(req.language)
    lucky = lucky_dates(req.birth_date, sign_en, req.language, count=3)
    questions_ru = [
        "Какую одну цель вы хотите продвинуть сегодня?",
        "Что поможет улучшить отношения/коммуникацию на этой неделе?",
        "Когда вам удобнее начать новый проект в ближайшие 7 дней?"
    ]
    questions_en = [
        "What’s the one goal you want to move today?",
        "What would improve your relationships/communication this week?",
        "When is the best moment to start a new project within 7 days?"
    ]
    qs = questions_ru if req.language == "ru" else questions_en
    return PredictResponse(
        date=date.today().isoformat(),
        user={"name": req.name, "language": req.language},
        zodiac={"en": sign_en, "ru": sign_ru},
        sources={
            "western": "Aztro (public API, daily); fallback: local",
            "vedic": "Simple favorable weekday heuristic",
            "numerology": "Digit-sum life path & date match"
        },
        forecast={"summary": summary, "work": adv["work"], "love": adv["love"], "energy": adv["energy"]},
        lucky_dates=lucky,
        questions=qs
    )
