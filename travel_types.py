"""온보딩 질문 선택지와 16가지 여행 성향 정의.

성향 판단 자체는 HyperCLOVA X가 하고, 이 모듈은
- 질문/선택지(화면과 프롬프트에서 공통 사용)
- 16가지 성향의 정식 이름·이모지(AI 응답 검증 기준)
- AI 호출이 실패했을 때 쓰는 규칙 기반 대체 판단
을 담당한다.
"""

QUESTIONS = [
    {
        'key': 'travel',
        'title': '당신이 선호하는 여행은\n어떤 스타일인가요?',
        'label': '여행 스타일',
        'options': ['🏂 액티비티', '🎬 영화 감상', '🍜 맛집 탐방', '🏖️ 휴양', '🗿 관광지', '🏃 즉흥',
                    '⏰ 계획', '🏨 호캉스', '🛍️ 쇼핑', '🎒 배낭', '🌍 자연'],
    },
    {
        'key': 'stay',
        'title': '당신이 좋아하는\n숙소 스타일을 알려주세요!',
        'label': '숙소 스타일',
        'options': ['🪙 가성비', '✨ 럭셔리', '🕯️ 감성 숙소', '🛏️ 다인실', '🗿 현지인 라이프',
                    '🏘️ 에어비앤비', '🏕️ 캠핑'],
    },
    {
        'key': 'move',
        'title': '당신이 좋아하는\n이동 스타일을 알려주세요!',
        'label': '이동 스타일',
        'options': ['🚆 기차', '🚴 자전거', '🚗 렌트카', '🚌 버스', '🚊 지하철', '🚕 택시', '🚢 배'],
    },
]

QUESTION_KEYS = [q['key'] for q in QUESTIONS]
OPTIONS_BY_KEY = {q['key']: q['options'] for q in QUESTIONS}

# 4가지 축 → 2^4 = 16가지 성향
AXES = [
    {'key': 'energy', 'letters': ('A', 'C'), 'names': ('액티브', '차분'),
     'desc': 'A=부지런히 돌아다니며 체험 위주 / C=여유롭게 쉬며 머무는 여행'},
    {'key': 'plan', 'letters': ('P', 'F'), 'names': ('계획', '즉흥'),
     'desc': 'P=일정과 동선을 미리 짬 / F=발길 닿는 대로 즉흥적으로 움직임'},
    {'key': 'spend', 'letters': ('S', 'E'), 'names': ('실속', '경험투자'),
     'desc': 'S=가성비·절약 우선 / E=분위기·편안함·경험에 돈을 씀'},
    {'key': 'move', 'letters': ('W', 'D'), 'names': ('대중교통·도보', '자유이동'),
     'desc': 'W=걷기·대중교통·자전거 선호 / D=렌트카·택시처럼 문 앞까지 편하게'},
]

