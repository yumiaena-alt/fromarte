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
        # price-calculator 폴더 내 master_db.xlsx 읽어오기
        df = pd.read_excel("price-calculator/master_db.xlsx")
        return df
    except Exception:
        try:
            # 루트 경로에 있을 경우 대비
            df = pd.read_excel("master_db.xlsx")
            return df
        except Exception:
            return None


db = load_master_db()

# ------------------------------------------------------------------
# 2. 상품 정보 검색 및 수동 입력 영역 (항상 노출)
# ------------------------------------------------------------------
st.subheader("1. 상품 검색 및 입력")

product_name = ""
yuan_price = 0.0
smartstore_url = ""

# DB 연결 상태 안내
if db is not None:
    st.success(f"✅ 전산 DB 연결 완료 (총 {len(db):,}개 상품 데이터)")

    search_keyword = st.text_input(
        "🔍 상품명 검색:",
        placeholder="전산 상품명의 일부를 입력하세요 (예: 오버핏)",
    )

    if search_keyword:
        filtered_db = db[
            db["상품명"]
            .astype(str)
            .str.contains(search_keyword, case=False, na=False)
        ]

        if not filtered_db.empty:
            selected_product = st.selectbox(
                f"매칭된 상품 ({len(filtered_db)}건) 중 선택하세요:",
                filtered_db["상품명"].tolist(),
            )
            row = filtered_db[filtered_db["상품명"] == selected_product].iloc[0]

            product_name = str(row.get("상품명", ""))
            try:
                yuan_price = float(row.get("매입위안", 0.0))
            except ValueError:
                yuan_price = 0.0

            smartstore_url = str(row.get("상품설명2", "") or "")
            if smartstore_url == "nan":
                smartstore_url = ""
        else:
            st.warning(
                "⚠️ 검색 결과가 없습니다. 아래에 수동으로 입력해 주세요."
            )
else:
    st.error(
        "⚠️ `master_db.xlsx` 전산 엑셀 파일을 찾을 수 없습니다. 깃허브 `price-calculator` 폴더 안에 올렸는지 확인해주세요!"
    )
    st.text_input(
        "🔍 상품명 (전산 DB 연결 필요)",
        disabled=True,
        placeholder="master_db.xlsx 파일이 업로드되면 검색창이 활성화됩니다.",
    )

st.markdown("---")

# 검색 결과가 반영되거나 직접 수정할 수 있는 입력란
col1, col2 = st.columns(2)
with col1:
    input_yuan = st.number_input(
        "매입위안 (¥)",
        value=float(yuan_price),
        step=0.1,
        help="값에 문제가 있거나 없는 경우 직접 숫자를 입력하세요.",
    )
with col2:
    input_url = st.text_input(
        "스마트스토어 주소 (상품설명2)",
        value=smartstore_url,
        placeholder="https://smartstore.naver.com/...",
    )

# ------------------------------------------------------------------
# 3. 엑셀 이미지 기반 수식 계산 (100% 반영)
# ------------------------------------------------------------------
if input_yuan > 0:

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

    # 마켓 순서 정리
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
