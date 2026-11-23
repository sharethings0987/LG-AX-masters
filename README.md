# 인생그램 (another-life)

20세부터 40세까지 다른 사람의 삶을 살아보는 시뮬레이션과, 그 백엔드입니다.

```
another-life/
├─ frontend/
│  ├─ another_life_v8A.html   게임 (A·B·C는 화면 구성만 다른 실험 버전)
│  ├─ another_life_v8B.html
│  ├─ another_life_v8C.html
│  └─ backend.js              세 버전이 같이 쓰는 서버 연동 코드
└─ backend/
   ├─ app/
   │  ├─ main.py              FastAPI 앱 (API + 프론트 정적 서빙)
   │  ├─ db.py                SQLite 스키마·연결·시드
   │  ├─ schemas.py           요청 검증, 정책 규칙 형식
   │  ├─ policies.json        정책 시드 데이터 (26개)
   │  └─ seed.py              policies.json → DB 재반영
   ├─ tests/test_api.py
   └─ data/another_life.db    첫 실행 때 생김 (git 제외)
```

## 실행

Python 3.10 이상이 필요합니다.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

- 게임: http://127.0.0.1:8000/ (A·B·C 중 하나로 무작위 이동)
- API 문서: http://127.0.0.1:8000/docs
- 테스트: `pytest`

서버 없이 HTML 파일을 그냥 열어도 게임은 예전처럼 동작합니다 (내장 정책, 편지는 브라우저 localStorage에 저장).
이때 로컬 서버가 켜져 있으면 `http://127.0.0.1:8000`으로 연결을 시도합니다.

## GitHub Pages 배포

`main` 브랜치에 푸시하면 GitHub Actions가 `frontend/`를 GitHub Pages에 배포합니다.
저장소의 **Settings → Pages → Build and deployment → Source**를 **GitHub Actions**로 한 번 설정하세요.
사이트 첫 화면은 C 버전(`another_life_v8C.html`)을 엽니다.

GitHub Pages는 정적 파일만 제공하므로 FastAPI 백엔드는 실행되지 않습니다.
따라서 API 기반 정책 갱신, 편지 저장, 플레이 기록 기능은 사용할 수 없고, 게임의 내장 정책을 사용합니다.
API 기능까지 공개하려면 백엔드를 별도 호스팅하고 프론트엔드의 API 주소 및 CORS 설정을 구성해야 합니다. GitHub Pages에는 `frontend/public-services.html`도 배포되며, 게임의 「공공정보」 메뉴에서 정부24 혜택, LH 임대공고, 온통청년 청년정책 목록을 볼 수 있습니다. 이 목록은 게임의 정책 판정과 별도로 동작합니다.

### KOSIS 통계 페이지

`frontend/statistics.html`은 2025년 KOSIS 인구·가구 집계 결과를 정적 JSON으로 표시합니다. SQLite나 Render API를 거치지 않으며, 원본 CSV를 브라우저에 내려주지 않습니다. `data/`의 원본 파일은 Git에서 제외되고, 공개 집계 결과만 `frontend/public-data/kosis-2025.json`에 들어갑니다.

KOSIS CSV 세 파일을 `data/01_KOSIS/`에 둔 뒤 저장소 루트에서 아래 명령을 실행해 공개 JSON을 다시 생성합니다.

```powershell
python backend/app/kosis_public.py
```