TYPES = {
    'APSW': ('🧭', '부지런한 알뜰 개척자', '꼼꼼한 동선과 대중교통으로 최소 비용에 최대 경험을 뽑아내는 타입'),
    'APSD': ('🗺️', '효율 만렙 플래너', '계획한 곳을 렌트·택시로 빠르게 돌며 시간을 아끼는 실속파'),
    'APEW': ('📸', '버킷리스트 수집가', '가고 싶은 곳 리스트를 하나씩 지워가며 경험에 투자하는 타입'),
    'APED': ('🏄', '프리미엄 액티비티 러버', '제대로 된 체험이라면 아끼지 않는, 계획적인 액티비티파'),
    'AFSW': ('🎒', '자유로운 배낭여행자', '가벼운 짐과 대중교통으로 즉흥 루트를 즐기는 알뜰 모험가'),
    'AFSD': ('🚗', '즉흥 로드트립러', '마음 맞는 사람과 차비를 나누며 즉흥 드라이브를 떠나는 타입'),
    'AFEW': ('🌆', '감성 골목 탐험가', '골목과 로컬 스팟을 걸으며 분위기 좋은 곳에 기꺼이 지갑을 여는 타입'),
    'AFED': ('🪂', '스릴 추구 모험가', '즉흥적인 도전과 짜릿한 체험을 위해서라면 이동도 과감한 타입'),
    'CPSW': ('🚶', '차분한 실속 산책러', '천천히 걷고 오래 머물며 계획적으로 아끼는 여유파'),
    'CPSD': ('🧘', '느긋한 계획형 힐러', '편하게 이동하며 정해둔 몇 곳에서 충분히 쉬는 타입'),
    'CPEW': ('🍷', '미식 & 문화 감상가', '맛집과 전시를 미리 예약해 두고 걸어서 음미하는 타입'),
    'CPED': ('🏨', '호캉스 플래너', '좋은 숙소와 편한 이동이 곧 여행의 질이라고 믿는 타입'),
    'CFSW': ('🏘️', '현지인처럼 사는 여행자', '동네 마트와 대중교통을 쓰며 현지 생활에 스며드는 타입'),
    'CFSD': ('🌄', '발길 닿는 대로 드라이버', '정해진 일정 없이 차를 타고 마음에 드는 풍경에 머무는 타입'),
    'CFEW': ('🌙', '낭만 감성 몽상가', '감성 숙소와 산책, 우연한 발견을 사랑하는 타입'),
    'CFED': ('🏖️', '여유로운 럭셔리 휴양가', '계획 없이 편안함과 휴식에 아낌없이 투자하는 타입'),
}

# 규칙 기반 대체 판단용 가중치(선택지 → 축 점수). 양수=첫 글자, 음수=둘째 글자
_WEIGHTS = {
    '🏂 액티비티': {'energy': 2}, '🎬 영화 감상': {'energy': -1}, '🍜 맛집 탐방': {'energy': 1, 'spend': -1},
    '🏖️ 휴양': {'energy': -2}, '🗿 관광지': {'energy': 1, 'plan': 1}, '🏃 즉흥': {'plan': -2},
    '⏰ 계획': {'plan': 2}, '🏨 호캉스': {'energy': -2, 'spend': -2}, '🛍️ 쇼핑': {'energy': 1, 'spend': -1},
    '🎒 배낭': {'spend': 2, 'plan': -1, 'move': 1}, '🌍 자연': {'energy': 1},
    '🪙 가성비': {'spend': 2}, '✨ 럭셔리': {'spend': -2}, '🕯️ 감성 숙소': {'spend': -1, 'plan': -1},
    '🛏️ 다인실': {'spend': 2}, '🗿 현지인 라이프': {'spend': 1, 'energy': -1}, '🏘️ 에어비앤비': {'spend': 1},
    '🏕️ 캠핑': {'spend': 1, 'energy': 1},
    '🚆 기차': {'move': 1}, '🚴 자전거': {'move': 2, 'energy': 1}, '🚗 렌트카': {'move': -2},
    '🚌 버스': {'move': 2}, '🚊 지하철': {'move': 2}, '🚕 택시': {'move': -2}, '🚢 배': {'move': 1},
}


def clean_answers(form_lists):
    """폼에서 받은 선택값 중 정의된 선택지만 남긴다."""
    out = {}
    for key in QUESTION_KEYS:
        allowed = OPTIONS_BY_KEY[key]
        picked = [v for v in form_lists.get(key, []) if v in allowed]
        out[key] = list(dict.fromkeys(picked))
    return out


def rule_based_code(answers):
    score = {a['key']: 0 for a in AXES}
    for key in QUESTION_KEYS:
        for opt in answers.get(key, []):
            for axis, w in _WEIGHTS.get(opt, {}).items():
                score[axis] += w
    return ''.join(a['letters'][0] if score[a['key']] >= 0 else a['letters'][1] for a in AXES)


def type_info(code):
    emoji, name, tagline = TYPES[code]
    return {'code': code, 'emoji': emoji, 'name': name, 'tagline': tagline}


def axes_of(code):
    return [{'key': a['key'], 'letter': code[i], 'name': a['names'][a['letters'].index(code[i])],
             'pair': a['names']} for i, a in enumerate(AXES)]
