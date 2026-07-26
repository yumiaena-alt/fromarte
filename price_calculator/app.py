import math
import os
import re
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="프롬아떼 도매 마켓 판매가 계산기", page_icon="💰", layout="centered"
)

st.title("💰 마켓별 판매가 자동 계산기")
st.write(
    "전산 상품을 검색하거나 매입위안/스마트스토어 판매가를 입력하여 맞춤형 판매가를 산출하세요."
)

# ------------------------------------------------------------------
# 1. 전산 데이터베이스 로드
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
# 2. 상품 부분 검색 및 자동 선택
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
# 3. 상세 정보 입력 및 스마트스토어 확인 로직
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
    input_url = st.text_input(
        "스마트스토어 주소",
        value=smartstore_url,
        placeholder="https://smartstore.naver.com/fromarte/products/...",
    )

    # 주소 유효성 검사 및 안내 메시지
    clean_url = input_url.strip()

    if not clean_url:
        st.warning(
            "⚠️ 스마트스토어 주소가 비어있습니다. 수동으로 주소를 입력해 주세요."
        )
    elif not (
        clean_url.startswith("http://") or clean_url.startswith("https://")
    ) or not ("naver.com" in clean_url or "products/" in clean_url):
        st.error(
            "🚨 올바른 스마트스토어 주소 형식이 아닙니다. (예: https://smartstore.naver.com/...)"
        )
    else:
        # 올바른 주소 형식인 경우 즉시 바로가기 버튼 제공
        st.link_button(
            "🔗 스마트스토어 상품페이지 직접 열기",
            clean_url,
            use_container_width=True,
        )

# ------------------------------------------------------------------
# 4. 스마트스토어 판매가 입력 및 경고창 끄기 제어
# ------------------------------------------------------------------
col_ss1, col_ss2 = st.columns([2, 1])

with col_ss1:
    input_ss_price = st.number_input(
        "네이버 스마트스토어 실제 판매가 (직접 확인 후 수정/입력)",
        value=int(db_selling_price),
        step=100,
        help="스마트스토어 상품페이지에서 실제 가격을 확인한 후 입력하세요.",
    )

    # 사용자가 가격을 수정했는지 여부 확인 (전산 DB 초기값과 다른지 비교)
    # 📌 전산 DB 값 그대로이면 붉은 경고창 표시 ➔ 숫자를 직접 변경하면 경고창이 꺼지고 정상(green) 안내 표시
    if db_selling_price > 0:
        if input_ss_price == db_selling_price:
            st.error(
                f"🚨 **[확인 필요] 전산 DB에 등록된 옛날 판매가({db_selling_price:,}원)입니다.**\n\n"
                f"위 버튼을 눌러 실제 스마트스토어 판매가를 확인하신 후, 수치가 다르면 숫자를 입력해 주세요. (가격을 확인/수정하면 이 경고창이 꺼집니다)"
            )
        else:
            st.success(
                f"🟢 **실제 스마트스토어 판매가({input_ss_price:,}원)가 확인되어 정상 반영되었습니다.**"
            )
    else:
        if input_ss_price > 0:
            st.success(
                f"🟢 **스마트스토어 판매가({input_ss_price:,}원)가 직접 입력되었습니다.**"
            )
        else:
            st.caption(
                "⚪ 등록된 가격이 없어 0원으로 표시됩니다. (스마트스토어 확인 후 직접 입력하세요)"
            )

# ------------------------------------------------------------------
# 5. 마켓별 판매가 자동 산출 로직
# ------------------------------------------------------------------
if input_yuan > 0:

    def roundup_100(val):
        return math.ceil(val / 100) * 100

    # 1) 원가 기반 기본 수식
    b1_cost_no_vat = input_yuan * 320
    b2_cost_vat = b1_cost_no_vat * 1.1

    orig_consumer = roundup_100(b2_cost_vat * 3)
    orig_recommend = roundup_100(b2_cost_vat * 2)  # 원가 기준 추천가

    # 2) 실제 스마트스토어 판매가 기준가 재설정
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

    # 3) 마켓별 계산
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
