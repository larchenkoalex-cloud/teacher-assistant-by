import traceback
try:
    import streamlit_app
    print('IMPORT_OK')
except Exception:
    traceback.print_exc()
