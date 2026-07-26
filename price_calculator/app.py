import math
import os
import re
import urllib.request
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="프롬아떼 도매 마켓 판매가 계산기", page_icon="💰", layout="centered"
)

st.title("💰 마켓별 판매가 자동 계산기")
st.write(
    "전산 상품명을 키워드로 부분 검색하여 선택하거나, 매입위안을 직접 입력해 마켓별 판매가를 산출하세요."
)

# ------------------------------------------------------------------
# 1. 스마트스토어 실제 판매가 크롤링 함수
# ------------------------------------------------------------------


@st.cache_data(ttl=300)
def fetch_smartstore_real_price(url):
    if not url or "smartstore.naver.com" not in url:
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            html = response.read().decode("utf-8", errors="ignore")

            # 1) meta tag (og:price:amount) 추출
            og_price = re.findall(
                r'property=["\']og:price:amount["\']\s+content=["\'](\d+)["\']',
                html,
            )
            if og_price:
                return int(og_price[0])

            # 2) JSON-LD 또는 price/discountedPrice 추출
            price_match = re.findall(
                r'["\']discountedPrice["\']\s*:\s*(\d+)', html
            )
            if price_match:
                return int(price_match[0])

            price_match2 = re.findall(r'["\']price["\']\s*:\s*(\d+)', html)
            if price_match2:
                return int(price_match2[0])
    except Exception:
        pass
    return None


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
            # ⚡ 1건일 경우 드롭박스 없이 즉시 자동 선택!
            row = filtered_db.iloc[0]
            selected_product_name = str(row.get("상품명", ""))

            try:
                yuan_price = float(row.get("매입위안", 0.0))
                if math.isnan(yuan_price):
                    yuan_price = 0.0
            except Exception:
                yuan_price = 0.0

            smartstore_url = str(
                row.get("스마트스토어링크", row.get("상품설명2", "")) or ""
            )
            if smartstore_url == "nan":
                smartstore_url = ""

            st.success(f"⚡ 1건 매칭되어 자동 선택됨: **{selected_product_name}**")

        elif count > 1:
            # 🎯 2건 이상일 경우만 드롭다운 노출
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

# ------------------------------------------------------------------
# 5. 마켓별 판매가 자동 계산 및 크롤링 판매가 출력
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

    # 실제 스마트스토어 링크 페이지에서 가격 크롤링
    real_price = fetch_smartstore_real_price(input_url)
    real_price_str = f"{real_price:,}원" if real_price else "불러오기 실패/링크없음"

    # 추천소비자가 바로 위에 '네이버 스마트스토어 실제 판매가' 배치
    prices = {
        "🏷️ 네이버 스마트스토어 실제 판매가 (크롤링)": real_price_str,
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
