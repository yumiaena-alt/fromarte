import math
import os
import re
import google.generativeai as genai
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="프롬아떼 스마트 커머스 툴",
    page_icon="🛍️",
    layout="centered",
)

st.title("🛍️ 프롬아떼 스마트 커머스 툴")
st.write("원하시는 기능을 상단 탭에서 선택하여 사용하세요.")

# ------------------------------------------------------------------
# 공통 데이터 로드 및 API 연동 함수
# ------------------------------------------------------------------


@st.cache_data(ttl=60)
def fetch_naver_api_price(smartstore_url):
    if not smartstore_url or "smartstore.naver.com" not in smartstore_url:
        return None

    match = re.search(r"products/(\d+)", smartstore_url)
    if not match:
        return None

    product_id = match.group(1)

    client_id = st.secrets.get("NAVER_CLIENT_ID") or os.environ.get(
        "NAVER_CLIENT_ID"
    )
    client_secret = st.secrets.get("NAVER_CLIENT_SECRET") or os.environ.get(
        "NAVER_CLIENT_SECRET"
    )

    if not client_id or not client_secret:
        return None

    try:
        token_url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "type": "SELF",
        }
        token_res = requests.post(token_url, data=token_data, timeout=5)
        access_token = token_res.json().get("access_token")

        if not access_token:
            return None

        api_url = f"https://api.commerce.naver.com/external/v2/products/channel-products/{product_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        res = requests.get(api_url, headers=headers, timeout=5)
        data = res.json()

        origin_product = data.get("originProduct", {})
        discount_price = origin_product.get("salePrice", 0)

        if discount_price > 0:
            return int(discount_price)
    except Exception:
        pass
    return None


@st.cache_data(ttl=5)
def load_master_db():
    possible_paths = [
        "title_generator/master_db.xlsx",
        "title_generator/전체상품목록_20260725210142_6999190.xlsx",
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
    if os.path.exists("title_generator"):
        folder_files = os.listdir("title_generator")

    return (
        None,
        f"파일 없음 (title_generator 폴더 안 파일 목록: {folder_files})",
    )


db, status_msg = load_master_db()

# ------------------------------------------------------------------
# 상단 탭 분리 (1. 마켓별 판매가 계산기 / 2. Title Generator)
# ------------------------------------------------------------------
tab1, tab2 = st.tabs(["💰 마켓별 판매가 계산기", "🏷️ Title Generator"])

# ==================================================================
# TAB 1: 마켓별 판매가 계산기
# ==================================================================
with tab1:
    st.subheader("1. 전산 상품 검색 & 매입 정보")

    selected_product_name = ""
    yuan_price = 0.0
    smartstore_url = ""
    db_selling_price = 0

    if db is not None:
        st.success(f"✅ 전산 DB 로드 성공! (총 {len(db):,}개 상품 데이터)")

        search_input = st.text_input(
            "🔍 상품명 키워드 부분 검색:",
            placeholder="단어를 띄어쓰기로 여러 개 입력할 수 있습니다. (예: 메디치 튤립)",
            key="price_search_input",
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
                    f"🎯 검색 결과 ({count}건) 중 선택하세요:",
                    options,
                    key="price_select_box",
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
                        row.get("스마트스토어링크", row.get("상품설명2", ""))
                        or ""
                    )
                    if smartstore_url == "nan":
                        smartstore_url = ""

                    st.info(
                        f"📌 선택된 상품명: **{selected_product_name}**"
                    )
            else:
                st.warning("⚠️ 입력하신 키워드와 일치하는 상품이 없습니다.")
    else:
        st.error(f"⚠️ 전산 데이터 연결 안됨: {status_msg}")

    st.markdown("---")

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
            key="price_yuan_input",
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
            key="price_url_input",
        )

        if input_url.strip():
            st.link_button(
                "🔗 스마트스토어 상품페이지 직접 열기", input_url.strip()
            )

    api_fetched_price = fetch_naver_api_price(input_url)
    default_ss_price = 0
    price_source_badge = ""

    if api_fetched_price:
        default_ss_price = api_fetched_price
        price_source_badge = (
            "🟢 **네이버 공식 API**로 불러온 실시간 판매가입니다."
        )
    elif db_selling_price > 0:
        default_ss_price = db_selling_price
        price_source_badge = (
            "🔵 **전산 DB 엑셀**에 등록되어 있던 판매가입니다."
        )
    else:
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
            key="price_ss_input",
        )
        st.caption(price_source_badge)

    if input_yuan > 0:

        def roundup_100(val):
            return math.ceil(val / 100) * 100

        b1_cost_no_vat = input_yuan * 320
        b2_cost_vat = b1_cost_no_vat * 1.1

        orig_consumer = roundup_100(b2_cost_vat * 3)
        orig_recommend = roundup_100(b2_cost_vat * 2)

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

