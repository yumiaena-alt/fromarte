import io
import urllib.request
import streamlit as st
from PIL import Image

# 페이지 기본 설정
st.set_page_config(
    page_title="프롬아떼 상세페이지 배너 자동 병합기", page_icon="🖼️", layout="centered"
)

st.title("🖼️ 상세페이지 + 하단 배너 자동 병합기")
st.write(
    "상세페이지 캡처 이미지를 업로드하면 주문제작/AI 안내 하단 배너를 자동으로 합쳐줍니다."
)

# 호스팅되어 있는 하단 공통 배너 URL (수정 가능)
FOOTER_URL = "https://gi.esmplus.com/fromarte/wholesale/order.png"


@st.cache_data(ttl=3600)
def load_footer_image(url):
    """호스팅된 하단 배너 이미지를 불러와 캐싱합니다."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req) as response:
            footer_data = response.read()
        return Image.open(io.BytesIO(footer_data)).convert("RGB")
    except Exception as e:
        st.error(f"하단 배너 이미지를 불러오는 데 실패했습니다: {e}")
        return None


# 1. 파일 업로드 (상세페이지 캡처본)
uploaded_file = st.file_uploader(
    "상세페이지 캡처 이미지를 선택하세요 (JPG, PNG)", type=["jpg", "jpeg", "png"]
)

if uploaded_file is not None:
    # 이미지 불러오기
    main_img = Image.open(uploaded_file).convert("RGB")
    footer_img = load_footer_image(FOOTER_URL)

    if footer_img is not None:
        # 2. 이미지 가로 폭 맞추기 (상세페이지 가로 너비 기준)
        main_width, main_height = main_img.size
        footer_width, footer_height = footer_img.size

        # 하단 배너의 비율을 유지하면서 상세페이지 가로 폭에 맞게 리사이즈
        new_footer_height = int(footer_height * (main_width / footer_width))
        resized_footer = footer_img.resize(
            (main_width, new_footer_height), Image.Resampling.LANCZOS
        )

        # 3. 두 이미지 세로로 합치기
        total_height = main_height + new_footer_height
        combined_img = Image.new("RGB", (main_width, total_height))

        # 상세페이지 배치
        combined_img.paste(main_img, (0, 0))
        # 하단 배너 배치
        combined_img.paste(resized_footer, (0, main_height))

        st.success("✅ 하단 배너 합성이 완료되었습니다!")

        # 4. 결과 미리보기 및 저장 버튼
        st.image(
            combined_img,
            caption="합성 완료 미리보기",
            use_container_width=True,
        )

        # 파일 다운로드를 위해 바이트로 변환
        buf = io.BytesIO()
        combined_img.save(buf, format="JPEG", quality=95)
        byte_im = buf.getvalue()

        # 원본 파일명 추출 및 저장 파일명 생성
        original_name = uploaded_file.name.rsplit(".", 1)[0]
        output_filename = f"{original_name}_final.jpg"

        # 다운로드 버튼
        st.download_button(
            label="📥 완성된 상세페이지 다운로드",
            data=byte_im,
            file_name=output_filename,
            mime="image/jpeg",
        )