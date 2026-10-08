# Hang_in_liton

## 행인(HANG-IN) - 낭비 없는 여행, 마음 맞는 순간

혼자 여행할 때 생기는 비용·감정 낭비를 줄이는 웹서비스입니다.

| 기능 | 설명 |
| --- | --- |
| 온보딩 · 여행 성향 | 여행·숙소·이동 스타일 3문항 → 한 프롬프트로 묶어 HyperCLOVA X(HCX-005) 가 16가지 성향 중 하나로 판단 → JSON으로 받아 마이페이지에 저장 |
| 행인 매칭 | 행인 구하기(모집글) / 행인 찾기(국가·카테고리 필터, 성향 배지) / 신청 → 수락하면 서로의 연락처(카톡·DM) 공개 |
| 정산 | 참여인원 ±, 결제자·참여자별 지출 기록, 받을/지불 금액, 최소 송금 경로, 정산비율, 공유하기 |
| 절약 | 외국 메뉴판 사진 → CLOVA OCR 로 글자 추출 → HyperCLOVA X 가 "무엇을 몇 개 시켜 나눠 먹을지" 절약형 N빵 가이드(JSON) 작성 |

### 실행 방법 

```powershell
py -3.14 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   
python app.py            # http://127.0.0.1:5000
```

### AI와 서버의 역할 나누기

- HyperCLOVA X : 16유형 판단과 설명, 메뉴판 해석과 주문 조합 판단
- 서버(Flask) : 입력값 검증, 유형 코드 검증, 금액 계산, 저장, 권한 확인

### 폴더 구조

```
app.py              Flask 라우트, DB 스키마/마이그레이션, CSRF
clova.py            HyperCLOVA X · CLOVA OCR 호출, JSON 파싱/검증
travel_types.py     온보딩 선택지, 16가지 성향, 규칙 기반 대체 판단
prompts/            시스템 프롬프트 (성향 분석, 메뉴판 옮겨 적기, N빵 가이드)
templates/          Jinja 템플릿 (daisyUI + Tailwind CDN + htmx)
static/css/app.css  디자인 토큰·컴포넌트
static/js/app.js    온보딩 단계, 사진 축소 업로드, 로딩 화면, 공유
static/img/         와이어프레임에서 추출한 캐릭터·아바타
uploads/            사용자가 올린 사진
```

### 사용된 라이브러리 및 오픈소스

Inspect - Export to HTML, React, TailwindCSS[https://www.figma.com/ko-kr/community/plugin/1049994768493726219/inspect-export-to-html-react-tailwindcss]

Figma to HTML[https://www.figma.com/ko-kr/community/plugin/851183094275736358/figma-to-html]
