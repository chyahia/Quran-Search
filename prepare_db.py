import sqlite3

def prepare_database():
    print("جاري الاتصال بقاعدة البيانات...")
    conn = sqlite3.connect('quran.db')
    cur = conn.cursor()

    # 1. إضافة أعمدة السورة والآية لجدول الجذور
    try:
        cur.execute("ALTER TABLE root_words ADD COLUMN sura_id INTEGER")
        cur.execute("ALTER TABLE root_words ADD COLUMN aya_num INTEGER")
        print("تم إضافة الأعمدة الجديدة بنجاح.")
    except sqlite3.OperationalError:
        print("الأعمدة موجودة مسبقاً، سيتم تحديث بياناتها.")

    # 2. قراءة البيانات الحالية
    print("جاري تحليل أماكن الكلمات...")
    cur.execute("SELECT rowid, word_location FROM root_words")
    rows = cur.fetchall()

    # 3. تفكيك النص واستخراج رقم السورة والآية
    count = 0
    for rowid, loc in rows:
        parts = loc.split(':') # فصل النص عند نقطتين
        if len(parts) >= 2:
            sura = int(parts[0])
            aya = int(parts[1])
            # تحديث الصف بالقيم الجديدة
            cur.execute("UPDATE root_words SET sura_id = ?, aya_num = ? WHERE rowid = ?", (sura, aya, rowid))
            count += 1

    conn.commit()
    conn.close()
    print(f"تم الانتهاء بنجاح! تم تحديث {count} موقع في قاعدة البيانات.")

if __name__ == '__main__':
    prepare_database()