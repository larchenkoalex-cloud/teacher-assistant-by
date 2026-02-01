import streamlit as st


def safe_rerun() -> None:
    """Безопасно перезапускает скрипт Streamlit с несколькими fallback-опциями.

    В некоторых версиях Streamlit `st.experimental_rerun` может быть недоступен.
    Пытаемся вызвать его, затем пытаемся поднять внутреннее `RerunException`,
    а если и это не работает — помечаем `st.session_state` и вызываем `st.stop()`.
    """
    try:
        st.rerun()
    except Exception:
        try:
            from streamlit.runtime.scriptrunner.script_runner import RerunException

            raise RerunException()
        except Exception:
            st.session_state["_rerun_indicator"] = st.session_state.get("_rerun_indicator", 0) + 1
            st.stop()
