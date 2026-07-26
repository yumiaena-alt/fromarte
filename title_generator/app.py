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
1. 가장 첫머리에는 반드시 브랜드명 [{brand_name}]을 배치할 것.
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
