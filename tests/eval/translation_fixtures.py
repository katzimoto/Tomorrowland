"""Translation benchmark fixture cases (#732).

Each fixture is a dict with required fields:
    id: str           — unique case identifier
    category: str     — eval category (see TRANSLATION_CATEGORIES)
    source_lang: str  — ISO 639-1 source language code
    target_lang: str  — ISO 639-1 target language code (default "en")
    source_text: str  — text to translate
    notes: str        — human-readable description
    tags: list[str]   — optional tags for filtering

Expected-preservation fields (optional):
    expected_placeholders: list[str]
        — substrings that MUST appear unchanged in the translation
          (URLs, emails, document IDs, version numbers, etc.)
    expected_numbers: list[str]
        — numeric substrings that MUST appear in the translation
          (may be reformatted as locale-appropriate, e.g. 8.3 → 8,3)
    expected_tokens_min: int
        — minimum expected token count in the output (detects catastrophic
          truncation or empty-output bugs)
    source_language_expected: str | None
        — expected detected language (ISO 639-1), or None to skip check
    allows_fast_baseline: bool
        — whether the fast (LibreTranslate/Argos) provider is expected to
          handle this pair. Default True.

Add new cases by appending to TRANSLATION_EVAL_CASES.
Each case must have a unique ``id``.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "translation"

TRANSLATION_CATEGORIES = [
    "placeholder_preservation",
    "number_preservation",
    "language_detection",
    "search_impact_smoke",
    "low_quality_text",
    "table_like_text",
    "document_section",
    "locale_formatting",
]

TRANSLATION_EVAL_CASES: list[dict] = [
    # ==================================================================
    # Hebrew → English
    # ==================================================================
    {
        "id": "tr-he-001-placeholders",
        "category": "placeholder_preservation",
        "source_lang": "he",
        "target_lang": "en",
        "source_text": (
            "לפרטים נוספים אנא בקרו בכתובת https://portal.company.co.il/products/new-2026\n"
            "או צרו קשר במייל alon.cohen@company.co.il בטלפון 03-555-0123.\n"
            "מזהה מסמך: Q4-2025-FIN-HE-001, גרסה: 2.1"
        ),
        "notes": (
            "Hebrew text with URL, email, phone, document ID, and version number. "
            "All placeholders must survive translation intact."
        ),
        "tags": ["hebrew", "placeholders"],
        "expected_placeholders": [
            "https://portal.company.co.il/products/new-2026",
            "alon.cohen@company.co.il",
            "03-555-0123",
            "Q4-2025-FIN-HE-001",
            "2.1",
        ],
        "expected_numbers": ["2.1"],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-he-002-numbers",
        "category": "number_preservation",
        "source_lang": "he",
        "target_lang": "en",
        "source_text": (
            'הכנסות: 12,450,000 ש"ח. עלייה של 8.3% לעומת הרבעון המקביל.\n'
            'רווח תפעולי: 3,200,000 ש"ח. יחידות שנמכרו: 5,800.'
        ),
        "notes": (
            "Hebrew financial figures. Numbers must be preserved, possibly "
            "reformatted (12,450,000 may become 12,450,000 or 12450000). "
            "Percentage (8.3%) and currency amounts must survive."
        ),
        "tags": ["hebrew", "numbers"],
        "expected_numbers": [
            "12,450,000",
            "8.3",
            "3,200,000",
            "5,800",
        ],
        "expected_tokens_min": 10,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-he-003-enterprise",
        "category": "document_section",
        "source_lang": "he",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "hebrew_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Hebrew enterprise document. Tests end-to-end section-aware "
            "translation with mixed numeric/currency formats, URLs, emails, "
            "and document metadata."
        ),
        "tags": ["hebrew", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.co.il/products/new-2026",
            "alon.cohen@company.co.il",
            "Q4-2025-FIN-HE-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Chinese → English
    # ==================================================================
    {
        "id": "tr-zh-001-placeholders",
        "category": "placeholder_preservation",
        "source_lang": "zh",
        "target_lang": "en",
        "source_text": (
            "详情见 https://portal.company.cn/products/new-2026，\n"
            "或发送邮件至 zhang.wei@company.cn，电话 010-5555-0123。\n"
            "文档编号：Q4-2025-FIN-CN-001，版本号：2.1"
        ),
        "notes": (
            "Chinese text with URL, email, phone, document ID, and version number. "
            "All placeholders must survive translation intact."
        ),
        "tags": ["chinese", "placeholders"],
        "expected_placeholders": [
            "https://portal.company.cn/products/new-2026",
            "zhang.wei@company.cn",
            "010-5555-0123",
            "Q4-2025-FIN-CN-001",
            "2.1",
        ],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-zh-002-numbers",
        "category": "number_preservation",
        "source_lang": "zh",
        "target_lang": "en",
        "source_text": (
            "收入：人民币124,500,000元，同比增长8.3%，营业利润32,000,000元。\n"
            "北美：4,200,000美元（5,800台），欧洲：3,100,000欧元（4,200台）。"
        ),
        "notes": (
            "Chinese financial figures with mixed currencies (CNY, USD, EUR, JPY). "
            "Numbers must survive translation; currency labels may be translated."
        ),
        "tags": ["chinese", "numbers"],
        "expected_numbers": [
            "124,500,000",
            "8.3",
            "32,000,000",
            "4,200,000",
            "5,800",
            "3,100,000",
            "4,200",
        ],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-zh-003-enterprise",
        "category": "document_section",
        "source_lang": "zh",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "chinese_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Chinese enterprise document with mixed numeric/currency formats, "
            "URLs, emails, and document metadata."
        ),
        "tags": ["chinese", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.cn/products/new-2026",
            "zhang.wei@company.cn",
            "Q4-2025-FIN-CN-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Arabic → English
    # ==================================================================
    {
        "id": "tr-ar-001-placeholders",
        "category": "placeholder_preservation",
        "source_lang": "ar",
        "target_lang": "en",
        "source_text": (
            "يرجى زيارة الرابط https://portal.company.sa/products/new-2026\n"
            "أو التواصل عبر البريد الإلكتروني ahmed.ali@company.sa\n"
            "على الرقم 011-555-0123. معرف المستند: Q4-2025-FIN-SA-001، الإصدار: 2.1"
        ),
        "notes": (
            "Arabic text with URL, email, phone, document ID, and version number. "
            "All placeholders must survive translation intact."
        ),
        "tags": ["arabic", "placeholders"],
        "expected_placeholders": [
            "https://portal.company.sa/products/new-2026",
            "ahmed.ali@company.sa",
            "011-555-0123",
            "Q4-2025-FIN-SA-001",
            "2.1",
        ],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-ar-002-numbers",
        "category": "number_preservation",
        "source_lang": "ar",
        "target_lang": "en",
        "source_text": (
            "الإيرادات: 124,500,000 ريال سعودي، زيادة 8.3%.\n"
            "الربح التشغيلي: 32,000,000 ريال. الوحدات: 5,800."
        ),
        "notes": (
            "Arabic financial figures. Numbers must be preserved. "
            "Currency labels (ريال سعودي → Saudi Riyal) may be translated."
        ),
        "tags": ["arabic", "numbers"],
        "expected_numbers": [
            "124,500,000",
            "8.3",
            "32,000,000",
            "5,800",
        ],
        "expected_tokens_min": 10,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-ar-003-enterprise",
        "category": "document_section",
        "source_lang": "ar",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "arabic_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Arabic enterprise document with mixed numeric/currency formats, "
            "URLs, emails, and document metadata. RTL text handling."
        ),
        "tags": ["arabic", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.sa/products/new-2026",
            "ahmed.ali@company.sa",
            "Q4-2025-FIN-SA-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Russian → English
    # ==================================================================
    {
        "id": "tr-ru-001-placeholders",
        "category": "placeholder_preservation",
        "source_lang": "ru",
        "target_lang": "en",
        "source_text": (
            "Подробнее: https://portal.company.ru/products/new-2026\n"
            "эл. почта: ivan.petrov@company.ru, тел. +7 (495) 555-01-23.\n"
            "Идентификатор документа: Q4-2025-FIN-RU-001, Версия: 2.1"
        ),
        "notes": (
            "Russian text with URL, email, international phone, document ID, "
            "and version number. All placeholders must survive translation intact."
        ),
        "tags": ["russian", "placeholders"],
        "expected_placeholders": [
            "https://portal.company.ru/products/new-2026",
            "ivan.petrov@company.ru",
            "+7 (495) 555-01-23",
            "Q4-2025-FIN-RU-001",
            "2.1",
        ],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-ru-002-numbers",
        "category": "number_preservation",
        "source_lang": "ru",
        "target_lang": "en",
        "source_text": (
            "Выручка: 124 500 000 руб. Рост на 8,3%.\nПрибыль: 32 000 000 руб. Продано: 5 800 шт."
        ),
        "notes": (
            "Russian financial figures with space-separated thousands. "
            "Numbers must be preserved; thousand separators may be reformatted."
        ),
        "tags": ["russian", "numbers"],
        "expected_numbers": ["8,3"],
        "expected_tokens_min": 10,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-ru-003-enterprise",
        "category": "document_section",
        "source_lang": "ru",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "russian_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Russian enterprise document with Cyrillic text, mixed numeric/"
            "currency formats, URLs, emails, and document metadata."
        ),
        "tags": ["russian", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.ru/products/new-2026",
            "ivan.petrov@company.ru",
            "Q4-2025-FIN-RU-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # French + Spanish → English
    # ==================================================================
    {
        "id": "tr-fr-001-enterprise",
        "category": "document_section",
        "source_lang": "fr",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "french_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full French enterprise document. Tests Latin-script translation "
            "with accented characters, locale-specific number formatting, and "
            "embedded URLs/emails."
        ),
        "tags": ["french", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.fr/products/new-2026",
            "marie.dubois@company.fr",
            "Q4-2025-FIN-FR-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-es-001-enterprise",
        "category": "document_section",
        "source_lang": "es",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "spanish_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Spanish enterprise document. Tests Latin-script translation "
            "with accented characters, European number formatting, and embedded "
            "URLs/emails."
        ),
        "tags": ["spanish", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.es/products/new-2026",
            "maria.garcia@company.es",
            "Q4-2025-FIN-ES-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Persian → English (NEW: user request)
    # ==================================================================
    {
        "id": "tr-fa-001-placeholders",
        "category": "placeholder_preservation",
        "source_lang": "fa",
        "target_lang": "en",
        "source_text": (
            "لطفاً به آدرس https://portal.company.ir/products/new-2026 مراجعه کنید\n"
            "یا با ایمیل ali.mohammadi@company.ir تماس بگیرید. تلفن ۰۲۱-۵۵۵۰-۰۱۲۳.\n"
            "شناسه سند: Q4-2025-FIN-IR-001، نسخه: ۲.۱"
        ),
        "notes": (
            "Persian text with URL, email, phone, document ID, and version number. "
            "RTL script with Arabic-derived characters."
        ),
        "tags": ["persian", "placeholders", "rtl"],
        "expected_placeholders": [
            "https://portal.company.ir/products/new-2026",
            "ali.mohammadi@company.ir",
            "Q4-2025-FIN-IR-001",
        ],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-fa-002-enterprise",
        "category": "document_section",
        "source_lang": "fa",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "persian_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Persian enterprise document. RTL script, Persian numerals, "
            "mixed currency formats, URLs, and emails."
        ),
        "tags": ["persian", "enterprise", "full", "rtl"],
        "expected_placeholders": [
            "https://portal.company.ir/products/new-2026",
            "ali.mohammadi@company.ir",
            "Q4-2025-FIN-IR-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Turkish → English (NEW: user request)
    # ==================================================================
    {
        "id": "tr-tr-001-placeholders",
        "category": "placeholder_preservation",
        "source_lang": "tr",
        "target_lang": "en",
        "source_text": (
            "Detaylar için https://portal.company.com.tr/products/new-2026 adresini ziyaret edin\n"
            "veya mehmet.yilmaz@company.com.tr adresine e-posta gönderin. Tel: 0212 555 01 23.\n"
            "Belge Kimli\u011fi: Q4-2025-FIN-TR-001, Sürüm: 2.1"
        ),
        "notes": (
            "Turkish text with URL, email, phone, document ID, and version number. "
            "Latin script with Turkish-specific characters (ı, ş, ğ, ü, ö, ç)."
        ),
        "tags": ["turkish", "placeholders"],
        "expected_placeholders": [
            "https://portal.company.com.tr/products/new-2026",
            "mehmet.yilmaz@company.com.tr",
            "Q4-2025-FIN-TR-001",
            "2.1",
        ],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-tr-002-enterprise",
        "category": "document_section",
        "source_lang": "tr",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "turkish_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Turkish enterprise document. Latin script with Turkish-specific "
            "characters, mixed currency formats, URLs, and emails."
        ),
        "tags": ["turkish", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.com.tr/products/new-2026",
            "mehmet.yilmaz@company.com.tr",
            "Q4-2025-FIN-TR-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Korean → English (NEW: user request)
    # ==================================================================
    {
        "id": "tr-ko-001-placeholders",
        "category": "placeholder_preservation",
        "source_lang": "ko",
        "target_lang": "en",
        "source_text": (
            "자세한 내용은 https://portal.company.kr/products/new-2026을 방문하시거나\n"
            "minjun.kim@company.kr로 이메일을 보내주세요. 전화 02-5550-0123.\n"
            "문서 ID: Q4-2025-FIN-KR-001, 버전: 2.1"
        ),
        "notes": (
            "Korean text with URL, email, phone, document ID, and version number. "
            "Hangul script with mixed alphanumeric identifiers."
        ),
        "tags": ["korean", "placeholders"],
        "expected_placeholders": [
            "https://portal.company.kr/products/new-2026",
            "minjun.kim@company.kr",
            "Q4-2025-FIN-KR-001",
            "2.1",
        ],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-ko-002-enterprise",
        "category": "document_section",
        "source_lang": "ko",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "korean_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Korean enterprise document. Hangul script, mixed currency formats, "
            "URLs, emails, and document metadata."
        ),
        "tags": ["korean", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.kr/products/new-2026",
            "minjun.kim@company.kr",
            "Q4-2025-FIN-KR-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Japanese → English (NEW: user request)
    # ==================================================================
    {
        "id": "tr-ja-001-placeholders",
        "category": "placeholder_preservation",
        "source_lang": "ja",
        "target_lang": "en",
        "source_text": (
            "詳細は https://portal.company.jp/products/new-2026 をご覧いただくか、\n"
            "taro.tanaka@company.jp までメールでお問い合わせください。電話 03-5550-0123。\n"
            "文書ID: Q4-2025-FIN-JP-001、バージョン: 2.1"
        ),
        "notes": (
            "Japanese text with URL, email, phone, document ID, and version number. "
            "Mixed kanji/kana script with embedded Latin alphanumeric identifiers."
        ),
        "tags": ["japanese", "placeholders"],
        "expected_placeholders": [
            "https://portal.company.jp/products/new-2026",
            "taro.tanaka@company.jp",
            "Q4-2025-FIN-JP-001",
            "2.1",
        ],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-ja-002-enterprise",
        "category": "document_section",
        "source_lang": "ja",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "japanese_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Japanese enterprise document. Mixed kanji/kana script, "
            "currency formats (JPY), URLs, emails, and document metadata."
        ),
        "tags": ["japanese", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.jp/products/new-2026",
            "taro.tanaka@company.jp",
            "Q4-2025-FIN-JP-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Italian → English (NEW: user request)
    # ==================================================================
    {
        "id": "tr-it-001-enterprise",
        "category": "document_section",
        "source_lang": "it",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "italian_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Italian enterprise document. Latin script with accented "
            "characters, European number formatting, URLs, and emails."
        ),
        "tags": ["italian", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.it/products/new-2026",
            "marco.rossi@company.it",
            "Q4-2025-FIN-IT-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Portuguese → English (NEW: user request)
    # ==================================================================
    {
        "id": "tr-pt-001-enterprise",
        "category": "document_section",
        "source_lang": "pt",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "portuguese_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Portuguese enterprise document. Latin script with accented "
            "characters, European number formatting, URLs, and emails."
        ),
        "tags": ["portuguese", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.pt/products/new-2026",
            "joao.silva@company.pt",
            "Q4-2025-FIN-PT-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Dutch → English (NEW: user request)
    # ==================================================================
    {
        "id": "tr-nl-001-enterprise",
        "category": "document_section",
        "source_lang": "nl",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "dutch_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Dutch enterprise document. Latin script, European number "
            "formatting with dots as thousands separators, URLs, and emails."
        ),
        "tags": ["dutch", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.nl/products/new-2026",
            "jan.devries@company.nl",
            "Q4-2025-FIN-NL-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Polish → English (NEW: user request)
    # ==================================================================
    {
        "id": "tr-pl-001-enterprise",
        "category": "document_section",
        "source_lang": "pl",
        "target_lang": "en",
        "source_text": (FIXTURES_DIR / "polish_enterprise.txt").read_text(encoding="utf-8"),
        "notes": (
            "Full Polish enterprise document. Latin script with Polish-specific "
            "characters (ą, ę, ś, ć, ń, ó, ż, ź, ł), European number formatting."
        ),
        "tags": ["polish", "enterprise", "full"],
        "expected_placeholders": [
            "https://portal.company.pl/products/new-2026",
            "anna.kowalska@company.pl",
            "Q4-2025-FIN-PL-001",
        ],
        "expected_tokens_min": 30,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Low-quality / OCR-damaged text
    # ==================================================================
    {
        "id": "tr-lq-001-ocr-damage",
        "category": "low_quality_text",
        "source_lang": "en",
        "target_lang": "fr",
        "source_text": (FIXTURES_DIR / "lowquality_ocr_english.txt").read_text(encoding="utf-8"),
        "notes": (
            "OCR-damaged English text with 0/O substitutions, spacing errors, "
            "and line noise. Tests translation robustness against low-quality "
            "input. Both providers must not crash or return empty output."
        ),
        "tags": ["low-quality", "ocr", "robustness"],
        "expected_tokens_min": 20,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-lq-002-mixed-scripts",
        "category": "low_quality_text",
        "source_lang": "en",
        "target_lang": "en",
        "source_text": (
            "The rεpοrt (that's Greek epsilon and omicron snuck in) cοntains "
            "mixed-script chαrαcters designed to test hοw the translator handles "
            "nοn-stαndard input. Th1s 1s a c0mm0n pr0blem in scαnned d0cuments "
            "where 0CR c0nfuses l (el) w1th 1 (one) and 0 (zero) w1th O (oh)."
        ),
        "notes": (
            "Mixed-script text with lookalike characters. Tests that the "
            "translator doesn't crash or produce empty output on confusable input. "
            "Target lang is 'en' (same as source) to test identity/no-op behaviour."
        ),
        "tags": ["low-quality", "mixed-script", "robustness"],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Table-like text
    # ==================================================================
    {
        "id": "tr-tb-001-table-mixed",
        "category": "table_like_text",
        "source_lang": "en",
        "target_lang": "he",
        "source_text": (
            "Quarterly Sales by Region\n"
            "=============================\n"
            "Region          | Revenue (USD) | Units Sold | Growth %\n"
            "----------------|---------------|------------|----------\n"
            "North America   |  4,200,000.00 |      5,800 |     4.2%\n"
            "Europe          |  3,100,000.00 |      4,200 |    -1.3%\n"
            "Asia-Pacific    |  2,800,000.00 |      3,100 |    12.7%\n"
            "Latin America   |    950,000.00 |      1,400 |     8.9%\n"
            "----------------|---------------|------------|----------\n"
            "TOTAL           | 11,050,000.00 |     14,500 |     5.2%"
        ),
        "notes": (
            "Table-like text with ASCII borders, column headers, and numeric data. "
            "All numeric values and region names must survive translation. "
            "Table structure (alignment, separators) may not be preserved."
        ),
        "tags": ["table", "numbers", "hebrew"],
        "expected_numbers": [
            "4,200,000.00",
            "5,800",
            "4.2",
            "3,100,000.00",
            "4,200",
            "-1.3",
            "2,800,000.00",
            "3,100",
            "12.7",
            "950,000.00",
            "1,400",
            "8.9",
            "11,050,000.00",
            "14,500",
            "5.2",
        ],
        "expected_tokens_min": 25,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Locale formatting (number/decimal separators)
    # ==================================================================
    {
        "id": "tr-lc-001-locale-numbers",
        "category": "locale_formatting",
        "source_lang": "fr",
        "target_lang": "en",
        "source_text": (
            "Chiffre d'affaires : 124 500 000,00 €\n"
            "Croissance : 8,3 % (contre 12,7 % l'année précédente)\n"
            "Effectif : 1 250 employés (augmentation de 3,5 %)\n"
            "Marge brute : 23,8 % du CA"
        ),
        "notes": (
            "French locale formatting: comma as decimal separator, space as "
            "thousands separator. English output should use dot for decimals "
            "(8,3% → 8.3%). Numbers must be semantically preserved even if "
            "formatting changes."
        ),
        "tags": ["french", "locale", "numbers"],
        "expected_numbers": ["8", "12", "1250", "23"],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Search-impact smoke tests
    # ==================================================================
    {
        "id": "tr-si-001-search-terms",
        "category": "search_impact_smoke",
        "source_lang": "he",
        "target_lang": "en",
        "source_text": (
            "החברה מפתחת מערכת חדשה לניהול מסמכים ארגוניים.\n"
            "המערכת כוללת יכולות חיפוש מתקדמות, תרגום אוטומטי,\n"
            "והפקת דוחות חכמה. המערכת תושק ברבעון השלישי של 2026."
        ),
        "notes": (
            "Hebrew text about enterprise document management. The English "
            "translation should contain key search terms like 'document', "
            "'management', 'search', 'translation', 'reports'. "
            "Used for downstream search-quality smoke testing."
        ),
        "tags": ["hebrew", "search-smoke"],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-si-002-search-terms-zh",
        "category": "search_impact_smoke",
        "source_lang": "zh",
        "target_lang": "en",
        "source_text": (
            "公司正在开发新的企业文档管理系统。\n"
            "该系统包括高级搜索功能、自动翻译和智能报告生成。\n"
            "系统将于2026年第三季度推出。"
        ),
        "notes": (
            "Chinese text about enterprise document management. The English "
            "translation should contain key search terms for downstream "
            "search-quality smoke testing."
        ),
        "tags": ["chinese", "search-smoke"],
        "expected_tokens_min": 15,
        "allows_fast_baseline": True,
    },
    # ==================================================================
    # Language detection smoke tests
    # ==================================================================
    {
        "id": "tr-ld-001-detect-he",
        "category": "language_detection",
        "source_lang": "he",
        "target_lang": "en",
        "source_text": "שלום עולם, זוהי בדיקת תרגום.",
        "notes": (
            "Short Hebrew text for language detection smoke test. "
            "source_lang is explicitly 'he', verifying the provider "
            "routes correctly when the language is known ahead of time."
        ),
        "tags": ["hebrew", "language-detection"],
        "source_language_expected": "he",
        "expected_tokens_min": 5,
        "allows_fast_baseline": True,
    },
    {
        "id": "tr-ld-002-detect-auto",
        "category": "language_detection",
        "source_lang": None,  # auto-detect
        "target_lang": "en",
        "source_text": "Dies ist ein deutscher Testtext für die automatische Spracherkennung.",
        "notes": (
            "German text with source_lang=None to test auto-detection. "
            "The provider must detect the source language and translate. "
            "If auto-detect is unsupported, the fallback behaviour is documented."
        ),
        "tags": ["german", "language-detection"],
        "expected_tokens_min": 5,
        "allows_fast_baseline": True,
    },
]
