import sqlite3, os
DB = r'h:\Visio_Progect\teacher-assistant\teacher_assistant_visits.db'
print('DB path:', DB)
print('DB exists:', os.path.exists(DB))
try:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    try:
        cur.execute('SELECT COUNT(*) FROM clients')
        print('clients:', cur.fetchone()[0])
    except Exception as e:
        print('clients: ERR', e)
    try:
        cur.execute("SELECT v FROM meta_visits WHERE k='page_views'")
        r = cur.fetchone()
        print('page_views:', r[0] if r else 0)
    except Exception as e:
        print('page_views: ERR', e)
    try:
        cur.execute("SELECT v FROM meta_visits WHERE k='unique_visitors'")
        r = cur.fetchone()
        print('unique_visitors:', r[0] if r else 0)
    except Exception as e:
        print('unique_visitors: ERR', e)
    con.close()
except Exception as e:
    print('ERR opening DB:', e)
