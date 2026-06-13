"""콘텐츠 도구 — 키워드/이미지/HTML 조립 (순수 함수, 재현 가능).

mock 번역용 glossary도 여기 둔다(translator가 import). 돈 계산은 없음 — 가격은 quote에서.
"""

from __future__ import annotations

import hashlib

MAX_TITLE_LEN = 50  # 네이버 상품명 권장 길이(전각 기준 보수적)

# mock 번역 사전 — 데모/테스트용. real 모드는 DeepL이 대체.
GLOSSARY: dict[str, str] = {
    "wireless": "무선", "earbuds": "이어폰", "headphones": "헤드폰",
    "charger": "충전기", "wall": "벽면", "usb": "USB", "fast": "고속",
    "charging": "충전", "pad": "패드", "power": "보조", "bank": "배터리",
    "studio": "스튜디오", "cotton": "면", "tote": "토트", "bag": "가방",
    "stainless": "스테인리스", "steel": "스틸", "water": "물", "bottle": "병",
    "insulated": "보온", "building": "블록", "blocks": "블록",
    "generic": "일반", "widget": "위젯", "running": "러닝", "shoes": "신발",
}


def glossary_translate(text: str) -> str:
    """사전 기반 단어별 치환(mock). 모르는 단어는 원형 유지. 결정론적."""
    out: list[str] = []
    for token in text.split():
        key = token.lower().strip(".,!?()[]")
        out.append(GLOSSARY.get(key, token))
    return " ".join(out)


def extract_keywords(category_path: list[str], translated_title: str) -> list[str]:
    """검색 키워드 추출 — 번역 제목 단어 + 카테고리. 중복 제거, 순서 보존."""
    seen: dict[str, None] = {}
    for w in translated_title.split():
        if len(w) >= 2:
            seen.setdefault(w, None)
    for c in category_path:
        seen.setdefault(c, None)
    return list(seen)[:10]


def rehost_images(image_urls: list[str]) -> list[str]:
    """원본 이미지를 자체 CDN으로 재호스팅(mock: 결정론적 URL 생성).

    실서비스: 원본 다운로드 → S3 업로드 → CDN URL. 원본 핫링크 금지(저작권).
    """
    out = []
    for url in image_urls:
        h = hashlib.md5(url.encode()).hexdigest()[:12]
        out.append(f"https://cdn.example.com/img/{h}.jpg")
    return out


def truncate_title(title: str, max_len: int = MAX_TITLE_LEN) -> str:
    return title if len(title) <= max_len else title[:max_len].rstrip()


def build_description_html(translated_title: str, translated_desc: str,
                          keywords: list[str]) -> str:
    tags = " ".join(f"#{k}" for k in keywords[:6])
    return (
        f"<h3>{translated_title}</h3>\n"
        f"<p>{translated_desc}</p>\n"
        f"<p class=\"tags\">{tags}</p>"
    )
