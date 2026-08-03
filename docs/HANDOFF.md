# 프롬아떼 스마트 커머스 툴 — 인수인계 문서

> 세션이 끊기거나 `/clear` 후 새 세션에서 이어서 작업할 때 **이 문서를 먼저 읽는다.**
> 마지막 갱신: 2026-08-03

---

## 1. 이 프로젝트가 뭔가

프롬아떼(도매 기반 이커머스 셀러)가 상품 등록·상세페이지 제작에 쓰는 **Streamlit 단일 페이지 웹앱**이다.
탭 5개로 기능이 나뉘어 있고, Streamlit Community Cloud에 배포되어 브라우저에서 바로 쓴다.

- **로컬 경로**: `C:\Claude\fromarte-repo`
- **GitHub**: `https://github.com/yumiaena-alt/fromarte` (브랜치 `main`)
- **배포 URL**: https://fromarte-9pmmpcfbggfbgu8vu4ufy7.streamlit.app
- **배포 진입점**: `title_generator/app.py` ← **실제로 배포되는 유일한 파일**

배포 방식은 GitHub 연동 자동 배포다. `main`에 푸시하면 Streamlit Cloud가 감지해 1~2분 내 재배포한다.
별도 배포 명령은 없다.

---

## 2. ⚠️ 가장 먼저 알아야 할 함정

### 2-1. 앱 코드가 두 파일에 중복되어 있다

| 파일 | 상태 |
|---|---|
| `title_generator/app.py` (2,796줄) | **실제 배포되는 파일. 수정은 여기에만 한다.** |
| `price_calculator/app.py` (2,477줄) | 거의 같은 내용의 오래된 복제본. **문법 오류로 실행 불가 상태이며 커밋되지 않은 변경이 쌓여 있다.** |
| `detail-merger/app.py` (89줄) | 소규모 별도 앱. 이번 작업 범위 밖. |

과거에 기능을 `price_calculator/app.py`에만 넣고 배포 파일에는 반영하지 않아
"코드는 있는데 화면에 안 나온다"는 혼란이 있었다. **반드시 `title_generator/app.py`를 수정할 것.**

`price_calculator/app.py`의 현재 상태:
- `IndentationError` (line 2357 부근) — 파이썬이 파싱조차 못 한다
- 커밋 안 된 변경 392줄 추가 / 216줄 삭제가 워킹 트리에 그대로 방치
- **의도적으로 손대지 않고 남겨둔 상태.** 정리하려면 사용자에게 먼저 물어볼 것
  (별도 배포된 앱인지 확인 필요 — 아직 확인받지 못했다)

### 2-2. 다운로드 파일명은 반드시 영문/숫자

사용자의 확정 규칙이다. 한글 파일명은 안 된다 (ESM+ 이미지 호스팅에서 깨진다).
`_safe_filename_token()` (line 443)을 반드시 경유시킬 것. 자세한 건 §4-5.

### 2-3. Streamlit Cloud 디스크는 휘발성

생성 로그(`title_generator/logs/`)는 로컬 디스크에 저장된다.
앱이 재시작·재배포·크래시 복구되면 **폴더가 통째로 사라진다.**
즉 "생성 로그 재다운로드" 기능은 앱이 계속 켜져 있는 동안만 유효하다.
영구 보관이 필요해지면 외부 스토리지(S3/Supabase 등)로 옮겨야 한다. — 미해결 과제

---

## 3. 화면 구조

`st.tabs`로 만든 5개 탭. 코드상 정의 순서와 화면 순서가 다르니 주의
(`tab4, tab1, tab2, tab3, tab5 = st.tabs([...])`, line 1245).

| 화면 순서 | 탭 변수 | 이름 | 코드 위치 |
|---|---|---|---|
| 1 | `tab4` | 🔗 도매마켓 바로가기 | line 2402 |
| 2 | `tab1` | 🏷️ 상품명 작성기 | line 1258 |
| 3 | `tab2` | 💰 마켓별 판매가 계산기 | line 1586 |
| 4 | `tab3` | 🖼️ 상세페이지 합치기 | line 1870 |
| 5 | `tab5` | 🎯 배너컷 생성기 (하위탭: 🎨 생성 / 📋 생성 로그) | line 2429 |

---

## 4. 이번 작업 세션에서 만든 기능 (2026-07-30 ~ 08-03)

커밋 `c2716f8` ~ `b9add67`. 전부 `title_generator/app.py` 단일 파일 수정.

### 4-1. 배너컷 생성기 — 다중 사진 업로드 (`c2716f8`)

- `st.file_uploader(..., accept_multiple_files=True)`
- 업로드된 **모든** 사진을 매 API 요청에 함께 첨부한다 → 색상이 여러 사진에 흩어져 있어도
  Gemini가 전체를 보고 해당 색상을 찾아 합성
- 핵심 함수: `fetch_gemini_banner_image(image_png_bytes_list, ...)` (line 465)
  — 인자가 **단일 bytes가 아니라 bytes 리스트**임에 주의