페이지는 게임 시작 화면과 `public-services.html`에서 연결됩니다. 공개 데이터 범위를 넓힐 때도 MDIS·YP2021 행 단위 원자료는 추가하지 말고, 재배포 조건을 확인한 집계 결과만 별도로 검토하세요.

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/health` | 상태 확인 |
| GET | `/api/policies` | 활성 정책 목록과 공식 사이트 도메인. 게임 시작 때 불러감 |
| GET | `/api/policies/{key}` | 정책 하나 |
| PUT | `/api/policies/{key}` | 정책 추가·수정 (관리자, `X-Admin-Token` 헤더) |
| POST | `/api/letters` | 엔딩의 편지 저장 |
| GET | `/api/letters?player_id=` | 내 편지함 |
| POST | `/api/plays` | 40세 엔딩 도달 시 플레이 기록 저장 |
| PATCH | `/api/plays/{id}` | 엔딩에서 고른 「마음속 목표」「고마웠던 것」 답 기록 |
| GET | `/api/plays?player_id=` | 내 플레이 기록 |
| GET | `/api/stats` | 버전별 플레이 수, 정책별 대상 수·획득 수·획득률 |
| GET | `/api/public/benefits` | 정부24 공공서비스(혜택) 목록 |
| GET | `/api/public/benefits/{service_id}/conditions` | 정부24 공공서비스 지원 조건 |
| GET | `/api/public/lh-notices` | LH 임대주택 공고 목록 |
| GET | `/api/public/youth-policies` | 온통청년 청년정책 목록 (`keyword`, `name` 검색 가능) |
| GET | `/api/public/youth-policies/{policy_no}` | 온통청년 청년정책 상세 |

공공 API 프록시는 키를 백엔드 환경변수에서만 읽습니다. 브라우저 코드나 GitHub Pages 저장소에 인증키를 넣지 마세요. 정부24와 LH API의 정확한 지원 대상·접수 기간은 각 카드의 공식 안내 링크에서 확인해야 합니다.

- [행정안전부 대한민국 공공서비스(혜택) 정보 API](https://www.data.go.kr/data/15113968/openapi.do)
- [한국토지주택공사 분양임대공고문 조회 API](https://www.data.go.kr/data/15058530/openapi.do)

### GitHub Pages + Render 백엔드 배포

GitHub Pages는 백엔드 프로세스를 실행할 수 없습니다. 저장소 루트의 `render.yaml`은 Render Blueprint로 FastAPI 서비스를 **Free 플랜**에 생성하도록 준비되어 있습니다.

1. Render에서 **New → Blueprint**를 선택하고 GitHub 저장소를 연결합니다. Root Directory는 별도로 지정하지 않습니다.
2. Blueprint가 `render.yaml`을 감지하면 `lg-ax-masters-api` 서비스를 만들고 배포합니다.
3. Render 서비스의 **Environment** 설정에서 `GOV24_SERVICE_KEY`, `LH_SERVICE_KEY`, `ONTONG_YOUTH_KEY`를 발급받은 키로 등록합니다. 키는 Blueprint나 GitHub에 저장하지 않습니다.
4. 배포가 완료되면 서비스 URL의 `/api/health`가 `{"ok": true, ...}`를 반환하는지 확인합니다.
5. 발급된 기본 URL을 `frontend/api-config.js`의 `window.AL_API_BASE_URL` 값에 설정하고 `main`에 푸시합니다. `/api` 경로는 URL에 붙이지 않습니다. Pages 배포가 끝나면 게임의 「공공정보」 메뉴에서 목록을 확인합니다.

Render Free 서비스는 일정 시간 요청이 없으면 일시 중지되어 첫 요청이 느릴 수 있고, 파일시스템이 임시 저장소이므로 편지·플레이 기록은 재시작·재배포·일시 중지 후 사라질 수 있습니다. 영구 기록이 필요하면 유료 영구 디스크나 외부 데이터베이스로 바꿔야 합니다. `api-config.js`의 백엔드 주소를 설정하기 전까지 GitHub Pages는 백엔드 API를 사용할 수 없습니다.

**플레이어 식별**: 로그인 없이, 브라우저가 처음 접속할 때 만든 익명 ID(`localStorage`의 `al_pid`)를 씁니다.
기기·브라우저가 바뀌면 다른 사람으로 보입니다. ID는 비밀번호가 아니라서, 남의 ID를 알면 그 사람의 편지를 읽을 수 있습니다.
실제로 공개하려면 계정이나 서명된 세션 토큰을 붙여야 합니다.

### 관리 API 켜기

`AL_ADMIN_TOKEN`을 설정하지 않으면 PUT은 항상 403입니다.

```powershell
$env:AL_ADMIN_TOKEN = "길고-임의의-문자열"
uvicorn app.main:app --reload
```

```powershell
$body = @{ name="청년월세 지원사업"; site="온통청년"; hint="월세를 지원해주는 사업이 있다던데?";
  description="월세 부담을 낮춰주는 모집형 사업."; effects=@{ money=10 };
  requirements=@(
    @{ label="만 19~34세"; field="age"; op="between"; value=@(19,34) },
    @{ label="주거: 월세"; field="h"; op="in"; value=@("월세") }
  ) } | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Put http://127.0.0.1:8000/api/policies/rent `
  -Headers @{ "X-Admin-Token" = $env:AL_ADMIN_TOKEN } -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

