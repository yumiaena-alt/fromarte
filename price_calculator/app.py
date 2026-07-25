import math
import pandas as pd
import streamlit as st

# Streamlit 기본 페이지 설정
st.set_page_config(
    page_title="프롬아떼 도매 마켓 판매가 계산기", page_icon="💰", layout="centered"
)

st.title("💰 마켓별 판매가 자동 계산기")
st.write(
    "전산 상품명을 검색하거나 매입위안을 입력하면 각 도매 마켓별 판매가가 자동으로 계산됩니다."
)

# ------------------------------------------------------------------
# 1. 전산 데이터베이스 로드 (master_db.xlsx)
# ------------------------------------------------------------------


@st.cache_data(ttl=600)
def load_master_db():
    try:
        df = pd.read_excel("master_db.xlsx")
        return df
    except Exception:
        return None


db = load_master_db()

# ------------------------------------------------------------------
# 2. 상품 정보 조회 및 입력
# ------------------------------------------------------------------
st.subheader("1. 상품 정보 조회 및 입력")

product_name = ""
yuan_price = 0.0
smartstore_url = ""

if db is not None:
    search_keyword = st.text_input(
        "🔍 상품명 검색 (전산 상품명의 일부를 입력하세요):"
    )

    if search_keyword:
        filtered_db = db[
            db["상품명"]
            .astype(str)
            .str.contains(search_keyword, case=False, na=False)
        ]

        if not filtered_db.empty:
            selected_product = st.selectbox(
                "매칭된 상품 선택:", filtered_db["상품명"].tolist()
            )
            row = filtered_db[filtered_db["상품명"] == selected_product].iloc[0]

            product_name = row.get("상품명", "")
            yuan_price = float(row.get("매입위안", 0.0) or 0.0)
            smartstore_url = str(row.get("상품설명2", "") or "")
        else:
            st.warning("검색 결과가 없습니다. 아래에 수동으로 입력해 주세요.")

col1, col2 = st.columns(2)
with col1:
    input_yuan = st.number_input(
        "매입위안 (¥)",
        value=yuan_price,
        step=0.1,
        help="값이 없으면 직접 입력하세요.",
    )
with col2:
    input_url = st.text_input(
        "스마트스토어 주소 (선택)",
        value=smartstore_url,
        placeholder="https://smartstore.naver.com/...",
    )

# ------------------------------------------------------------------
# 3. 엑셀 이미지 기반 수식 100% 동일 적용
# ------------------------------------------------------------------
if input_yuan > 0:
    # 100원 단위 올림 함수
    def roundup_100(val):
        return math.ceil(val / 100) * 100

    # [B1] 원가입력(VAT 비포함) = 매입위안 * 320
    b1_cost_no_vat = input_yuan * 320

    # [B2] 원가 VAT 포함 = B1 * 1.1
    b2_cost_vat = b1_cost_no_vat * 1.1

    # [B4] 추천 소비자가 = B2 * 3
    b4_consumer = roundup_100(b2_cost_vat * 3)

    # [B5] 추천 판매가 (기준가) = B2 * 2
    b5_recommend = roundup_100(b2_cost_vat * 2)

    # [B6, B9, B10, B12, B13] = B5 * 0.9 (오너클랜, K셀러, 도매창고, 도매꾹&도매매, 펀앤쇼핑)
    b5_09 = roundup_100(b5_recommend * 0.9)

    # [B11] 도매의신 = B10(도매창고) * 0.95
    b11_dome_shin = roundup_100(b5_09 * 0.95)

    # [B14, B15, B16] 투비즈온, 셀링콕, 온채널 = 도매의신과 동일 금액
    b14_tobizon = b11_dome_shin
    b15_sellingkok = b14_tobizon
    b16_onchannel = b15_sellingkok

    # [B18~B22] 패션플러스 등 홈쇼핑/패션몰 = B5 * 1.2
    b5_12 = roundup_100(b5_recommend * 1.2)

    # 마켓 순서별 정리 (엑셀 표 순서와 일치)
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

    # ------------------------------------------------------------------
    # 4. 결과 화면 출력
    # ------------------------------------------------------------------
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
