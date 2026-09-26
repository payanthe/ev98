from sqlalchemy import select

from app.models.entities import SourceSystem

SOURCES = (
    {
        "code": "ocm",
        "name": "Open Charge Map",
        "source_type": "aggregator",
        "base_url": "https://api.openchargemap.io/v3",
        "trust_level": 70,
        "attribution_text": "داده‌ها از Open Charge Map. هر POI مجوز ارائه‌دهندهٔ خودش را دارد.",
    },
    {
        "code": "abrp",
        "name": "ABRP",
        "source_type": "aggregator",
        "base_url": "https://api.iternio.com",
        "trust_level": 55,
        "attribution_text": "داده‌ها از ABRP / Iternio. پیوند source=ocm یک مکان تکراری نمی‌سازد.",
    },
    {
        "code": "sharinet",
        "name": "شارینت",
        "source_type": "cpo",
        "base_url": "https://gen.emapna.com",
        "trust_level": 80,
        "attribution_text": "دادهٔ ایستگاه، کانکتور، قیمت مشاهده‌شده و وضعیت از شارینت (مپنا).",
    },
)


def ensure_sources(session) -> None:
    for item in SOURCES:
        current = session.scalar(select(SourceSystem).where(SourceSystem.code == item["code"]))
        if current is None:
            session.add(SourceSystem(**item, active=True))
            continue
        current.name = item["name"]
        current.source_type = item["source_type"]
        current.base_url = item["base_url"]
        current.trust_level = item["trust_level"]
        current.attribution_text = item["attribution_text"]
        current.active = True