정책을 끄려면 같은 내용에 `active=$false`를 넣어 보냅니다. 꺼진 정책은 소문·피드·알림으로 더는 나오지 않습니다.

### policies.json을 고친 뒤

DB가 이미 있으면 서버는 시드를 다시 읽지 않습니다. 고친 내용을 반영하려면:

```powershell
python -m app.seed
```

같은 키의 정책은 JSON 내용으로 덮어쓰고, 관리 API로만 추가한 정책은 그대로 둡니다.

## 정책 규칙 형식

정책의 `requirements`는 규칙 배열이고, 모두 만족해야 대상입니다. 최상위 규칙의 `label`은 게임의 「나는 대상일까?」 목록에 그대로 보입니다.

```json
{"label": "만 18~25세", "field": "age", "op": "between", "value": [18, 25]}
{"label": "자신감·관계가 낮아진 상태", "any": [
  {"field": "st.self", "op": "lt", "value": 50},
  {"field": "st.soc",  "op": "lt", "value": 40}]}
```

| field | 뜻 |
|---|---|
| `age` | 나이 |
| `job` | 현재 상황 (대학생, 취준생, 공시생, 쉬는중, 대기업, 스타트업, 중견·중소, 프리랜서, 공무원, 창업) |
| `h` | 주거 (본가, 월세, 전세, 자가) |
| `employed` | 재직 중인지 (참/거짓) |
| `tenure` | 입사 후 개월 수 |
| `me.q` | 집안 형편 1~5 |
| `st.health` `st.mood` `st.soc` `st.self` `st.burn` `st.money` | 상태값 0~100 (`st.money`는 순자산을 0~100으로 환산한 값) |
| `f.<플래그>` | 사건 플래그: `wage` `laid` `harass` `married` `kid` `care` `sick` `bust` `partner` 등 |

`op`: `between` `in` `lt` `le` `gt` `ge` `eq` `truthy`. 묶음은 `all`(모두) / `any`(하나라도).
`effects` 키: `money`(×10만원) `health` `mood` `soc` `self` `burn` `prep` `hp`.

같은 규칙을 서버(`schemas.py`의 `Rule`)가 검증하고, 브라우저(`backend.js`의 `compile`)가 판정합니다. 필드를 추가할 땐 두 곳을 같이 고쳐야 합니다.

## 환경변수

| 이름 | 기본값 | |
|---|---|---|
| `AL_DB_PATH` | `backend/data/another_life.db` | SQLite 파일 위치 |
| `AL_ADMIN_TOKEN` | 없음 (관리 API 꺼짐) | 정책 수정용 토큰 |
| `AL_CORS_ORIGINS` | `*` | 허용 출처, 쉼표로 구분. 배포 시 실제 도메인으로 좁힐 것 |
| `AL_FRONTEND_DIR` | `frontend/` | 정적 서빙할 폴더 |
| `GOV24_SERVICE_KEY` | 없음 | 정부24 공공서비스 API 인증키 |
| `LH_SERVICE_KEY` | 없음 | LH 분양임대공고 API 인증키 |
| `ONTONG_YOUTH_KEY` | 없음 | 온통청년 청년정책 API 인증키 |

※ 이벤트·정책은 프로토타입용 예시입니다. 실제 대상·조건·금액은 온통청년·복지로·고용24·정부24에서 확인해야 합니다.