### 4-2. 메모리 초과(OOM) 방지 리사이즈 (`f18d2a7`)

원본 해상도 사진 여러 장을 그대로 API에 보내다 배포 서버가 강제 종료(OOM kill)되는 일이 있었다.
증상: 로그에 파이썬 트레이스백 없이 뚝 끊기고 "Error running app" 화면.

→ 업로드 직후 **긴 변 1600px(`MAX_BANNER_UPLOAD_DIMENSION`)로 축소**한 뒤 전송한다.
Streamlit Cloud 무료 티어 메모리는 약 1GB이므로 이 상한을 함부로 올리지 말 것.

### 4-3. 생성 로그 + 재다운로드 (`c2716f8`)

- `save_banner_generation_log()` (line 543)
- 저장 구조:
  ```
  title_generator/logs/
  ├── banner_log.csv            # 생성일시, 배너스타일, 생성모델, 색상, 생성수량, 저장폴더, 파일목록
  └── banner_YYYYMMDD_HHMMSS/   # 생성된 jpg들
  ```
- 📋 생성 로그 탭에서 과거 생성분을 썸네일로 보고 개별/전체 재다운로드
- ⚠️ §2-3의 휘발성 제약을 반드시 함께 기억할 것

### 4-4. ZIP 폐지 → 개별 이미지 자동 저장 (`3100609`, `49b6f66`)

사용자 요청으로 ZIP 압축을 없앴다. 생성 탭·로그 탭 모두 **이미지 파일을 각각 따로** 저장한다.

- `trigger_individual_image_downloads(results)` (line 593)
- 숨은 `<a download>` 앵커를 만들어 **900ms 간격으로 순차 클릭**한다
  (간격을 두는 이유: 브라우저가 동시 다운로드를 스로틀링/차단함)
- `import zipfile`은 이제 안 쓰므로 제거됨
- **브라우저 제약**: 크롬은 "여러 파일을 다운로드하려고 합니다"를 한 번 묻는다.
  사용자가 과거에 '차단'을 눌렀다면 첫 장만 저장되고 조용히 막힌다.
  코드로 우회 불가 — 사이트 설정에서 '자동 다운로드 허용'으로 바꿔야 한다.

### 4-5. 다운로드 파일명 영문화 (`b9add67`)

- `COLOR_NAME_TO_ENGLISH` (line 388): 한글 색상명 → 영문 매핑
  (흰색→white, 핑크→pink, 베이지→beige, 연청→lightdenim … 약 50개)
- `_safe_filename_token()` (line 443): 먼저 위 매핑으로 치환 → 그 뒤 `[A-Za-z0-9]` 외 전부 제거
  → 매핑에 없으면 `color1`, `color2`로 폴백
- 결과 예: `흰색` → `banner_white_studio_white.jpg`, `블랙2` → `banner_black2_studio_white.jpg`
- **화면 라벨은 한글 유지**(📥 흰색 / 📥 핑크 / 📥 전체 모음), **파일명만** 영문
- 자주 쓰는 색상이 더 생기면 매핑 표에 추가하면 된다

### 4-6. 플로팅 버튼 (화면 우측에 따라다니는 버튼)

파일 상단(line 43)에서 `components.html`로 **부모 문서에 직접 주입**한다.
Streamlit 컴포넌트는 iframe 안에서 실행되므로 `window.parent.document`를 조작해야 한다.

| 버튼 | id | `bottom` | 비고 |
|---|---|---|---|
| ⬆️ 맨 위로 | `scroll_to_top_fab` | 144px | 위에서 1번 |
| ⬇️ 맨 아래로 | `scroll_to_bottom_fab` | 84px | 2번 |
| 📥 상세페이지 다운로드 | `detail_download_fab` | 24px | 3번. 합성 완료 시에만 생성 |

- `bottom` 값이 **클수록 화면 위쪽**이다 (순서 바꿀 때 헷갈리기 쉬움)
- `__fromarteRepositionFabs()`: 화면 가장자리가 아니라 본문 컬럼(`.block-container`)
  오른쪽에 붙도록 좌표를 계산. 창 크기 변경 시 재계산

### 4-7. 상세페이지 탭 하단 "맨 위로 이동" 버튼

여기서 **시행착오가 많았으니 반복하지 말 것.** 최종 방식은 아래와 같다.

**최종 구현** (`49b6f66`): 바로 위 다운로드 버튼의 **DOM을 복제**해서 그 아래에 삽입하고,
클릭은 클라이언트에서만 처리한다.
- 앵커: `.st-key-detail_bottom_actions [data-testid="stDownloadButton"]`
  → 이를 위해 하단 다운로드 버튼을 `st.container(key="detail_bottom_actions")`로 감쌌다
- 복제 노드의 `data-testid`는 제거한다 (자기 자신을 다시 선택하는 것 방지)
- `MutationObserver`로 재렌더링에 지워지면 재삽입

**실패했던 방식들과 그 이유:**

