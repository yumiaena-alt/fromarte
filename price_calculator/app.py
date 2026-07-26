import math
import os
import re
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="프롬아떼 도매 마켓 판매가 계산기", page_icon="💰", layout="centered"
)

st.title("💰 마켓별 판매가 자동 계산기")
st.write(
    "전산 상품명을 키워드로 부분 검색하여 선택하거나, 매입위안을 직접 입력해 마켓별 판매가를 산출하세요."
)

# ------------------------------------------------------------------
# 1. 네이버 커머스 API 연동 함수 (실시간 공식 판매가)
# ------------------------------------------------------------------


@st.cache_data(ttl=60)
def fetch_naver_api_price(smartstore_url):
    if not smartstore_url or "smartstore.naver.com" not in smartstore_url:
        return None, "유효한 스마트스토어 주소가 아닙니다."

    # URL에서 상품 ID(숫자) 추출
    match = re.search(r"products/(\d+)", smartstore_url)
    if not match:
        return None, "상품 ID를 추출할 수 없습니다."

    product_id = match.group(1)

    # Secrets 및 환경변수 확인
    client_id = st.secrets.get("NAVER_CLIENT_ID") or os.environ.get(
        "NAVER_CLIENT_ID"
    )
    client_secret = st.secrets.get("NAVER_CLIENT_SECRET") or os.environ.get(
        "NAVER_CLIENT_SECRET"
    )

    if not client_id or not client_secret:
        return None, "Streamlit Secrets 설정이 필요합니다."

    try:
        # 1) 토큰 발급
        token_url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "type": "SELF",
        }
        token_res = requests.post(token_url, data=token_data, timeout=5)
        token_json = token_res.json()
        access_token = token_json.get("access_token")

        if not access_token:
            return None, "API 토큰 발급 실패"

        # 2) 상품 상세 조회
        api_url = f"https://api.commerce.naver.com/external/v2/products/channel-products/{product_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        res = requests.get(api_url, headers=headers, timeout=5)
        data = res.json()

        # 실시간 가격 추출 (할인가 또는 기준가)
        origin_product = data.get("originProduct", {})
        discount_price = origin_product.get("salePrice", 0)

        if discount_price > 0:
            return int(discount_price), "성공"
        else:
            return None, "상품 가격 정보를 찾을 수 없습니다."

    except Exception as e:
        return None, f"API 접속 오류 ({str(e)})"


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
                return None, f"파일은 찾았으나 읽기 실패 ({path}): {str(e)}"

    folder_files = []
    if os.path.exists("price_calculator"):
        folder_files = os.listdir("price_calculator")

    return (
        None,
        f"파일 없음 (price_calculator 폴더 안 파일 목록: {folder_files})",
    )


db, status_msg = load_master_db()

# ------------------------------------------------------------------
# 3. 스마트 부분 검색 및 자동 선택 (1건 시 드롭박스 패스)
# ------------------------------------------------------------------
st.subheader("1. 상품 검색 및 선택")

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

            st.success(f"⚡ 1건 매칭되어 자동 선택됨: **{selected_product_name}**")

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
# 4. 상세 정보 입력 및 붉은색 경고
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

# ------------------------------------------------------------------
# 5. 마켓별 판매가 자동 계산 및 API 연동 판매가 출력
# ------------------------------------------------------------------
if input_yuan > 0:

    def roundup_100(val):
        return math.ceil(val / 100) * 100

    b1_cost_no_vat = input_yuan * 320
    b2_cost_vat = b1_cost_no_vat * 1.1

    b4_consumer = roundup_100(b2_cost_vat * 3)
    b5_recommend = roundup_100(b2_cost_vat * 2)

    b5_09 = roundup_100(b5_recommend * 0.9)
    b11_dome_shin = roundup_100(b5_09 * 0.95)

    b14_tobizon = b11_dome_shin
    b15_sellingkok = b14_tobizon
    b16_onchannel = b15_sellingkok

    b5_12 = roundup_100(b5_recommend * 1.2)

    # 네이버 공식 커머스 API로 실시간가 조회
    api_price, api_msg = fetch_naver_api_price(input_url)

    if api_price:
        smartstore_display_price = f"{api_price:,}원 (네이버 공식 API 연동)"
    elif db_selling_price > 0:
        smartstore_display_price = f"{db_selling_price:,}원 (전산등록가)"
    else:
        smartstore_display_price = f"조회 실패 ({api_msg})"

    prices = {
        "🏷️ 네이버 스마트스토어 실제 판매가": smartstore_display_price,
        "추천 소비자가": b4_consumer,
        "추천 판매가 (기준가)": b5_recommend,
        "--- 도매 마켓 그룹 ---": "",
        "오너클랜": b5_09,
        "지마켓 / 옥션": b5_recommend,
        "쿠팡": b5_recommend,
        "K셀러": b5_09,
        "도매창고": b5_09,
        "도매의신": b11_dome_shin,
        "도매꾹 & 도매매": b5_09,
        "펀앤쇼핑": b5_09,
        "투비즈온": b14_tobizon,
        "셀링콕 등 도매마켓": b15_sellingkok,
        "온채널": b16_onchannel,
        "11번가": b5_recommend,
        "네이버 스마트스토어": b5_recommend,
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
        f"💡 **원가 정보:** 매입가 ¥{input_yuan:,} ➔ 원가(VAT포함) {int(b2_cost_vat):,}원"
    )

    for market, price in prices.items():
        if market.startswith("---"):
            st.caption(f"**{market}**")
        else:
            col_m, col_p = st.columns([2, 1])
            col_m.write(f"**{market}**")
            if isinstance(price, int):
                col_p.code(f"{price:,}원", language=None)
            else:
                col_p.code(f"{price}", language=None)

else:
    st.warning(
        "매입위안 금액을 입력하거나 상품을 검색하면 판매가가 산출됩니다."
    )
