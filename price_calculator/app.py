import base64
import math
import os
import re
import time
import bcrypt
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="프롬아떼 도매 마켓 판매가 계산기", page_icon="💰", layout="centered"
)

st.title("💰 마켓별 판매가 자동 계산기")
st.write(
    "전산 상품을 검색하거나 매입위안/스마트스토어 판매가를 입력하여 맞춤형 판매가를 산출하세요."
)

# ------------------------------------------------------------------
# 1. 네이버 커머스 API 연동 함수 (공식 bcrypt 서명 방식)
# ------------------------------------------------------------------


def fetch_naver_api_price(smartstore_url):
    """스마트스토어 URL에서 상품ID를 추출하여 네이버 Commerce API(공식 bcrypt 서명 방식)로 판매가를 조회합니다."""
    if not smartstore_url or not isinstance(smartstore_url, str):
        return None, "주소가 입력되지 않았습니다."

    # URL 패턴 매칭
    match = re.search(r"products/(\d+)", smartstore_url)
    if not match:
        return (
            None,
            "URL 형태가 올바르지 않습니다. (예: .../products/12345678)",
        )

    product_id = match.group(1)

    client_id = st.secrets.get("NAVER_CLIENT_ID") or os.environ.get(
        "NAVER_CLIENT_ID"
    )
    client_secret = st.secrets.get("NAVER_CLIENT_SECRET") or os.environ.get(
        "NAVER_CLIENT_SECRET"
    )

    if not client_id or not client_secret:
        return (
            None,
            "네이버 API Client ID 또는 Secret이 설정되지 않았습니다. (.streamlit/secrets.toml 확인)",
        )

    try:
        # 1. 네이버 커머스 API 공식 Timestamp & bcrypt 서명 생성
        # 서버 시간 차로 인한 오류 방지를 위해 3초 차감
        timestamp = str(int((time.time() - 3) * 1000))

        # 비밀번호 생성: client_id + "_" + timestamp
        password = f"{client_id}_{timestamp}"

        # bcrypt hash 생성 (client_secret을 salt로 사용)
        hashed = bcrypt.hashpw(
            password.encode("utf-8"), client_secret.encode("utf-8")
        )

        # Base64 인코딩
        client_secret_sign = base64.b64encode(hashed).decode("utf-8")

        # 2. 토큰 발급 요청
        token_url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        token_data = {
            "client_id": client_id,
            "timestamp": timestamp,
            "client_secret_sign": client_secret_sign,
            "grant_type": "client_credentials",
            "type": "SELF",
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        token_res = requests.post(
            token_url, data=token_data, headers=headers, timeout=5
        )

        if token_res.status_code != 200:
            return (
                None,
                f"토큰 발급 실패 (상태 코드: {token_res.status_code}, 내용: {token_res.text})",
            )

        access_token = token_res.json().get("access_token")
        if not access_token:
            return None, "토큰 발급 응답에 access_token이 없습니다."

        # 3. 상품 상세 정보 조회
        api_url = f"https://api.commerce.naver.com/external/v2/products/channel-products/{product_id}"
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        res = requests.get(api_url, headers=auth_headers, timeout=5)

        if res.status_code != 200:
            return (
                None,
                f"상품 API 조회 실패 (상태 코드: {res.status_code}, 내용: {res.text})",
            )

        data = res.json()
        origin_product = data.get("originProduct", {})
        discount_price = origin_product.get("salePrice", 0)

        if discount_price > 0:
            return int(discount_price), "성공"
        else:
            return None, "상품 판매가가 0원입니다."

    except Exception as e:
        return None, f"API 통신 오류: {str(e)}"


# ------------------------------------------------------------------
# 2. 전산 데이터베이스 로드
# ------------------------------------------------------------------


@st.cache_data(ttl=5)
def load_master_db():
    possible_paths = [
        "price_calculator/master_db.xlsx",
        "price_calculator/전체상품목록_20260725210142_6999190.xlsx",
        "master_db.xlsx",
        "전체상품목록_20260725210142_6999190.xlsx",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            try:
                df = pd.read_excel(path)
                return df, path
            except Exception as e:
                return None, f"파일 읽기 실패: {str(e)}"

    folder_files = []
    if os.path.exists("price_calculator"):
        folder_files = os.listdir("price_calculator")

    return (
        None,
        f"파일 없음 (price_calculator 폴더 안 파일 목록: {folder_files})",
    )


db, status_msg = load_master_db()

# ------------------------------------------------------------------
# 3. 상품 부분 검색 및 자동 선택
# ------------------------------------------------------------------
st.subheader("1. 상품 검색 및 데이터 선택")

selected_product_name = ""
yuan_price = 0.0
smartstore_url = ""
db_selling_price = 0

if db is not None:
    st.success(f"✅ 전산 DB 로드 성공! (총 {len(db):,}개 상품 데이터)")

    search_input = st.text_input(
        "🔍 상품명 키워드 부분 검색:",
        placeholder="단어를 띄어쓰기로 여러 개 입력할 수 있습니다. (예: 메디치 튤립)",
    )

    if search_input.strip():
        keywords = search_input.strip().split()

        condition = pd.Series(True, index=db.index)
        for kw in keywords:
            condition &= (
                db["상품명"]
                .astype(str)
                .str.contains(kw, case=False, na=False, regex=False)
            )

        filtered_db = db[condition]
        count = len(filtered_db)

        if count == 1:
            row = filtered_db.iloc[0]
            selected_product_name = str(row.get("상품명", ""))

            try:
                yuan_price = float(row.get("매입위안", 0.0))
                if math.isnan(yuan_price):
                    yuan_price = 0.0
            except Exception:
                yuan_price = 0.0

            try:
                db_selling_price = int(row.get("판매가", 0))
                if math.isnan(db_selling_price):
                    db_selling_price = 0
            except Exception:
                db_selling_price = 0

            smartstore_url = str(
                row.get("스마트스토어링크", row.get("상품설명2", "")) or ""
            )
            if smartstore_url == "nan":
                smartstore_url = ""

            st.success(
                f"⚡ 1건 매칭되어 자동 선택됨: **{selected_product_name}**"
            )

        elif count > 1:
            options = ["-- 아래 목록에서 상품 선택 --"] + filtered_db[
                "상품명"
            ].tolist()
            chosen = st.selectbox(
                f"🎯 검색 결과 ({count}건) 중 선택하세요:", options
            )

            if chosen != "-- 아래 목록에서 상품 선택 --":
                row = filtered_db[filtered_db["상품명"] == chosen].iloc[0]
                selected_product_name = str(row.get("상품명", ""))

                try:
                    yuan_price = float(row.get("매입위안", 0.0))
                    if math.isnan(yuan_price):
                        yuan_price = 0.0
                except Exception:
                    yuan_price = 0.0

                try:
                    db_selling_price = int(row.get("판매가", 0))
                    if math.isnan(db_selling_price):
                        db_selling_price = 0
                except Exception:
                    db_selling_price = 0

                smartstore_url = str(
                    row.get("스마트스토어링크", row.get("상품설명2", "")) or ""
                )
                if smartstore_url == "nan":
                    smartstore_url = ""

                st.info(f"📌 선택된 상품명: **{selected_product_name}**")
        else:
            st.warning("⚠️ 입력하신 키워드와 일치하는 상품이 없습니다.")
else:
    st.error(f"⚠️ 전산 데이터 연결 안됨: {status_msg}")

st.markdown("---")

# ------------------------------------------------------------------
# 4. 상세 정보 입력 및 출처 표기 기능
# ------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    if yuan_price <= 0:
        st.markdown(
            "<div style='background-color:#ffe6e6; padding:8px; border-radius:5px; border:1px solid #ff4d4d; color:#cc0000; font-weight:bold; margin-bottom:8px;'>🚨 [필수] 매입위안을 입력하세요!</div>",
            unsafe_allow_html=True,
        )

    input_yuan = st.number_input(
        "매입위안 (¥)",
        value=float(yuan_price),
        step=0.1,
    )

with col2:
    if not smartstore_url.strip():
        st.markdown(
            "<div style='background-color:#fff0e6; padding:8px; border-radius:5px; border:1px solid #ff9933; color:#cc5500; font-weight:bold; margin-bottom:8px;'>⚠️ 스마트스토어 주소가 없습니다! (붙여넣기)</div>",
            unsafe_allow_html=True,
        )

    input_url = st.text_input(
        "스마트스토어 주소",
        value=smartstore_url,
        placeholder="https://smartstore.naver.com/...",
    )

    if input_url.strip():
        st.link_button("🔗 스마트스토어 상품페이지 직접 열기", input_url.strip())

# 스마트스토어 실시간 API 또는 전산 등록가 자동 추출 및 출처 판단
api_fetched_price, api_msg = fetch_naver_api_price(input_url)
default_ss_price = 0
price_status_type = ""
price_source_badge = ""

if api_fetched_price is not None:
    default_ss_price = api_fetched_price
    price_status_type = "success"
    price_source_badge = "🟢 **네이버 공식 API**로 불러온 실시간 판매가입니다."
elif db_selling_price > 0:
    default_ss_price = db_selling_price
    price_status_type = "error"
    # 📌 DB 등록가는 확인용이므로 붉은색 강한 경고 박스로 표기
    price_source_badge = f"🚨 **[주의] 네이버 API 연동 실패 ({api_msg})**\n\n이 금액은 API 실시간가가 아닌 **전산 DB 엑셀에 등록되어 있던 옛날 판매가**입니다. 실제 스마트스토어 판매가와 다를 수 있으니 반드시 확인 후 수정해 주세요!"
else:
    price_status_type = "info"
    price_source_badge = (
        "⚪ 등록된 가격이 없어 0원으로 표시됩니다. (직접 입력 가능)"
    )

col_ss1, col_ss2 = st.columns([2, 1])
with col_ss1:
    input_ss_price = st.number_input(
        "네이버 스마트스토어 실제 판매가 (직접 수정/입력 가능)",
        value=int(default_ss_price),
        step=100,
        help="주소를 통해 자동 수집된 가격이 있거나 직접 변경할 금액을 입력하세요.",
    )

    # 📌 출처 표기 시각화
    if price_status_type == "error":
        st.error(price_source_badge)
    elif price_status_type == "success":
        st.success(price_source_badge)
    else:
        st.caption(price_source_badge)

# ------------------------------------------------------------------
# 5. 스마트스토어 판매가 비교 및 재계산 로직
# ------------------------------------------------------------------
if input_yuan > 0:

    def roundup_100(val):
        return math.ceil(val / 100) * 100

    # 1) 기존 원가 기반 계산 (기본 수식)
    b1_cost_no_vat = input_yuan * 320
    b2_cost_vat = b1_cost_no_vat * 1.1

    orig_consumer = roundup_100(b2_cost_vat * 3)
    orig_recommend = roundup_100(b2_cost_vat * 2)  # 원가 기준 추천가

    # 2) 스마트스토어 실제 판매가와 추천가 비교
    ss_price = input_ss_price

    if ss_price > orig_recommend:
        final_recommend = ss_price
        final_consumer = roundup_100(ss_price * 1.33)
        if final_consumer <= ss_price:
            final_consumer = roundup_100(ss_price * 1.5)

        price_case_msg = "info"
        price_case_text = f"💡 **스마트스토어 판매가({ss_price:,}원)**가 원가 기준 추천가({orig_recommend:,}원)보다 높아 **스마트스토어 판매가를 기준가**로 적용하여 재산출했습니다."

    else:
        final_recommend = orig_recommend
        final_consumer = orig_consumer

        if ss_price > 0 and ss_price < orig_recommend:
            price_case_msg = "warning"
            price_case_text = f"🚨 **주의:** 현재 스마트스토어 판매가({ss_price:,}원)가 추천 판매가({orig_recommend:,}원)보다 낮습니다! 마진 확보를 위해 **스마트스토어 판매가를 인상**하는 것을 권장합니다."
        else:
            price_case_msg = "normal"
            price_case_text = ""

    # 3) 최종 기준가 바탕 마켓별 산출
    b5_09 = roundup_100(final_recommend * 0.9)
    b11_dome_shin = roundup_100(b5_09 * 0.95)

    b14_tobizon = b11_dome_shin
    b15_sellingkok = b14_tobizon
    b16_onchannel = b15_sellingkok

    b5_12 = roundup_100(final_recommend * 1.2)

    prices = {
        "추천 소비자가": final_consumer,
        "추천 판매가 (기준가)": final_recommend,
        "--- 도매 마켓 그룹 ---": "",
        "오너클랜": b5_09,
        "지마켓 / 옥션": final_recommend,
        "쿠팡": final_recommend,
        "K셀러": b5_09,
        "도매창고": b5_09,
        "도매의신": b11_dome_shin,
        "도매꾹 & 도매매": b5_09,
        "펀앤쇼핑": b5_09,
        "투비즈온": b14_tobizon,
        "셀링콕 등 도매마켓": b15_sellingkok,
        "온채널": b16_onchannel,
        "11번가": final_recommend,
        "네이버 스마트스토어": final_recommend,
        "--- 홈쇼핑 / 패션몰 그룹 ---": "",
        "패션플러스": b5_12,
        "GS홈쇼핑": b5_12,
        "SSG닷컴": b5_12,
        "NS홈쇼핑": b5_12,
        "텐바이텐": b5_12,
    }

    st.markdown("---")
    st.subheader("2. 마켓별 산출 판매가 목록")

    st.info(
        f"💡 **원가 정보:** 매입가 ¥{input_yuan:,} ➔ 원가(VAT포함) {int(b2_cost_vat):,}원 | **원가 기준 기본 추천가:** {orig_recommend:,}원"
    )

    if price_case_msg == "info":
        st.info(price_case_text)
    elif price_case_msg == "warning":
        st.warning(price_case_text)

    for market, price in prices.items():
        if market.startswith("---"):
            st.caption(f"**{market}**")
        else:
            col_m, col_p = st.columns([2, 1])
            col_m.write(f"**{market}**")

            if isinstance(price, (int, float)):
                col_p.code(f"{price:,}", language=None)
            else:
                col_p.code(f"{price}", language=None)

else:
    st.warning(
        "매입위안 금액을 입력하거나 상품을 검색하면 판매가가 산출됩니다."
    )
