"""NAVER Cloud CLOVA Studio(HyperCLOVA X)와 CLOVA OCR 호출 모듈.

API 키는 서버 환경변수(.env)에서만 읽는다. 브라우저로 내려보내지 않는다.
"""
import base64
import json
import os
import re
import time
import uuid

import requests

import travel_types as tt

PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompts')


class ClovaError(Exception):
    """사용자에게 보여줄 수 있는 짧은 메시지를 담는 오류."""


def _env(name, default=''):
    return os.environ.get(name, default).strip()


def _prompt(name):
    with open(os.path.join(PROMPT_DIR, name), encoding='utf-8') as f:
        return f.read()


# ─── HyperCLOVA X ────────────────────────────────────────────

def chat(messages, *, max_tokens=1024, temperature=0.3, timeout=90):
    api_key = _env('CLOVA_STUDIO_API_KEY')
    if not api_key:
        raise ClovaError('CLOVA_STUDIO_API_KEY가 설정되지 않았어요.')
    if not api_key.lower().startswith('bearer '):
        api_key = f'Bearer {api_key}'
    host = _env('CLOVA_STUDIO_HOST', 'https://clovastudio.stream.ntruss.com').rstrip('/')
    model = _env('CLOVA_STUDIO_MODEL', 'HCX-005')
    headers = {
        'Authorization': api_key,
        'X-NCP-CLOVASTUDIO-REQUEST-ID': uuid.uuid4().hex,
        'Content-Type': 'application/json; charset=utf-8',
        'Accept': 'application/json',
    }
    body = {
        'messages': messages,
        'topP': 0.8,
        'topK': 0,
        'maxTokens': max_tokens,
        'temperature': temperature,
        'repetitionPenalty': 1.1,
        'stop': [],
        'seed': 0,
        'includeAiFilters': True,
    }
    try:
        res = requests.post(f'{host}/v3/chat-completions/{model}', headers=headers, json=body, timeout=timeout)
    except requests.Timeout as e:
        raise ClovaError('HyperCLOVA X 응답이 너무 늦어요. 잠시 후 다시 시도해 주세요.') from e
    except requests.RequestException as e:
        raise ClovaError('HyperCLOVA X에 연결하지 못했어요.') from e
    try:
        data = res.json()
    except ValueError as e:
        raise ClovaError(f'HyperCLOVA X 응답을 읽지 못했어요. (HTTP {res.status_code})') from e
    status = data.get('status') or {}
    if res.status_code != 200 or status.get('code') != '20000':
        raise ClovaError(f"HyperCLOVA X 오류: {status.get('code', res.status_code)} {status.get('message', '')}".strip())
    return (data.get('result') or {}).get('message', {}).get('content', '')


def parse_json(text):
    """모델 응답에서 JSON 객체를 꺼낸다. 코드블록·앞뒤 문장·끝 쉼표를 허용한다."""
    if not text:
        raise ClovaError('HyperCLOVA X가 빈 응답을 보냈어요.')
    cleaned = re.sub(r'```(?:json)?', '', text).strip()
    start, end = cleaned.find('{'), cleaned.rfind('}')
    if start == -1 or end <= start:
        raise ClovaError('HyperCLOVA X 응답에서 JSON을 찾지 못했어요.')
    candidate = cleaned[start:end + 1]
    for attempt in (candidate, re.sub(r',\s*([}\]])', r'\1', candidate)):
        try:
            value = json.loads(attempt, strict=False)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise ClovaError('HyperCLOVA X 응답 JSON 형식이 올바르지 않아요.')


def chat_json(messages, **kwargs):
    return parse_json(chat(messages, **kwargs))


# ─── CLOVA OCR ───────────────────────────────────────────────

_ocr_unreachable_until = 0.0


def ocr_configured():
    """OCR 주소가 설정돼 있고, 최근 10분 안에 연결 실패한 적이 없으면 True"""
    return bool(_env('CLOVA_OCR_INVOKE_URL') and _env('CLOVA_OCR_SECRET')) and time.time() >= _ocr_unreachable_until


