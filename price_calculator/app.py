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
                def get_available_flash_models(_api_key_marker):
                    """실제로 generateContent를 지원하는 모델만 조회 (하드코딩 대신)."""
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

                # 캐시 키 용도로만 사용 (API 키 자체를 노출하지 않음)
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
