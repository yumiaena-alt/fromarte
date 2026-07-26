import base64
import hashlib
import hmac
import io
import math
import os
import re
import time
import urllib.request

import bcrypt
import google.generativeai as genai
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(
    page_title="프롬아떼 스마트 커머스 툴",
    page_icon="🛍️",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1100px;
        margin: 0 auto;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🛍️ 프롬아떼 스마트 커머스 툴")
st.write("원하시는 기능을 상단 탭에서 선택하여 사용하세요.")

# ------------------------------------------------------------------
# 공통 데이터 로드 및 API 연동 함수
# ------------------------------------------------------------------


def _get_naver_commerce_token():
    """네이버 커머스 API OAuth2 access token 발급 (실패 사유를 함께 반환)."""
    client_id = st.secrets.get("NAVER_CLIENT_ID") or os.environ.get(
        "NAVER_CLIENT_ID"
    )
    client_secret = st.secrets.get("NAVER_CLIENT_SECRET") or os.environ.get(
        "NAVER_CLIENT_SECRET"
    )

    if not client_id or not client_secret:
        return None, "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET가 등록되지 않았습니다."

    try:
        # 네이버 커머스 API는 client_secret을 bcrypt salt로 사용해
        # "client_id_timestamp" 문자열을 해시한 서명을 요구한다.
        timestamp = str(int(time.time() * 1000))
        password = f"{client_id}_{timestamp}"
        hashed = bcrypt.hashpw(
            password.encode("utf-8"), client_secret.encode("utf-8")
        )
        client_secret_sign = base64.b64encode(hashed).decode("utf-8")

        token_url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        token_data = {
            "client_id": client_id,
            "timestamp": timestamp,
            "client_secret_sign": client_secret_sign,
            "grant_type": "client_credentials",
            "type": "SELF",
        }
        token_res = requests.post(token_url, data=token_data, timeout=10)
        access_token = token_res.json().get("access_token")
        if not access_token:
            return None, f"토큰 발급 실패: {token_res.text}"
        return access_token, None
    except Exception as e:
        return None, f"네이버 커머스 API 토큰 발급 실패: {e}"


@st.cache_data(ttl=60)
def fetch_naver_api_price(smartstore_url):
    if not smartstore_url or "smartstore.naver.com" not in smartstore_url:
        return None

    match = re.search(r"products/(\d+)", smartstore_url)
    if not match:
        return None

    product_id = match.group(1)

    access_token, err = _get_naver_commerce_token()
    if err:
        return None

    try:
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


def _parse_text_align(raw_html):
    # 사용자 요청에 따라 원본 정렬과 상관없이 항상 중앙정렬로 렌더링한다.
    return "center"


def _parse_text_color(raw_html):
    m = re.search(r"color:\s*rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", raw_html)
    if m:
        return tuple(int(x) for x in m.groups())
    m = re.search(r"color:\s*#([0-9a-fA-F]{6})\b", raw_html)
    if m:
        h = m.group(1)
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    m = re.search(r"color:\s*#([0-9a-fA-F]{3})\b", raw_html)
    if m:
        h = m.group(1)
        return tuple(int(c * 2, 16) for c in h)
    return (51, 51, 51)


def _parse_detail_content_segments(html):
    """detailContent HTML을 순서대로 순회하여 텍스트/이미지행 세그먼트로 변환.
    각 세그먼트는 ("text", 문자열, 폰트크기, 정렬, 색상) 또는
    ("images", [url, ...]) 형태이며, 같은 블록 안에 나란히 있던 이미지들은
    하나의 "행"으로 묶어 반환한다 (개별 확대로 인한 화질 저하를 막기 위해
    나중에 행 단위로 리사이즈한다)."""
    soup = BeautifulSoup(html or "", "html.parser")
    segments = []

    def handle_block(node):
        pending_text = []
        pending_imgs = []

        def flush_text():
            nonlocal pending_text
            if pending_text:
                joined = "\n".join(t for t, _ in pending_text if t.strip())
                raw_all = " ".join(h for _, h in pending_text)
                sizes = [
                    int(s) for s in re.findall(r"font-size:\s*(\d+)px", raw_all)
                ]
                # 원본 대비 다소 작게 렌더링 (0.8배 축소, 13~34px로 제한)
                font_size = (
                    max(min(int(max(sizes) * 0.8), 34), 13) if sizes else 20
                )
                align = _parse_text_align(raw_all)
                color = _parse_text_color(raw_all)
                if joined.strip():
                    segments.append(
                        ("text", joined.strip(), font_size, align, color)
                    )
            pending_text = []

        def flush_imgs():
            nonlocal pending_imgs
            if pending_imgs:
                segments.append(("images", pending_imgs))
            pending_imgs = []

        for child in node.children:
            name = getattr(child, "name", None)
            if name == "img":
                flush_text()
                src = child.get("src", "")
                if src:
                    pending_imgs.append(src)
                continue
            if name is not None:
                if child.find("img"):
                    flush_text()
                    flush_imgs()
                    handle_block(child)
                else:
                    text = child.get_text(separator=" ", strip=True)
                    if text:
                        flush_imgs()
                        pending_text.append((text, str(child)))
            else:
                text = str(child).strip()
                if text:
                    flush_imgs()
                    pending_text.append((text, text))

        flush_text()
        flush_imgs()

    handle_block(soup)
    return segments


def fetch_naver_product_detail_segments(smartstore_url):
    """네이버 커머스 API로 상품 상세페이지의 텍스트/이미지 순서를 그대로 가져온다."""
    if not smartstore_url or "smartstore.naver.com" not in smartstore_url:
        return None, "스마트스토어 상품 URL이 아닙니다."

    match = re.search(r"products/(\d+)", smartstore_url)
    if not match:
        return None, "URL에서 상품 번호를 찾지 못했습니다."
    product_id = match.group(1)

    access_token, err = _get_naver_commerce_token()
    if err:
        return None, err

    try:
        api_url = f"https://api.commerce.naver.com/external/v2/products/channel-products/{product_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        res = requests.get(api_url, headers=headers, timeout=15)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        return None, f"상품 정보 조회 실패: {e}"

    origin_product = data.get("originProduct", {}) or {}
    detail_content = (
        origin_product.get("detailContent") or data.get("detailContent") or ""
    )

    segments = _parse_detail_content_segments(detail_content)
    if not segments:
        return None, (
            "상세페이지 내용을 응답에서 찾지 못했습니다 "
            "(detailContent가 비어있거나 형식이 다를 수 있습니다)."
        )

    return segments, None


_KOREAN_FONT_CANDIDATES = [
    "fonts/NanumGothic.ttf",
    "title_generator/fonts/NanumGothic.ttf",
    "price_calculator/fonts/NanumGothic.ttf",
]


def _get_korean_font(size):
    for path in _KOREAN_FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap_text_lines(draw, text, font, max_width, max_chars=15):
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split(" ")
        current = ""
        para_lines = []
        for word in words:
            candidate = (current + " " + word).strip()
            fits = (
                draw.textlength(candidate, font=font) <= max_width
                and len(candidate) <= max_chars
            )
            if not current or fits:
                current = candidate
            else:
                para_lines.append(current)
                current = word
            while draw.textlength(current, font=font) > max_width and len(current) > 1:
                lo, hi = 1, len(current)
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if draw.textlength(current[:mid], font=font) <= max_width:
                        lo = mid
                    else:
                        hi = mid - 1
                para_lines.append(current[:lo])
                current = current[lo:]
        if current:
            para_lines.append(current)

        # 한 문단이 3줄 이상으로 나뉘면 3줄마다 빈 줄을 넣어 숨 쉴 틈을 준다.
        if len(para_lines) >= 3:
            spaced = []
            for i, line in enumerate(para_lines):
                spaced.append(line)
                if (i + 1) % 3 == 0 and i != len(para_lines) - 1:
                    spaced.append("")
            para_lines = spaced

        lines.extend(para_lines)
    return lines


def render_text_segment(text, width, font_size=26, align="center", color=(51, 51, 51)):
    """텍스트를 상세페이지 폭에 맞춰 이미지로 렌더링 (원래 위치/정렬/색상을 반영)."""
    # 문장이 이어져서 너무 길어지지 않도록 마침표 뒤는 줄바꿈하되,
    # "8.5cm" 같은 소수점 숫자는 그대로 둔다 (앞뒤가 숫자면 건너뜀).
    text = re.sub(r"(?<!\d)\.(?!\d)\s*", ".\n", text).strip()

    font = _get_korean_font(font_size)
    tmp_draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    padding_x = 24
    max_width = width - padding_x * 2
    lines = _wrap_text_lines(tmp_draw, text, font, max_width)

    ascent, descent = font.getmetrics()
    line_height = ascent + descent + 8
    total_height = max(line_height * max(len(lines), 1) + 16, 32)

    img = Image.new("RGB", (width, total_height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 8
    for line in lines:
        line_w = draw.textlength(line, font=font) if line else 0
        if align == "center":
            x = padding_x + max(0, (max_width - line_w) / 2)
        elif align == "right":
            x = width - padding_x - line_w
        else:
            x = padding_x
        draw.text((x, y), line, font=font, fill=color)
        y += line_height
    return img


def open_image_flatten_white(data):
    """PNG 등 투명 배경 이미지를 검은 배경으로 깨지지 않도록 흰 배경에 합성해서 연다."""
    img = Image.open(data)
    if img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    ):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def combine_image_row(images):
    """가로로 나란히 있던 이미지들을 개별 확대 없이 원본 비율 그대로 한 장으로 합친다."""
    if len(images) == 1:
        return images[0]

    max_h = max(img.height for img in images)
    resized = []
    for img in images:
        if img.height != max_h:
            new_w = max(1, int(img.width * (max_h / img.height)))
            img = img.resize((new_w, max_h), Image.Resampling.LANCZOS)
        resized.append(img)

    total_w = sum(img.width for img in resized)
    row_img = Image.new("RGB", (total_w, max_h), (255, 255, 255))
    x = 0
    for img in resized:
        row_img.paste(img, (x, 0))
        x += img.width
    return row_img


def _naver_ad_signature(secret_key, timestamp, method, uri):
    message = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(
        secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _to_search_count(value):
    """'< 10' 같은 네이버 응답 형식도 처리해서 정수로 변환."""
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else 0


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@st.cache_data(ttl=600)
def fetch_naver_related_keywords(seed_keyword):
    """네이버 검색광고 Open API로 연관키워드 + 월간검색수를 조회."""
    api_key = st.secrets.get("NAVER_AD_API_KEY") or os.environ.get(
        "NAVER_AD_API_KEY"
    )
    secret_key = st.secrets.get("NAVER_AD_SECRET_KEY") or os.environ.get(
        "NAVER_AD_SECRET_KEY"
    )
    customer_id = (
        st.secrets.get("NAVER_AD_CUSTOMER_ID")
        or os.environ.get("NAVER_AD_CUSTOMER_ID")
        or "4454771"
    )

    if not api_key or not secret_key:
        return None, (
            "NAVER_AD_API_KEY / NAVER_AD_SECRET_KEY가 등록되지 않았습니다. "
            "Streamlit Secrets 설정을 확인해주세요."
        )

    # 네이버 hintKeywords는 띄어쓰기/특수문자가 있으면 무효 처리되므로 제거
    clean_keyword = re.sub(r"[^0-9A-Za-z가-힣]", "", seed_keyword)
    if not clean_keyword:
        return None, "키워드에 한글/영문/숫자 외의 문자만 있어 조회할 수 없습니다."

    uri = "/keywordstool"
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    signature = _naver_ad_signature(secret_key, timestamp, method, uri)

    headers = {
        "X-Timestamp": timestamp,
        "X-API-KEY": api_key,
        "X-Customer": str(customer_id),
        "X-Signature": signature,
    }
    params = {"hintKeywords": clean_keyword, "showDetail": "1"}

    try:
        res = requests.get(
            "https://api.searchad.naver.com" + uri,
            headers=headers,
            params=params,
            timeout=10,
        )
    except Exception as e:
        return None, f"네이버 키워드 API 요청 자체가 실패했습니다: {e}"

    if res.status_code != 200:
        try:
            detail = res.json()
        except Exception:
            detail = res.text
        return None, (
            f"네이버 키워드 API 호출 실패 (HTTP {res.status_code}): {detail} "
            f"(Customer ID: {customer_id})"
        )

    data = res.json()

    results = []
    for item in data.get("keywordList", []):
        kw = str(item.get("relKeyword", "")).strip()
        if not kw:
            continue
        results.append(
            {
                "키워드": kw,
                "PC 검색수": _to_search_count(item.get("monthlyPcQcCnt", 0)),
                "모바일 검색수": _to_search_count(
                    item.get("monthlyMobileQcCnt", 0)
                ),
                "PC 클릭수": _to_float(item.get("monthlyAvePcClkCnt", 0)),
                "모바일 클릭수": _to_float(
                    item.get("monthlyAveMobileClkCnt", 0)
                ),
                "PC 클릭률(%)": _to_float(item.get("monthlyAvePcCtr", 0)),
                "모바일 클릭률(%)": _to_float(
                    item.get("monthlyAveMobileCtr", 0)
                ),
                "경쟁정도": str(item.get("compIdx", "")),
                "노출 광고수": _to_search_count(item.get("plAvgDepth", 0)),
            }
        )

    # 모바일 검색수 많은 순 정렬 (사용자가 기존에 수기로 하던 정렬 기준과 동일)
    results.sort(key=lambda r: r["모바일 검색수"], reverse=True)
    return results, None


def render_keyword_selection_table(kw_results, page_size=10):
    """네이버 키워드 도구 화면처럼 표 + 페이지네이션으로 키워드를 선택하게 하고,
    선택된 키워드 리스트를 반환한다."""
    if "tg_kw_selected" not in st.session_state:
        st.session_state["tg_kw_selected"] = {}
    selected_map = st.session_state["tg_kw_selected"]

    if "tg_kw_editor_version" not in st.session_state:
        st.session_state["tg_kw_editor_version"] = 0

    total = len(kw_results)
    total_pages = max(1, math.ceil(total / page_size))
    page = min(max(st.session_state.get("tg_kw_page", 1), 1), total_pages)
    st.session_state["tg_kw_page"] = page

    start = (page - 1) * page_size
    page_rows = kw_results[start : start + page_size]

    table_rows = [
        {
            "추가": selected_map.get(row["키워드"], False),
            "연관키워드": row["키워드"],
            "PC 검색수": row["PC 검색수"],
            "모바일 검색수": row["모바일 검색수"],
            "PC 클릭수": row["PC 클릭수"],
            "모바일 클릭수": row["모바일 클릭수"],
            "PC 클릭률(%)": row["PC 클릭률(%)"],
            "모바일 클릭률(%)": row["모바일 클릭률(%)"],
            "경쟁정도": row["경쟁정도"],
            "노출 광고수": row["노출 광고수"],
        }
        for row in page_rows
    ]
    df = pd.DataFrame(table_rows)

    edited = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        disabled=[c for c in df.columns if c != "추가"],
        column_config={
            "추가": st.column_config.CheckboxColumn("추가", width="small"),
            "연관키워드": st.column_config.TextColumn(width="large"),
            "PC 검색수": st.column_config.NumberColumn(format="%d", width="small"),
            "모바일 검색수": st.column_config.NumberColumn(
                format="%d", width="small"
            ),
            "PC 클릭수": st.column_config.NumberColumn(
                format="%.1f", width="small"
            ),
            "모바일 클릭수": st.column_config.NumberColumn(
                format="%.1f", width="small"
            ),
            "PC 클릭률(%)": st.column_config.NumberColumn(
                format="%.2f", width="small"
            ),
            "모바일 클릭률(%)": st.column_config.NumberColumn(
                format="%.2f", width="small"
            ),
            "경쟁정도": st.column_config.TextColumn(width="small"),
            "노출 광고수": st.column_config.NumberColumn(
                format="%d", width="small"
            ),
        },
        key=f"tg_kw_editor_{page}_{st.session_state['tg_kw_editor_version']}",
    )

    for _, r in edited.iterrows():
        selected_map[r["연관키워드"]] = bool(r["추가"])

    nav1, nav2, nav3 = st.columns([1, 2, 1])
    with nav1:
        if st.button("◀ 이전", disabled=(page <= 1), key="tg_kw_prev"):
            st.session_state["tg_kw_page"] = page - 1
            st.rerun()
    with nav2:
        st.markdown(
            f"<div style='text-align:center'>{page} / {total_pages} 페이지 "
            f"(총 {total}개)</div>",
            unsafe_allow_html=True,
        )
    with nav3:
        if st.button(
            "다음 ▶", disabled=(page >= total_pages), key="tg_kw_next"
        ):
            st.session_state["tg_kw_page"] = page + 1
            st.rerun()

    selected_keywords = [kw for kw, checked in selected_map.items() if checked]
    st.caption(f"✅ 선택된 키워드: {len(selected_keywords)}개")

    if selected_keywords:
        chip_cols = st.columns(6)
        for idx, kw in enumerate(selected_keywords):
            if chip_cols[idx % 6].button(
                f"❌ {kw}", key=f"tg_kw_remove_{kw}", use_container_width=True
            ):
                selected_map[kw] = False
                st.session_state["tg_kw_editor_version"] += 1
                st.rerun()

    return selected_keywords


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
# 상단 탭 분리 (1. Title Generator / 2. 마켓별 판매가 계산기 / 3. 상세페이지 합치기)
# ------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(
    ["🏷️ 상품명 작성기", "💰 마켓별 판매가 계산기", "🖼️ 상세페이지 합치기"]
)

# ==================================================================
# TAB 1: Title Generator
# ==================================================================
with tab1:
    gemini_api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get(
        "GEMINI_API_KEY"
    )

    st.subheader("🏷️ SEO 키워드 기반 최적화 상품명 생성기")
    st.caption(
        "네이버 광고주 센터 데이터를 기반으로 100byte SEO 상품명을 자동 조합합니다."
    )

    product_type = st.text_input(
        "상품 종류/기본명",
        placeholder="예: 차량용 무선 선풍기",
        key="tg_product_type",
    )

    # 상품 종류가 바뀌면 핵심 키워드 입력창에 자동 반영 (이후 직접 수정 가능)
    if st.session_state.get("_tg_last_product_type") != product_type:
        st.session_state["_tg_last_product_type"] = product_type
        st.session_state["tg_seed_keyword"] = product_type

    product_features = st.text_input(
        "주요 특징/소재",
        placeholder="예: USB 충전, 무소음, 3단계 풍속조절",
        key="tg_product_features",
    )
    product_target = st.text_input(
        "타겟/용도", placeholder="예: 캠핑, 차량용", key="tg_product_target"
    )
    brand_name = st.text_input(
        "브랜드명", value="프롬아떼", key="tg_brand_name"
    )

    st.markdown("#### 📥 연관 키워드 가져오기")
    kw_input_method = st.radio(
        "키워드 입력 방식",
        ["🔍 네이버 API로 자동 조회 (추천)", "✍️ 직접 붙여넣기"],
        horizontal=True,
        key="tg_kw_input_method",
    )

    valid_keywords = []

    if kw_input_method == "🔍 네이버 API로 자동 조회 (추천)":
        seed_col1, seed_col2 = st.columns([3, 1])
        with seed_col1:
            seed_keyword = st.text_input(
                "핵심 키워드를 입력하고 조회 버튼을 누르세요",
                placeholder="예: 자전거바구니",
                key="tg_seed_keyword",
            )
        with seed_col2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            search_clicked = st.button(
                "🔍 조회", key="tg_kw_search_btn", use_container_width=True
            )

        if search_clicked:
            if not seed_keyword.strip():
                st.warning("⚠️ 조회할 키워드를 입력해주세요.")
            else:
                with st.spinner("네이버에서 연관 키워드를 조회 중입니다..."):
                    results, err = fetch_naver_related_keywords(seed_keyword.strip())
                if err:
                    st.error(f"⚠️ {err}")
                    st.session_state["tg_kw_results"] = None
                else:
                    st.session_state["tg_kw_results"] = results
                    st.session_state["tg_kw_seed"] = seed_keyword.strip()
                    st.session_state["tg_kw_page"] = 1
                    st.session_state["tg_kw_selected"] = {}

        kw_results = st.session_state.get("tg_kw_results")
        if kw_results:
            st.caption(
                f"'{st.session_state.get('tg_kw_seed', '')}' 연관 키워드 "
                f"{len(kw_results)}개 (모바일 검색량 많은 순 정렬)"
            )
            valid_keywords = render_keyword_selection_table(kw_results)
    else:
        raw_keywords_text = st.text_area(
            "네이버 광고주 센터에서 추출한 키워드 및 검색량 목록을 붙여넣으세요:",
            placeholder="예시 (키워드 / 월간검색량 순으로 붙여넣기):\n무선선풍기 15000\n차량용선풍기 8200\nUSB선풍기 3100\n미니선풍기 1200",
            height=120,
            key="tg_raw_keywords",
        )

        parsed_keywords = []
        if raw_keywords_text.strip():
            lines = raw_keywords_text.strip().split("\n")
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

        if parsed_keywords:
            parsed_keywords.sort(key=lambda x: x[1], reverse=True)

            st.markdown("#### 🖐️ [휴먼 터치] 필요한 키워드만 체크해서 추가")
            st.caption(
                "실제 검색량이 높은 순서대로 정렬되었습니다. **내 상품과 맞는 키워드만 체크**하세요!"
            )

            cols = st.columns(4)
            selected_kw_list = []

            for idx, (kw, count) in enumerate(parsed_keywords):
                col_idx = idx % 4
                display_label = f"{kw} ({count:,})" if count > 0 else kw
                is_checked = cols[col_idx].checkbox(
                    display_label, value=False, key=f"tg_kw_{idx}"
                )
                if is_checked:
                    selected_kw_list.append(kw)

            st.caption(f"✅ 선택된 키워드: {len(selected_kw_list)}개")

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
아래 규칙을 예외 없이 그대로 따르고, 지정된 출력 형식 외의 인사말·소개·부연설명·대화체 문장은 절대 출력하지 마.

[상품 정보 - 참고용]
- 브랜드명: {brand_name}
- 기본 상품명: {product_type}
- 주요 특징/소재: {product_features}
- 타겟/용도(참고용, 아래 금지어 규칙이 이 값보다 항상 우선함): {product_target}

[휴먼터치 거친 실제 검색량 높은 순 키워드 (우선순위 순서대로 배치할 것)]
{', '.join(valid_keywords)}

[절대 금지어 - KC 어린이제품 안전인증 이슈로 상품명에 절대 포함 금지]
"아기", "유아", "영유아", "신생아", "어린이"
- 위 단어들은 브랜드명/특징/타겟 입력값에 있더라도 최종 상품명 문구에 절대 그대로 쓰지 마.
- 타겟 표현이 꼭 필요하면 "키즈", "주니어" 등 안전한 단어로 바꾸거나, 아예 생략해.

[바이트 규칙 - 매우 중요]
- 한글 1자 = 2Byte, 영문/숫자/기호 1자 = 1Byte 기준으로 계산.
- 각 상품명은 90~100Byte 사이가 되도록 100Byte에 최대한 가깝게 길게 작성해.
- 50~70Byte처럼 짧게 끝내지 말고, 남은 키워드나 소재/특징 수식어를 더 붙여서 100Byte에 최대한 채워.

[기타 제약]
1. 가장 첫머리에는 반드시 브랜드명 {brand_name}을(를) 대괄호나 특수문자로 감싸지 말고 텍스트 그대로 배치할 것 (예: [{brand_name}]이 아니라 {brand_name}).
2. 키워드는 검색량 높은 순서대로 배치할 것.
3. '최저가', '1+1', '특가', '무료배송' 등 수식어나 금지어는 절대 제외할 것.
4. 저작권 및 상표권 문제가 없는 안전한 단어만 활용할 것.
5. 서로 다른 느낌의 상품명 3가지를 만들 것.

[출력 형식 - 반드시 이 4줄 형식으로만 출력. 다른 문장은 절대 추가하지 마]
TITLE1: <상품명1>
TITLE2: <상품명2>
TITLE3: <상품명3>
KEYWORDS: <활용 키워드 20개를 검색량 높은 순으로 쉼표(,)로 구분>
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

                def kr_byte_len(text):
                    """네이버 상품명 바이트 규칙(한글 2Byte) 기준 실제 바이트 수 계산."""
                    try:
                        return len(text.encode("cp949"))
                    except UnicodeEncodeError:
                        return len(text.encode("utf-8"))

                def parse_ai_output(text):
                    titles = []
                    keywords_line = ""
                    for line in text.splitlines():
                        line = line.strip()
                        m = re.match(r"TITLE\s*\d*\s*[:：]\s*(.+)", line, re.IGNORECASE)
                        if m:
                            titles.append(m.group(1).strip())
                            continue
                        m2 = re.match(r"KEYWORDS\s*[:：]\s*(.+)", line, re.IGNORECASE)
                        if m2:
                            keywords_line = m2.group(1).strip()
                    return titles, keywords_line

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
                    titles, keywords_line = parse_ai_output(response_text)

                    if titles:
                        st.success("✅ SEO 상품명 생성 완료! 아래 코드 박스 오른쪽 복사 아이콘을 눌러 바로 복사하세요.")
                        for title in titles:
                            byte_len = kr_byte_len(title)
                            st.code(title, language=None)
                            if byte_len > 100:
                                st.caption(f"⚠️ 실측 {byte_len}Byte (100Byte 초과 — 줄여야 함)")
                            else:
                                st.caption(f"실측 {byte_len}Byte")

                        if keywords_line:
                            st.markdown("**활용 키워드 20개**")
                            st.code(keywords_line, language=None)
                    else:
                        st.warning("⚠️ AI 응답 형식이 예상과 달라 원문 그대로 표시합니다.")
                        st.code(response_text, language=None)
                else:
                    st.error(f"AI 생성 중 오류가 발생했습니다: {str(last_error)}")
                    if candidate_models:
                        with st.expander("조회된 사용 가능 모델 목록 보기"):
                            st.write(candidate_models)

# ==================================================================
# TAB 2: 마켓별 판매가 계산기
# ==================================================================
with tab2:
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
# TAB 3: 상세페이지 + 하단 배너 자동 병합기
# ==================================================================
with tab3:
    st.subheader("🖼️ 상세페이지 + 하단 배너 자동 병합기")
    st.caption(
        "상세페이지 이미지를 업로드하거나 스마트스토어 상품 링크로 바로 가져와서 "
        "주문제작/AI 안내 하단 배너를 자동으로 합쳐줍니다."
    )

    top_download_slot = st.container()
    st.markdown("---")

    @st.cache_data(ttl=300)
    def get_outbound_ip():
        try:
            res = requests.get("https://api.ipify.org", timeout=5)
            return res.text.strip()
        except Exception:
            return None

    _outbound_ip = get_outbound_ip()
    if _outbound_ip:
        st.info(
            f"🔧 현재 서버 외부 IP: `{_outbound_ip}` — 네이버 커머스 API "
            "애플리케이션의 'API호출 IP' 설정에 이 값을 등록하세요. "
            "(Streamlit Cloud 서버 IP는 재배포/재시작 시 바뀔 수 있습니다)"
        )

    DETAIL_FOOTER_URL = "https://gi.esmplus.com/fromarte/wholesale/order.png"

    @st.cache_data(ttl=3600)
    def load_footer_image(url):
        """호스팅된 하단 배너 이미지를 불러와 캐싱합니다."""
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req) as response:
                footer_data = response.read()
            return open_image_flatten_white(io.BytesIO(footer_data))
        except Exception as e:
            st.error(f"하단 배너 이미지를 불러오는 데 실패했습니다: {e}")
            return None

    detail_input_method = st.radio(
        "상세페이지 가져오는 방식",
        ["📤 이미지 업로드", "🔗 스마트스토어 링크로 가져오기"],
        horizontal=True,
        key="detail_input_method",
    )

    main_img = None
    source_name = "detail_page"

    if detail_input_method == "📤 이미지 업로드":
        detail_uploaded_file = st.file_uploader(
            "상세페이지 캡처 이미지를 선택하세요 (JPG, PNG)",
            type=["jpg", "jpeg", "png"],
            key="detail_uploader",
        )
        if detail_uploaded_file is not None:
            main_img = open_image_flatten_white(detail_uploaded_file)
            source_name = detail_uploaded_file.name.rsplit(".", 1)[0]
    else:
        detail_target_width = st.number_input(
            "상세페이지 폭 (px) — 국내 오픈마켓 표준 폭에 맞춰 리사이즈됩니다",
            min_value=300,
            max_value=2000,
            value=860,
            step=10,
            key="detail_target_width",
            help="지마켓/옥션/쿠팡 등 국내 오픈마켓이 요구하는 상세페이지 표준 폭 "
            "(보통 860px)에 맞춰 자동으로 리사이즈합니다. 필요시 값을 바꾸세요.",
        )
        smartstore_link = st.text_input(
            "스마트스토어 상품 URL",
            placeholder="https://smartstore.naver.com/.../products/...",
            key="detail_smartstore_url",
        )
        fetch_clicked = st.button("📥 상세페이지 가져오기", key="detail_fetch_btn")

        if fetch_clicked:
            if not smartstore_link.strip():
                st.warning("⚠️ 스마트스토어 상품 URL을 입력해주세요.")
            else:
                with st.spinner("상세페이지 내용을 조회하는 중입니다..."):
                    segments, err = fetch_naver_product_detail_segments(
                        smartstore_link.strip()
                    )

                if err:
                    st.error(f"⚠️ {err}")
                    st.session_state["detail_link_main_img"] = None
                else:
                    built_blocks = []
                    failed_count = 0
                    text_count = sum(1 for s in segments if s[0] == "text")
                    img_count = sum(
                        len(s[1]) for s in segments if s[0] == "images"
                    )

                    with st.spinner(
                        f"텍스트 {text_count}개 / 이미지 {img_count}개를 "
                        "원래 순서대로 조합하는 중입니다..."
                    ):
                        for seg in segments:
                            if seg[0] == "text":
                                _, text, font_size, align, color = seg
                                built_blocks.append(
                                    render_text_segment(
                                        text,
                                        detail_target_width,
                                        font_size,
                                        align,
                                        color,
                                    )
                                )
                                continue

                            _, urls = seg
                            row_images = []
                            for img_url in urls:
                                try:
                                    img_res = requests.get(
                                        img_url,
                                        headers={
                                            "User-Agent": "Mozilla/5.0",
                                            "Referer": "https://smartstore.naver.com/",
                                        },
                                        timeout=15,
                                    )
                                    img_res.raise_for_status()
                                    row_images.append(
                                        open_image_flatten_white(
                                            io.BytesIO(img_res.content)
                                        )
                                    )
                                except Exception:
                                    failed_count += 1

                            if not row_images:
                                continue

                            # 가로로 나란히 있던 이미지들을 먼저 원본 비율 그대로
                            # 한 장으로 합친 뒤, 그 행 전체를 하나의 단위로만
                            # 리사이즈한다 (이미지 각각을 늘리면 화질이 깨짐).
                            row_img = combine_image_row(row_images)
                            row_w, row_h = row_img.size
                            new_h = int(row_h * (detail_target_width / row_w))
                            row_img = row_img.resize(
                                (detail_target_width, new_h),
                                Image.Resampling.LANCZOS,
                            )
                            built_blocks.append(row_img)

                    if not built_blocks:
                        st.error("⚠️ 상세페이지 내용을 하나도 가져오지 못했습니다.")
                        st.session_state["detail_active_blocks"] = None
                        st.session_state["detail_link_main_img"] = None
                    else:
                        st.session_state["detail_active_blocks"] = [
                            {"image": b, "parts": None} for b in built_blocks
                        ]
                        if failed_count:
                            st.warning(
                                f"⚠️ 이미지 {failed_count}개는 다운로드에 실패해 "
                                "제외했습니다."
                            )
                        st.success(
                            f"✅ 텍스트/이미지 {len(built_blocks)}개 블록을 "
                            f"{detail_target_width}px 폭으로 가져왔습니다. "
                            "아래에서 순서 변경/가로 합치기/삭제가 가능합니다."
                        )

        active_blocks = st.session_state.get("detail_active_blocks")
        if active_blocks:
            st.markdown(
                "#### 🖼️ 미리보기 — 위/아래로 순서를 바꾸거나, 다음 블록과 "
                "가로로 합치거나(옆에 배치하면 두 이미지가 작아지며 나란히 "
                "정렬됩니다), 합친 블록은 다시 분리하거나, 삭제할 수 있습니다"
            )

            for idx, entry in enumerate(active_blocks):
                with st.container(border=True):
                    st.image(entry["image"], use_container_width=True)
                    btn_cols = st.columns(5)
                    if btn_cols[0].button(
                        "⬆️ 위로",
                        key=f"detail_up_{idx}",
                        disabled=(idx == 0),
                        use_container_width=True,
                    ):
                        active_blocks[idx - 1], active_blocks[idx] = (
                            active_blocks[idx],
                            active_blocks[idx - 1],
                        )
                        st.session_state["detail_active_blocks"] = active_blocks
                        st.rerun()
                    if btn_cols[1].button(
                        "⬇️ 아래로",
                        key=f"detail_down_{idx}",
                        disabled=(idx == len(active_blocks) - 1),
                        use_container_width=True,
                    ):
                        active_blocks[idx + 1], active_blocks[idx] = (
                            active_blocks[idx],
                            active_blocks[idx + 1],
                        )
                        st.session_state["detail_active_blocks"] = active_blocks
                        st.rerun()
                    if btn_cols[2].button(
                        "➡️ 다음과 가로로 합치기",
                        key=f"detail_merge_{idx}",
                        disabled=(idx == len(active_blocks) - 1),
                        use_container_width=True,
                    ):
                        next_entry = active_blocks[idx + 1]
                        merged_row = combine_image_row(
                            [entry["image"], next_entry["image"]]
                        )
                        row_w, row_h = merged_row.size
                        new_h = int(row_h * (detail_target_width / row_w))
                        merged_row = merged_row.resize(
                            (detail_target_width, new_h),
                            Image.Resampling.LANCZOS,
                        )
                        active_blocks[idx : idx + 2] = [
                            {
                                "image": merged_row,
                                "parts": [entry, next_entry],
                            }
                        ]
                        st.session_state["detail_active_blocks"] = active_blocks
                        st.rerun()
                    if btn_cols[3].button(
                        "↩️ 분리하기",
                        key=f"detail_split_{idx}",
                        disabled=not entry["parts"],
                        use_container_width=True,
                    ) and entry["parts"]:
                        active_blocks[idx : idx + 1] = entry["parts"]
                        st.session_state["detail_active_blocks"] = active_blocks
                        st.rerun()
                    if btn_cols[4].button(
                        "🗑️ 삭제",
                        key=f"detail_del_{idx}",
                        use_container_width=True,
                    ):
                        active_blocks.pop(idx)
                        st.session_state["detail_active_blocks"] = active_blocks
                        st.rerun()

            if active_blocks:
                block_gap = 20
                total_h = sum(
                    e["image"].height for e in active_blocks
                ) + block_gap * (len(active_blocks) - 1)
                stacked = Image.new(
                    "RGB", (detail_target_width, total_h), (255, 255, 255)
                )
                y = 0
                for i, e in enumerate(active_blocks):
                    stacked.paste(e["image"], (0, y))
                    y += e["image"].height
                    if i < len(active_blocks) - 1:
                        y += block_gap
                st.session_state["detail_link_main_img"] = stacked
            else:
                st.session_state["detail_link_main_img"] = None

        stored_img = st.session_state.get("detail_link_main_img")
        if stored_img is not None:
            main_img = stored_img
            id_match = re.search(r"products/(\d+)", smartstore_link or "")
            source_name = f"product_{id_match.group(1)}" if id_match else "detail_page"

    if main_img is not None:
        footer_img = load_footer_image(DETAIL_FOOTER_URL)

        if footer_img is not None:
            main_width, main_height = main_img.size
            footer_width, footer_height = footer_img.size

            new_footer_height = int(footer_height * (main_width / footer_width))
            resized_footer = footer_img.resize(
                (main_width, new_footer_height), Image.Resampling.LANCZOS
            )

            total_height = main_height + new_footer_height
            combined_img = Image.new("RGB", (main_width, total_height))

            combined_img.paste(main_img, (0, 0))
            combined_img.paste(resized_footer, (0, main_height))

            st.success("✅ 하단 배너 합성이 완료되었습니다!")

            st.image(
                combined_img,
                caption="합성 완료 미리보기",
                use_container_width=True,
            )

            buf = io.BytesIO()
            combined_img.save(buf, format="JPEG", quality=95)
            byte_im = buf.getvalue()

            output_filename = f"{source_name}_final.jpg"

            with top_download_slot:
                st.download_button(
                    label="📥 완성된 상세페이지 다운로드",
                    data=byte_im,
                    file_name=output_filename,
                    mime="image/jpeg",
                    key="detail_download_btn",
                    use_container_width=True,
                )
