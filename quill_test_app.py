import streamlit as st
from streamlit.components.v1 import declare_component
import time

quill = declare_component(
    "quill_test",
    path="./quill_test_component"
)

st.title("Quill auto replace TEST")

if "html" not in st.session_state:
    st.session_state.html = "<p>Выдели этот текст и нажми ПКМ → Заменить</p>"

if "apply" not in st.session_state:
    st.session_state.apply = None

if "quill_key" not in st.session_state:
    st.session_state.quill_key = 0

evt = quill(
    value=st.session_state.html,
    apply_replace=st.session_state.apply,
    key=f"quill_{st.session_state.quill_key}"
)

if isinstance(evt, dict):
    if evt.get("type") == "replace_request":
        st.session_state.apply = {
            "range": evt["range"],
            "text": "ЗАМЕНЕНО ИИ",
            "_uid": time.time()
        }

        st.session_state.quill_key += 1   # пересоздать компонент
        st.rerun()

    if evt.get("type") == "content":
        st.session_state.html = evt["html"]
        st.session_state.apply = None

st.markdown("---")
st.markdown("### HTML:")
st.code(st.session_state.html, language="html")