def ocr_text(image_bytes, image_format):
    """General OCR로 이미지 속 글자를 줄 단위 텍스트로 돌려준다."""
    url = _env('CLOVA_OCR_INVOKE_URL').rstrip('/')
    secret = _env('CLOVA_OCR_SECRET')
    if not url or not secret:
        raise ClovaError('CLOVA OCR이 설정되지 않았어요.')
    if not re.search(r'/(general|infer)$', url):
        url += '/general'
    message = {
        'version': 'V2',
        'requestId': uuid.uuid4().hex,
        'timestamp': int(time.time() * 1000),
        'images': [{'format': image_format, 'name': 'menu', 'data': base64.b64encode(image_bytes).decode()}],
    }
    lang = _env('CLOVA_OCR_LANG')
    if lang:
        message['lang'] = lang
    global _ocr_unreachable_until
    try:
        res = requests.post(url, headers={'X-OCR-SECRET': secret, 'Content-Type': 'application/json'},
                            json=message, timeout=(5, 40))
    except requests.RequestException as e:
        if isinstance(e, (requests.ConnectionError, requests.ConnectTimeout)):
            _ocr_unreachable_until = time.time() + 600
        raise ClovaError('CLOVA OCR에 연결하지 못했어요.') from e
    if res.status_code != 200:
        raise ClovaError(f'CLOVA OCR 오류 (HTTP {res.status_code})')
    try:
        image = res.json()['images'][0]
    except (ValueError, KeyError, IndexError) as e:
        raise ClovaError('CLOVA OCR 응답을 읽지 못했어요.') from e
    if image.get('inferResult') != 'SUCCESS':
        raise ClovaError(f"CLOVA OCR 인식 실패: {image.get('message', '')}")
    lines, current = [], []
    for field in image.get('fields', []):
        current.append(field.get('inferText', ''))
        if field.get('lineBreak'):
            lines.append(' '.join(current))
            current = []
    if current:
        lines.append(' '.join(current))
    return '\n'.join(line for line in lines if line.strip())


# ─── 기능 1: 여행 성향 16유형 분석 ─────────────────────────────

def _travel_system_prompt():
    axes = '\n'.join(f"- {a['key']}: {a['desc']}" for a in tt.AXES)
    types = '\n'.join(f'{code}: {name} - {tagline}' for code, (_, name, tagline) in tt.TYPES.items())
    return (_prompt('travel_type_system.txt').replace('{{AXES}}', axes)
            .replace('{{HINTS}}', tt.axis_hints()).replace('{{TYPES}}', types))


def _travel_user_prompt(answers):
    lines = [f"[{q['label']}] {', '.join(tt.plain(o) for o in answers.get(q['key'], [])) or '선택 없음'}"
             for q in tt.QUESTIONS]
    return '사용자가 고른 항목입니다.\n' + '\n'.join(lines)


def _str_list(value, limit):
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def analyze_travel_type(answers):
    """세 질문의 선택값을 한 프롬프트로 묶어 HyperCLOVA X에 성향 판단을 맡긴다."""
    raw = chat_json([
        {'role': 'system', 'content': _travel_system_prompt()},
        {'role': 'user', 'content': _travel_user_prompt(answers)},
    ], max_tokens=1200, temperature=0.3)
    return normalize_travel_profile(raw, answers, source='hcx')


def normalize_travel_profile(raw, answers, source):
    """AI 응답을 검증해서 저장용 형태로 정리한다. 코드가 틀리면 축 값 또는 규칙 기반으로 보정한다."""
    code = str(raw.get('type_code', '')).upper().strip()
    if code not in tt.TYPES:
        axes = raw.get('axes') or {}
        joined = ''.join(str(axes.get(a['key'], '')).upper()[:1] for a in tt.AXES)
        code = joined if joined in tt.TYPES else tt.rule_based_code(answers)
    info = tt.type_info(code)
    best = raw.get('best_match') or {}
    best_code = str(best.get('type_code', '')).upper().strip()
    best_info = tt.type_info(best_code) if best_code in tt.TYPES else None
    return {
        **info,
        'summary': str(raw.get('summary') or info['tagline']).strip(),
        'description': str(raw.get('description') or '').strip(),
        'keywords': _str_list(raw.get('keywords'), 5),
        'saving_tips': _str_list(raw.get('saving_tips'), 4),
        'best_match': {**best_info, 'reason': str(best.get('reason') or '').strip()} if best_info else None,
        'caution': str(raw.get('caution') or '').strip(),
        'axes': tt.axes_of(code),
        'source': source,
        'analyzed_at': time.strftime('%Y-%m-%d %H:%M'),
    }


def fallback_travel_profile(answers):
    code = tt.rule_based_code(answers)
    return normalize_travel_profile({'type_code': code}, answers, source='rule')


# ─── 기능 2: 외국 메뉴판 → 절약형 N빵 가이드 ──────────────────────

def _to_number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        digits = re.sub(r'[^0-9.,]', '', value)
        if digits.count(',') and digits.count('.'):
            digits = digits.replace(',', '')
        elif digits.count(',') == 1 and len(digits.split(',')[1]) <= 2:
            digits = digits.replace(',', '.')
        else:
            digits = digits.replace(',', '')
        try:
            return float(digits)
        except ValueError:
            return None
    return None


IMAGE_MIME = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}


