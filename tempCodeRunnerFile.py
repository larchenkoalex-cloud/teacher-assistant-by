   st.session_state["generated_title"] = f"{subject or 'Урок'} — {topic}"[:200]
            st.session_state["stream_buffer"] = plan_text
            st.session_state["generated_content"] = plan_text
            st.success("✅ План сгенерирован. Редактор скрыт — правьте текст через предпросмотр и AI-замену.")

with col_editor:
    st.subheader("Предпросмотр плана урока")

    # Оставляем только визуальный редактор (WYSIWYG), чтобы не отвлекать учителя Markdown-разметкой.

    stream_placeholder = st.empty()

    # Редактор убран: работаем только с предпросмотром.

    # Если идёт генерация — показываем потоковый предпросмотр.
    # ВАЖНО: после окончания стрима сразу переключаемся на Quill в этом же прогоне,
    # без safe_rerun (иначе можно "застрять" без редактора).
    if st.session_state.get("is_generating"):
        if st.session_state.get("start_stream_now"):
            st.session_state["start_stream_now"] = False
            messages = st.session_state.pop("generated_messages", None)
            headers = st.session_state.pop("generated_headers", None)
            model_to_use = st.session_state.pop("generated_model", "deepseek/deepseek-chat")

            full_text = ""
            try:
                if messages and headers:
                    with st.spinner("🤖 Генерирую..."):
                        full_text = stream_generate_chat_via_api(
                            messages=messages,
                            headers=headers,
                            placeholder=stream_placeholder,
                            model=model_to_use,
                        )
            except Exception:
                full_text = ""

            if not full_text:
                full_text = generate_lesson_plan_locally(subject, grade, topic, notes, class_level)

            st.session_state["stream_buffer"] = full_text
            # Сохраняем сгенерированный Markdown отдельно — НЕ загружаем автоматически в редактор.
            st.session_state["generated_content"] = full_text
            # Сброс предпросмотра (пересчитается в HTML на следующем прогоне)
            st.session_state["preview_html"] = ""
            st.session_state["is_generating"] = False

        stream_buffer = st.session_state.get("stream_buffer", "")
        if stream_buffer:
            # Во время генерации показываем потоковый Markdown.
            stream_placeholder.markdown(_postprocess_plan_text(stream_buffer))

    if not st.session_state.get("is_generating"):
        # После генерации убираем потоковый Markdown, чтобы пользователь работал
        # только в Quill (иначе ПКМ будет открывать браузерное меню на обычном тексте страницы).
        stream_placeholder.empty()

        # --- Интерактивный предпросмотр с ПКМ→AI замена (без "режима редактора")
        preview_md = st.session_state.get("generated_content") or st.session_state.get("stream_buffer") or ""
        if "preview_html" not in st.session_state:
            st.session_state["preview_html"] = ""
        if "preview_apply_replace" not in st.session_state:
            st.session_state["preview_apply_replace"] = None
        if "preview_request_selection" not in st.session_state:
            st.session_state["preview_request_selection"] = None
        if "preview_request_uid" not in st.session_state:
            st.session_state["preview_request_uid"] = None
        if "preview_pending_action" not in st.session_state:
            st.session_state["preview_pending_action"] = None
        if "preview_selected_range" not in st.session_state:
            st.session_state["preview_selected_range"] = None
        if "preview_selected_text" not in st.session_state:
            st.session_state["preview_selected_text"] = ""
        if "preview_rewrite_range" not in st.session_state:
            st.session_state["preview_rewrite_range"] = None
        if "preview_rewrite_source" not in st.session_state:
            st.session_state["preview_rewrite_source"] = ""
        if "preview_rewrite_result" not in st.session_state:
            st.session_state["preview_rewrite_result"] = ""
        if "preview_event_log" not in st.session_state:
            st.session_state["preview_event_log"] = []

        if preview_md and not st.session_state.get("preview_html"):
            md = normalize_ai_markdown(_postprocess_plan_text(preview_md))
            html_val = quill_html_utils.sanitize_html_for_quill(markdown_to_html(md))
            st.session_state["preview_html"] = html_val

        with st.expander("Диагностика предпросмотра", expanded=False):
            st.write(
                {
                    "generated_content_len": len(preview_md or ""),
                    "preview_html_len": len(st.session_state.get("preview_html") or ""),
                    "quill_component": "ok" if quill_editor is not None else "missing",
                    "pending_action": st.session_state.get("preview_pending_action"),
                    "request_uid": st.session_state.get("preview_request_uid"),
                    "last_selected_text": st.session_state.get("preview_selected_text"),
                }
            )

        with st.expander("Лог событий компонента (последние 10)", expanded=False):
            logs = st.session_state.get("preview_event_log", [])
            for e in logs[:10]:
                st.write(e)

        if preview_md and not (st.session_state.get("preview_html") or "").strip():
            st.warning("Текст сгенерирован, но HTML предпросмотра пустой. Проверьте Диагностику.")

        prev_instr_choice_key = "preview_ai_instr_choice"
        prev_instr_custom_key = "preview_ai_instr_custom"
        if prev_instr_choice_key not in st.session_state:
            st.session_state[prev_instr_choice_key] = "Сократить и сделать яснее"
        if prev_instr_custom_key not in st.session_state:
            st.session_state[prev_instr_custom_key] = ""

        INSTR_PRESETS = [
            "Сократить и сделать яснее",
            "Упростить для учеников",
            "Сделать более официально",
            "Сделать более разговорно",
            "Исправить ошибки и улучшить стиль",
            "Переформулировать без изменения смысла",
            "Свой вариант...",
        ]

        def _current_instr() -> str:
            choice = (st.session_state.get(prev_instr_choice_key) or "").strip()
            if choice == "Свой вариант...":
                return (st.session_state.get(prev_instr_custom_key) or "").strip()
            return choice

        st.markdown("**Выделение → Переделать → (посмотреть) → Заменить**")
        st.selectbox("Инструкция для ИИ", INSTR_PRESETS, key=prev_instr_choice_key)
        if st.session_state.get(prev_instr_choice_key) == "Свой вариант...":
            st.text_input("Свой вариант инструкции", key=prev_instr_custom_key, placeholder="Например: сделай короче и добавь конкретику")

        btn_col1, btn_col2 = st.columns([1, 1])
        if btn_col1.button("Переделать выделенный фрагмент"):
            instr = _current_instr()
            if not instr:
                st.warning("Введите инструкцию для ИИ.")
            else:
                req_uid = time.time()
                st.session_state["preview_pending_action"] = "rewrite"
                st.session_state["preview_request_uid"] = req_uid
                st.session_state["preview_request_selection"] = {"_uid": req_uid}

                # Перезапуск необходим: в следующем прогоне компонент получит requestSelection
                # и вернёт событие selection, которое мы затем обработаем.
                st.rerun()

        can_apply = bool(st.session_state.get("preview_rewrite_result")) and bool(st.session_state.get("preview_rewrite_range"))
        if btn_col2.button("Заменить выделенный фрагмент", disabled=not can_apply):
            st.session_state["preview_apply_replace"] = {
                "range": st.session_state.get("preview_rewrite_range"),
                "text": st.session_state.get("preview_rewrite_result") or "",
                "_uid": time.time(),
            }
            # applyReplace будет отправлен в компонент в этом же прогоне.

        with st.expander("Предварительный просмотр переделанного фрагмента", expanded=True):
            src = st.session_state.get("preview_rewrite_source") or ""
            res = st.session_state.get("preview_rewrite_result") or ""
            if src:
                st.caption("Исходный фрагмент")
                st.text_area("Исходный фрагмент", value=src, height=90, disabled=True, key="preview_src_view", label_visibility="collapsed")
            st.caption("Результат (переделанный фрагмент)")
            st.text_area("Результат", value=res, height=140, key="preview_res_view", label_visibility="collapsed")

        if quill_editor is not None:
            evt_preview = quill_editor(
                value=st.session_state.get("preview_html") or "",
                height=420,
                placeholder="Сгенерируйте план — он появится здесь...",
                apply_replace=st.session_state.get("preview_apply_replace"),
                request_selection=st.session_state.get("preview_request_selection"),
                key="preview_quill",
            )
        else:
            evt_preview = None
            if preview_md:
                st.info("Компонент предпросмотра (Quill) недоступен. Проверьте установку/запуск приложения.")

        if isinstance(evt_preview, dict):
            # Логируем приходящие события от компонента для диагностики
            logs = st.session_state.get("preview_event_log", [])
            logs.insert(0, {"time": datetime.utcnow().isoformat(), "evt": evt_preview})
            st.session_state["preview_event_log"] = logs[:200]
            evt_type = evt_preview.get("type")
            if evt_type == "content":
                html_value = evt_preview.get("html")
                if html_value is not None:
                    st.session_state["preview_html"] = html_value
                    # Завершаем цикл apply, если он был
                    if st.session_state.get("preview_apply_replace") is not None:
                        st.session_state["preview_apply_replace"] = None
                        # Не делаем принудительный rerun: событие content уже пришло на rerun.
            elif evt_type == "selection":
                # Ответ компонента на одноразовый запрос выделения.
                # Важно: Streamlit компоненты возвращают "последнее значение" на каждом rerun,
                # поэтому обрабатываем selection только если он соответствует текущему запросу.
                req_uid = st.session_state.get("preview_request_uid")
                evt_uid = evt_preview.get("request_uid")
                if not req_uid or evt_uid != req_uid:
                    # Событие не относится к текущему запросу — игнорируем, чтобы не зациклить rerun.
                    pass
                else:
                    st.session_state["preview_request_selection"] = None
                    st.session_state["preview_request_uid"] = None

                    rng = evt_preview.get("range")
                    txt = (evt_preview.get("text") or "")
                    st.session_state["preview_selected_range"] = rng
                    st.session_state["preview_selected_text"] = txt

                    if st.session_state.get("preview_pending_action") == "rewrite":
                        st.session_state["preview_pending_action"] = None
                        sel_text = (txt or "").strip()
                        instr = _current_instr()
                        api_key = st.session_state.get("api_key") or os.getenv("OPENROUTER_API_KEY")

                        if not api_key:
                            st.error("API ключ не найден. Укажите OpenRouter API key слева (sk-or-v1-...).")
                        elif not rng or not rng.get("length"):
                            st.warning("Сначала выделите фрагмент в тексте.")
                        elif not sel_text:
                            st.warning("Пустое выделение.")
                        elif len(sel_text) > 4000:
                            st.error("Фрагмент слишком длинный (макс 4000 символов). Разбейте на части.")
                        elif not instr:
                            st.warning("Введите инструкцию для ИИ.")
                        else:
                            prompt = (
                                "Переделай фрагмент текста согласно инструкции.\n"
                                "Ответ дай только новым текстом без комментариев.\n\n"
                                f"Фрагмент:\n---\n{sel_text}\n---\n"
                                f"Инструкция: {instr}"
                            )
                            with st.spinner("ИИ переделывает выделение..."):
                                resp = generate_with_deepseek(api_key, prompt)
                            ai_text = None
                            if isinstance(resp, dict):
                                ai_text = resp.get("choices", [{}])[0].get("message", {}).get("content")
                            ai_text = (ai_text or "").strip()
                            if not ai_text:
                                st.error("Не удалось получить ответ от ИИ.")
                            else:
                                st.session_state["pr