# ==================================================================
# TAB 2: Title Generator
# ==================================================================
with tab2:
    gemini_api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get(
        "GEMINI_API_KEY"
    )

    st.subheader("🏷️ SEO 키워드 기반 최적화 상품명 생성기")
    st.caption(
        "네이버 광고주 센터 데이터를 기반으로 100byte SEO 상품명을 자동 조합합니다."
    )

    col_info1, col_info2 = st.columns(2)
    with col_info1:
        brand_name = st.text_input(
            "브랜드명", value="프롬아떼", key="tg_brand_name"
        )
        product_type = st.text_input(
            "상품 종류/기본명",
            placeholder="예: 어린이 자전거 바구니",
            key="tg_product_type",
        )
    with col_info2:
        product_features = st.text_input(
            "주요 특징/소재",
            placeholder="예: 플라스틱, 자체디자인, 킥보드겸용",
            key="tg_product_features",
        )
        product_target = st.text_input(
            "타겟/용도", placeholder="예: 어린이, 유아", key="tg_product_target"
        )

    st.markdown("#### 📥 네이버 키워드 도구 데이터 입력")
    raw_keywords_text = st.text_area(
        "네이버 광고주 센터에서 추출한 키워드 및 검색량 목록을 붙여넣으세요:",
        placeholder="예시 (키워드 / 월간검색량 순으로 붙여넣기):\n자전거바구니 15000\n어린이자전거바구니 8200\n킥보드바구니 3100\n유아바구니 1200",
        height=120,
        key="tg_raw_keywords",
    )

    valid_keywords = []

    if raw_keywords_text.strip():
        lines = raw_keywords_text.strip().split("\n")
        parsed_keywords = []

        for line in lines:
            parts = re.split(r"[\t,,\s]+", line.strip())
            if parts and parts[0]:
                kw = parts[0]
                count = (
                    int(parts[1])
                    if len(parts) > 1 and parts[1].isdigit()
                    else 0
                )
                parsed_keywords.append((kw, count))

        parsed_keywords.sort(key=lambda x: x[1], reverse=True)

        st.markdown("#### 🖐️ [휴먼 터치] 연관 없는 키워드 체크 해제")
        st.caption(
            "실제 검색량이 높은 순서대로 정렬되었습니다. **내 상품과 맞지 않는 단어만 체크 해제**하세요!"
        )

        cols = st.columns(4)
        selected_kw_list = []

        for idx, (kw, count) in enumerate(parsed_keywords):
            col_idx = idx % 4
            display_label = f"{kw} ({count:,})" if count > 0 else kw
            is_checked = cols[col_idx].checkbox(
                display_label, value=True, key=f"tg_kw_{idx}"
            )
            if is_checked:
                selected_kw_list.append(kw)

        valid_keywords = selected_kw_list

    if st.button(
        "🚀 100byte 최적화 상품명 생성하기", type="primary", key="tg_generate_btn"
    ):
        if not gemini_api_key:
            st.error("⚠️ GEMINI_API_KEY가 등록되지 않았습니다. Streamlit Secrets 설정을 확인해주세요.")
        elif not product_type:
            st.warning("⚠️ '상품 종류/기본명'을 입력해주세요.")
        elif not valid_keywords:
            st.warning(
                "⚠️ 선택된 키워드가 없습니다. 네이버 키워드를 입력하고 체크해주세요."
            )
        else:
            with st.spinner("AI가 상품명을 생성 중입니다..."):
                genai.configure(api_key=gemini_api_key)

                prompt = f"""
너는 한국 이커머스(네이버 스마트스토어, 쿠팡 등) SEO 전문가야.
직원이 선별한 '실제 검색량이 높은 키워드 순서'를 최우선으로 반영하여 최적의 상품명을 만들어줘.

[상품 정보]
- 브랜드명: {brand_name}
- 기본 상품명: {product_type}
- 주요 특징/소재: {product_features}
- 타겟/용도: {product_target}

[휴먼터치 거친 실제 검색량 높은 순 키워드 (우선순위 순서대로 배치할 것)]
{', '.join(valid_keywords)}

[요청 및 제약 사항]
1. 가장 첫머리에는 반드시 브랜드명 [{brand_name}]을 배치해줘.
2. 상단 제공된 키워드 중 검색량이 높은 순서대로 차례대로 조합하여 상품명을 작성해줘.
3. 네이버 상품명 제한인 **100Byte 이내(한글 기준 약 30~40자 내외)**로 타이트하고 매끄럽게 작성해줘.
4. '최저가', '1+1', '특가', '무료배송' 등 수식어나 금지어는 절대 제외할 것.
5. 저작권 및 상표권 문제가 없는 안전한 단어만 활용할 것.
6. 서로 다른 느낌의 추천 상품명 3가지를 제안하고, 각 상품명 뒤에 (OO byte) 형태로 바이트 수를 표기해줘.
7. 가장 아래에는 활용된 키워드 20개를 검색량 높은 순서대로 쉼표(,)로 구분하여 한 줄로 적어줘.
"""

                @st.cache_data(ttl=3600)
                def get_available_flash_models(_has_key):
                    """generateContent를 지원하는 모델을 실제로 조회 (하드코딩 대신)."""
                    try:
                        all_models = list(genai.list_models())
                    except Exception:
                        return []

                    supported = [
                        m.name
                        for m in all_models
                        if "generateContent"
                        in getattr(m, "supported_generation_methods", [])
                    ]

                    # flash 계열(저비용/무료 티어)을 우선순위로 정렬
                    return sorted(
                        supported,
                        key=lambda name: (0 if "flash" in name.lower() else 1, name),
                    )

                candidate_models = get_available_flash_models(bool(gemini_api_key))

                response_text = None
                last_error = None

                if not candidate_models:
                    last_error = (
                        "사용 가능한 Gemini 모델을 조회하지 못했습니다. "
                        "API 키 권한 또는 프로젝트 설정을 확인해주세요."
                    )
                else:
                    for model_name in candidate_models:
                        try:
                            model = genai.GenerativeModel(model_name)
                            res = model.generate_content(prompt)
                            if res and res.text:
                                response_text = res.text
                                break
                        except Exception as err:
                            last_error = f"[{model_name}] {err}"
                            continue

                if response_text:
                    st.success("✅ SEO 상품명 생성 완료!")
                    st.markdown(response_text)
                else:
                    st.error(f"AI 생성 중 오류가 발생했습니다: {str(last_error)}")
                    if candidate_models:
                        with st.expander("조회된 사용 가능 모델 목록 보기"):
                            st.write(candidate_models)