def transcribe_menu(image, image_format):
    """CLOVA OCR을 쓸 수 없을 때 HCX-005 비전으로 메뉴판 글자를 옮겨 적는다(OCR 대체)."""
    data_uri = f"data:{IMAGE_MIME.get(image_format, 'image/jpeg')};base64,{base64.b64encode(image).decode()}"
    return chat([
        {'role': 'system', 'content': _prompt('menu_transcribe_system.txt')},
        {'role': 'user', 'content': [
            {'type': 'image_url', 'dataUri': {'data': data_uri}},
            {'type': 'text', 'text': '이 메뉴판의 글자를 빠짐없이 옮겨 적어 주세요.'},
        ]},
    ], max_tokens=2000, temperature=0.0, timeout=90).strip()


def analyze_menu(*, menu_text, people, country_name, currency, note='', travel_type=None):
    """메뉴판 글자(OCR 결과)를 HyperCLOVA X에 보내 절약형 N빵 가이드 JSON을 받는다."""
    context = [
        f'[여행 국가] {country_name} (기본 통화 {currency})',
        f'[인원 수] {people}명',
        f"[추가 요청] {note or '없음'}",
    ]
    if travel_type:
        context.append(f"[주문하는 사람의 여행 성향] {travel_type['name']} - {travel_type.get('summary', '')}")
    context.append('[메뉴판 OCR 결과]\n' + menu_text[:6000])
    raw = chat_json([
        {'role': 'system', 'content': _prompt('menu_guide_system.txt').replace('{{CURRENCY}}', currency)},
        {'role': 'user', 'content': '\n'.join(context) + '\n\n위 메뉴판으로 절약형 N빵 가이드를 JSON으로 만들어 주세요.'},
    ], max_tokens=3000, temperature=0.2, timeout=120)
    return normalize_menu_guide(raw, people=people, currency=currency)


_CATEGORY_WORDS = [
    ('디저트', ('dessert', 'sweet', 'dolce', 'postre', '甜', 'デザート', '디저트')),
    ('음료', ('drink', 'boisson', 'beverage', 'bebida', 'wine', 'vin', 'beer', 'bière', 'cafe', 'café', '음료', '飲', '酒')),
    ('전채', ('entrée', 'entree', 'starter', 'appet', 'antipast', 'tapa', '전채', '前菜')),
    ('사이드', ('side', 'accomp', 'garniture', '사이드')),
    ('메인', ('main', 'plat', 'secondi', 'primi', 'pizza', 'pasta', '메인', '主')),
]


def _category(value):
    text = str(value or '').strip()
    if text in ('메인', '전채', '사이드', '음료', '디저트', '기타'):
        return text
    low = text.lower()
    return next((name for name, words in _CATEGORY_WORDS if any(w in low for w in words)), '기타')


def normalize_menu_guide(raw, *, people, currency):
    """금액 계산은 AI 대신 서버가 다시 한다(메뉴판 가격 우선, 수량 × 단가)."""
    cur = str(raw.get('currency') or currency).upper().strip()[:3] or currency
    if not re.fullmatch(r'[A-Z]{3}', cur):
        cur = currency
    menu = []
    for item in (raw.get('menu_items') or [])[:30]:
        if not isinstance(item, dict) or not item.get('name'):
            continue
        menu.append({
            'name': str(item.get('name')).strip(),
            'name_ko': str(item.get('name_ko') or '').strip(),
            'price': _to_number(item.get('price')),
            'category': _category(item.get('category')),
            'shareable': bool(item.get('shareable')),
        })
    menu_price = {m['name'].lower(): m['price'] for m in menu if m['price'] is not None}
    orders, total = [], 0.0
    for item in raw.get('orders') or []:
        if not isinstance(item, dict) or not item.get('name'):
            continue
        qty = _to_number(item.get('quantity')) or 1
        qty = max(1, min(int(round(qty)), 20))
        unit = menu_price.get(str(item.get('name')).strip().lower(), _to_number(item.get('unit_price')))
        subtotal = round(unit * qty, 2) if unit is not None else None
        if subtotal is not None:
            total += subtotal
        orders.append({
            'name': str(item.get('name')).strip(),
            'name_ko': str(item.get('name_ko') or '').strip(),
            'quantity': qty,
            'unit_price': unit,
            'subtotal': subtotal,
            'reason': str(item.get('reason') or '').strip(),
        })
    total = round(total, 2)
    individual = _to_number(raw.get('individual_estimate'))
    saving = round(individual - total, 2) if individual and individual > total else 0
    return {
        'restaurant_type': str(raw.get('restaurant_type') or '').strip(),
        'currency': cur,
        'menu_items': menu,
        'orders': orders,
        'total': total,
        'per_person': round(total / people, 2) if people else total,
        'individual_estimate': individual,
        'saving': saving,
        'split_tip': str(raw.get('split_tip') or '').strip(),
        'saving_tips': _str_list(raw.get('saving_tips'), 4),
        'summary': str(raw.get('summary') or '').strip(),
    }