| 시도 | 실패 이유 |
|---|---|
| `scrollTo({behavior:'smooth'})` | 이 Streamlit 버전에서 안 먹힘. **`scrollTop = 0` 직접 대입만 동작** |
| `window.scrollTo()` | 실제 스크롤 컨테이너는 `window`가 아니라 **`[data-testid="stMain"]`** |
| `st.button` + 스크롤 스크립트 | `st.button` 클릭은 **스크립트 전체 재실행**을 유발 → 무거운 이미지 합성이 다시 돌아 극심한 버벅임 |
| `st.button` + `st.rerun()` | 재실행이 **두 번** 일어나 더 느려짐 |
| "마지막 다운로드 버튼"을 복제 대상으로 찾기 | 배너컷 탭의 다운로드 버튼이 잡혀 **숨겨진 탭 안에 삽입**되어 안 보였음 |
| 다운로드 실행을 `st.expander` 안에 두기 | expander가 접히면 내부 컴포넌트가 실행되지 않아 다운로드 누락 → **밖으로 빼야 함** |

---

## 5. 설정값 (Streamlit Secrets)

`st.secrets` 또는 환경변수로 읽는다. 코드에 하드코딩된 키는 없다.

| 키 | 용도 |
|---|---|
| `GEMINI_BANNER_API_KEY` | 배너컷 생성용. **유료 프로젝트 키를 분리해 과금을 섞지 않으려는 의도.** 없으면 `GEMINI_API_KEY`로 폴백 |
| `GEMINI_API_KEY` | 상품명 작성기 등 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 네이버 커머스 API (판매가 조회) |
| `NAVER_AD_API_KEY` / `NAVER_AD_SECRET_KEY` / `NAVER_AD_CUSTOMER_ID` | 네이버 검색광고 API (연관 키워드) |
| `ESM_CUSTOMER_ID` | ESM+ 이미지 호스팅 URL 조립용. 기본값 `fromarte` |
| `PROXY_URL` | 네이버 API용 고정 IP 프록시. Streamlit Cloud 외부 IP가 재배포마다 바뀌는 문제 대응. 없으면 직접 호출 |

`BANNER_MODEL_OPTIONS` (line 458) — 사용 가능 이미지 생성 모델:
`gemini-3.1-flash-image`(기본/저렴), `gemini-3-pro-image`(고품질/고가), `gemini-2.5-flash-image`(최저가)

---

## 6. 로컬에서 실행·검증하는 방법

`C:\Claude\.claude\launch.json`에 preview 설정이 등록되어 있다 (`title_generator`, 포트 8502).

로컬 실행 시 `secrets.toml`이 없으면 `StreamlitSecretNotFoundError`로 앱이 죽는다.
UI만 확인할 목적이면 임시 파일을 만들고 **확인 후 반드시 삭제**한다
(커밋되면 안 되는 파일이고, 실제 키를 넣지도 말 것):

```bash
printf 'GEMINI_API_KEY = ""\n' > title_generator/.streamlit/secrets.toml
# ... 검증 ...
rm -rf title_generator/.streamlit
```

문법 검사(매 수정 후 필수):

```bash
python -c "import ast; ast.parse(open('title_generator/app.py', encoding='utf-8').read()); print('OK')"
```

**검증 원칙**: 사용자는 "다 됐다"는 말보다 실제 동작 확인을 요구한다.
JS/스크롤/DOM 관련 변경은 브라우저에서 `javascript_tool`로 실제 값을 측정해 확인했다
(예: `scrollTop` 300 → 0, 복제 버튼과 원본 버튼의 computed style 일치 여부).
API 키가 필요해 로컬 재현이 안 되는 부분은 **격리 테스트 앱**을 따로 만들어 검증한 뒤 삭제했다.

---

## 7. 미해결 / 확인 필요

1. **`price_calculator/app.py` 정리** — 문법 오류 + 미커밋 변경 방치 상태.
   별도 배포된 앱인지 사용자 확인 후 처리. (§2-1)
2. **생성 로그 영구 보관** — 현재는 앱 재시작 시 소실. 외부 스토리지 필요. (§2-3)
3. **크롬 다중 다운로드 차단** — 사용자 브라우저 설정 이슈. 코드로 해결 불가. (§4-4)
4. **`use_container_width` deprecated 경고** — 배포 로그를 도배하고 있다.
   2025-12-31 이후 제거 예정이므로 `width='stretch'`로 일괄 교체 필요.
5. **`google-generativeai` 패키지 EOL** — `google.genai`로 이전 권고 경고가 뜬다.
   현재 실제 이미지 생성은 `requests`로 REST 직접 호출하므로 급하지는 않다.

---

## 8. 작업 관례

- 커밋 메시지: `<type>: <설명>` (feat / fix / refactor / docs …), 본문에 이유를 한국어로 적는다
- 커밋 단위: `title_generator/app.py`만 스테이징한다
  (`price_calculator/app.py`의 미커밋 변경이 섞이지 않도록 `git add -A` 쓰지 말 것)
- 푸시 = 배포다. 푸시 전 사용자 승인을 받는다
- 수정 후 문법 검사 → 가능하면 로컬 브라우저 검증 → 커밋 → 푸시 순서
