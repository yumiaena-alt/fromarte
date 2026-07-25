import math
import os
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="프롬아떼 도매 마켓 판매가 계산기", page_icon="💰", layout="centered"
)

st.title("💰 마켓별 판매가 자동 계산기")
st.write(
    "전산 상품명을 검색하거나 매입위안을 입력하면 각 도매 마켓별 판매가가 자동으로 계산됩니다."
)

# ------------------------------------------------------------------
# 1. 전산 데이터베이스 로드 (실제 폴더 경로 price_calculator 반영)
# ------------------------------------------------------------------


@st.cache_data(ttl=5)
def load_master_db():
    # 경로 목록 (price_calculator 언더바 적용)
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

    # 폴더 내 실제 파일 목록 체크
    folder_files = []
    if os.path.exists("price_calculator"):
        folder_files = os.listdir("price_calculator")

    return (
        None,
        f"파일 없음 (price_calculator 폴더 안 파일 목록: {folder_files})",
    )


db, status_msg = load_master_db()

# ------------------------------------------------------------------
# 2. 상품 검색 및 입력
# ------------------------------------------------------------------
st.subheader("1. 상품 검색 및 입력")

product_name = ""
yuan_price = 0.0
smartstore_url = ""

if db is not None:
    st.success(f"✅ 전산 DB 로드 성공! (총 {len(db):,}개 상품 데이터)")

    search_keyword = st.text_input(
        "🔍 상품명 검색:",
        placeholder="전산 상품명의 일부를 입력하세요 (예: 콰자, 뜨개꽃 등)",
    )

    if search_keyword:
        filtered_db = db[
            db["상품명"]
            .astype(str)
            .str.contains(search_keyword, case=False, na=False)
        ]

        if not filtered_db.empty:
            selected_product = st.selectbox(
                f"매칭된 상품 ({len(filtered_db)}건) 중 선택:",
                filtered_db["상품명"].tolist(),
            )
            row = filtered_db[filtered_db["상품명"] == selected_product].iloc[0]

            product_name = str(row.get("상품명", ""))

            # 매입위안
            try:
                yuan_price = float(row.get("매입위안", 0.0))
            except Exception:
                yuan_price = 0.0

            # 스마트스토어 링크
            smartstore_url = str(
                row.get("스마트스토어링크", row.get("상품설명2", "")) or ""
            )
            if smartstore_url == "nan":
                smartstore_url = ""
        else:
            st.warning("⚠️ 검색 결과가 없습니다.")
else:
    st.error(f"⚠️ 전산 데이터 연결 안됨: {status_msg}")

st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    input_yuan = st.number_input(
        "매입위안 (¥)",
        value=float(yuan_price),
        step=0.1,
    )
with col2:
    input_url = st.text_input(
        "스마트스토어 주소",
        value=smartstore_url,
        placeholder="https://smartstore.naver.com/...",
    )

# ------------------------------------------------------------------
# 3. 판매가 계산 로직
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

    prices = {
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
            col_p.code(f"{price:,}원", language=None)

else:
    st.warning(
        "매입위안 금액을 입력하거나 상품을 검색하면 판매가가 산출됩니다."
    )
