import io
import re
import os
import sys
import signal
import sqlite3
import webbrowser
from threading import Timer
from collections import Counter
from flask import Flask, jsonify, render_template, request, send_file
from export import create_word_document

# دالة ذكية لاكتشاف مسار الملفات داخل النسخة التنفيذية (exe)
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ربط المسارات بالدالة الجديدة ليتعرف عليها البرنامج داخل مجلد _internal
app = Flask(__name__, 
            template_folder=resource_path('templates'),
            static_folder=resource_path('static'))
DB_PATH = resource_path('quran.db')
IS_LOCAL = True  # غيرها إلى False عند الرفع على موقع الويب المجاني

# خريطة ترتيب النزول لمعرفة المكي والمدني
REV_ORDER_MAP = {
    96: 1, 68: 2, 73: 3, 74: 4, 1: 5, 111: 6, 81: 7, 87: 8, 92: 9, 89: 10, 
    93: 11, 94: 12, 103: 13, 100: 14, 108: 15, 102: 16, 107: 17, 109: 18, 105: 19, 113: 20, 
    114: 21, 112: 22, 53: 23, 80: 24, 97: 25, 91: 26, 85: 27, 95: 28, 106: 29, 101: 30, 
    75: 31, 104: 32, 77: 33, 50: 34, 90: 35, 86: 36, 54: 37, 38: 38, 7: 39, 72: 40, 
    36: 41, 25: 42, 35: 43, 19: 44, 20: 45, 56: 46, 26: 47, 27: 48, 28: 49, 17: 50, 
    10: 51, 11: 52, 12: 53, 15: 54, 6: 55, 37: 56, 31: 57, 34: 58, 39: 59, 40: 60, 
    41: 61, 42: 62, 43: 63, 44: 64, 45: 65, 46: 66, 51: 67, 88: 68, 18: 69, 16: 70, 
    71: 71, 14: 72, 21: 73, 23: 74, 32: 75, 52: 76, 67: 77, 69: 78, 70: 79, 78: 80, 
    79: 81, 82: 82, 84: 83, 30: 84, 29: 85, 83: 86, 2: 87, 8: 88, 3: 89, 33: 90, 
    60: 91, 4: 92, 99: 93, 57: 94, 47: 95, 13: 96, 55: 97, 76: 98, 65: 99, 98: 100, 
    59: 101, 24: 102, 22: 103, 63: 104, 58: 105, 49: 106, 66: 107, 64: 108, 61: 109, 62: 110, 
    48: 111, 5: 112, 9: 113, 110: 114
}

# قائمة التجاهل الموسعة 
STOP_WORDS = {
    "في", "من", "على", "إلى", "عن", "مع", "يا", "أيها", "الذين", "الذي", "التي", "ما", "لا", "إن", "أن", 
    "هل", "بل", "قد", "لقد", "لم", "لن", "ثم", "أو", "و", "ف", "ب", "ك", "ل", "هذا", "هذه", "هؤلاء", "ذلك", 
    "تلك", "أولئك", "هم", "هن", "هو", "هي", "إياك", "إياه", "كان", "كانوا", "كنتم", "إنما", "إلا", "غير", 
    "بين", "إذا", "إذ", "لو", "لولا", "كل", "أي", "نحن", "أنت", "أنتم", "له", "لهم", "عليكم", "إليهم", "بهم", 
    "به", "عليه", "فيها", "فيهم", "منهم", "منها", "عنهم", "عنها", "قال", "قالوا", "قل", "بها", "اللاتي", 
    "اللواتي", "اللذان", "هذان", "هاتان", "أنا", "إنا", "إني", "أني", "أنه", "أنهم", "أنكم", "إنهم", "إنكم", 
    "فإن", "فلا", "ولا", "وما", "فما", "كما", "بما", "لما", "أما", "إما", "وهم", "فهم", "ولهم", "فلهم", "إذن", 
    "حتى", "دون", "عند", "أين", "كيف", "كم", "متى", "أينما", "حيث", "رب", "ربنا", "ياأيها", "الناس",
    "عذاب", "عذابا", "ذين", "لذين", "وفي", "ومن", "فمن", "أمن", "لمن", "بمن", "عمن", "ومما", "مما", "عما",
    "وهو", "وهي", "وهذا", "وهذه", "فإنما", "وإنما", "وإذا", "فإذا", "وإن", "ألا", "وإذ"
}

def normalize_and_strip(word):
    # 1. الإبقاء على الحروف العربية فقط
    w = re.sub(r'[^\u0621-\u064A]', '', word)
    if not w or w in STOP_WORDS: 
        return None
    
    stripped = w
    # 2. تجريد السوابق
    if len(w) > 4 and w.startswith(('وال', 'فال', 'بال', 'كال')):
        stripped = w[3:]
    elif len(w) > 3 and w.startswith(('لل', 'ال')):
        stripped = w[2:]
    elif len(w) > 3 and w.startswith(('و', 'ف', 'ب', 'ك', 'ل')):
        stripped = w[1:]
    
    # 3. اختبار الكلمة بعد التجريد
    if not stripped or stripped in STOP_WORDS or len(stripped) < 2:
        return None
        
    return stripped

def get_collocations(rows, query, match_type, logic, window_size, total_occurrences):
    before_counter = Counter()
    after_counter = Counter()
    
    q_words = [query] if logic == 'phrase' else query.split()
    
    for row in rows:
        text_tokens = row['text_clean'].split()
        target_indexes = []
        
        if logic == 'phrase':
            q_len = len(q_words)
            for i in range(len(text_tokens) - q_len + 1):
                match = True
                for j, qw in enumerate(q_words):
                    if match_type == 'exact' and text_tokens[i+j] != qw:
                        match = False; break
                    elif match_type == 'contains' and qw not in text_tokens[i+j]:
                        match = False; break
                if match:
                    target_indexes.append((i, i + q_len - 1))
        else:
            for i, t in enumerate(text_tokens):
                for qw in q_words:
                    if (match_type == 'exact' and t == qw) or (match_type == 'contains' and qw in t):
                        target_indexes.append((i, i))
                        break

        for start_idx, end_idx in target_indexes:
            # قبل الكلمة
            for k in range(max(0, start_idx - window_size), start_idx):
                cw = normalize_and_strip(text_tokens[k])
                if cw: before_counter[cw] += 1
            # بعد الكلمة
            for k in range(end_idx + 1, min(len(text_tokens), end_idx + 1 + window_size)):
                cw = normalize_and_strip(text_tokens[k])
                if cw: after_counter[cw] += 1

    top_before, top_after = [], []
    
    if total_occurrences > 0:
        for k, v in before_counter.items():
            if v > 1:
                percent = round((v / total_occurrences) * 100, 1)
                top_before.append({'word': k, 'count': v, 'percent': percent})
                
        for k, v in after_counter.items():
            if v > 1:
                percent = round((v / total_occurrences) * 100, 1)
                top_after.append({'word': k, 'count': v, 'percent': percent})
    
    top_before = sorted(top_before, key=lambda x: x['count'], reverse=True)[:10]
    top_after = sorted(top_after, key=lambda x: x['count'], reverse=True)[:10]
    
    return {'before': top_before, 'after': top_after}

def regexp_match(expr, item):
    if item is None: return False
    return re.search(expr, item) is not None

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.create_function('REGEXP', 2, regexp_match)
    return conn

def calculate_distribution(results):
    mushaf_bins = [(1, 11, "الفاتحة-هود"), (12, 22, "يوسف-الحج"), (23, 34, "المؤمنون-سبأ"), (35, 45, "فاطر-الجاثية"), (46, 57, "الأحقاف-الحديد"), (58, 68, "المجادلة-القلم"), (69, 79, "الحاقة-النازعات"), (80, 91, "عبس-الشمس"), (92, 102, "الليل-التكاثر"), (103, 114, "العصر-الناس")]
    rev_bins = [(1, 11, "العلق-الضحى"), (12, 22, "الشرح-الإخلاص"), (23, 34, "النجم-ق"), (35, 45, "البلد-طه"), (46, 57, "الواقعة-لقمان"), (58, 68, "سبأ-الغاشية"), (69, 79, "الكهف-المعارج"), (80, 91, "النبأ-الممتحنة"), (92, 102, "النساء-النور"), (103, 114, "الحج-النصر")]
    mushaf_counts = [0] * 10
    rev_counts = [0] * 10

    for row in results:
        s_id = row['sura_id']
        for i, (start, end, _) in enumerate(mushaf_bins):
            if start <= s_id <= end: mushaf_counts[i] += 1; break
        r_id = REV_ORDER_MAP.get(s_id, 1)
        for i, (start, end, _) in enumerate(rev_bins):
            if start <= r_id <= end: rev_counts[i] += 1; break

    return {
        'mushaf': {'labels': [b[2] for b in mushaf_bins], 'counts': mushaf_counts},
        'revelation': {'labels': [b[2] for b in rev_bins], 'counts': rev_counts}
    }

@app.route('/')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM suras ORDER BY id ASC")
    suras = [dict(row) for row in cur.fetchall()]
    conn.close()
    # التعديل هنا: أضفنا is_local
    return render_template('index.html', suras=suras, is_local=IS_LOCAL)

@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json()
    query = data.get('query', '').strip()
    match_type = data.get('match_type', 'contains')
    search_target = data.get('search_target', 'clean')
    sura_filter = data.get('sura_filter', 'all')
    type_filter = data.get('type_filter', 'all')
    multi_word_logic = data.get('multi_word_logic', 'and')
    context_window = int(data.get('context_window', 1))

    if not query:
        return jsonify({'count': 0, 'occurrences': 0, 'results': [], 'chart': {}, 'collocations': {}, 'root_highlights': {}})

    words = [query] if multi_word_logic == 'phrase' else query.split()
    if not words:
        return jsonify({'count': 0, 'occurrences': 0, 'results': [], 'chart': {}, 'collocations': {}, 'root_highlights': {}})

    target_col = {'clean': 'text_clean', 'tashkeel': 'text_tashkeel', 'uthmani': 'text_uthmani'}.get(search_target, 'text_clean')

    conn = get_db_connection()
    cur = conn.cursor()

    conditions, params = [], []
    word_conditions = []
    
    root_highlights = {}
    total_root_occurrences = 0

    for w in words:
        if match_type == 'root':
            clean_root = w.replace(" ", "")
            
            # 1. جلب مواقع المشتقات لإنشاء خريطة التلوين
            cur.execute("""
                SELECT rw.sura_id, rw.aya_num, rw.word_location 
                FROM root_words rw 
                JOIN roots r ON rw.root_id = r.id 
                WHERE REPLACE(r.arabic_trilateral, ' ', '') = ?
            """, (clean_root,))
            root_matches = cur.fetchall()
            
            total_root_occurrences += len(root_matches)
            
            for r_sura, r_aya, r_loc in root_matches:
                key = f"{r_sura}_{r_aya}"
                try:
                    # تحويل مكان الكلمة (مثل 41:24:4) إلى فهرس برمجي يبدأ من 0 (تصبح 3)
                    word_idx = int(r_loc.split(':')[2]) - 1 
                    if key not in root_highlights:
                        root_highlights[key] = []
                    root_highlights[key].append(word_idx)
                except:
                    pass
            
            # 2. شرط جلب الآيات نفسها
            word_conditions.append("""
                EXISTS (
                    SELECT 1 FROM root_words rw 
                    JOIN roots r ON rw.root_id = r.id 
                    WHERE REPLACE(r.arabic_trilateral, ' ', '') = ? 
                    AND rw.sura_id = a.sura_id 
                    AND rw.aya_num = a.aya_num
                )
            """)
            params.append(clean_root)
            
        elif match_type == 'exact':
            pattern = rf'(?<![\u0621-\u064A\u0671-\u06D3]){re.escape(w)}(?![\u0621-\u064A\u0671-\u06D3])'
            word_conditions.append(f"a.{target_col} REGEXP ?")
            params.append(pattern)
        else:
            word_conditions.append(f"a.{target_col} LIKE ?")
            params.append(f'%{w}%')
    
    joiner = " AND " if multi_word_logic in ['and', 'phrase'] else " OR "
    conditions.append(f"({joiner.join(word_conditions)})")

    if sura_filter != 'all':
        conditions.append("a.sura_id = ?")
        params.append(int(sura_filter))

    if type_filter != 'all':
        meccan_ids = [s for s, r in REV_ORDER_MAP.items() if r <= 86]
        medinan_ids = [s for s, r in REV_ORDER_MAP.items() if r > 86]
        target_list = meccan_ids if type_filter == 'meccan' else medinan_ids
        conditions.append(f"a.sura_id IN ({','.join('?' * len(target_list))})")
        params.extend(target_list)

    sql = f"""
        SELECT a.id, a.sura_id, a.aya_num, a.text_clean, a.text_tashkeel, a.text_uthmani, s.name as sura_name
        FROM ayas a JOIN suras s ON a.sura_id = s.id
        WHERE {" AND ".join(conditions)} ORDER BY a.id ASC
    """
    
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    
    total_occurrences = total_root_occurrences if match_type == 'root' else 0
    
    if match_type != 'root':
        for row in rows:
            if multi_word_logic == 'phrase':
                if match_type == 'exact':
                    pattern = rf'(?<![\u0621-\u064A\u0671-\u06D3]){re.escape(query)}(?![\u0621-\u064A\u0671-\u06D3])'
                    total_occurrences += len(re.findall(pattern, row[target_col]))
                else:
                    total_occurrences += row[target_col].count(query)
            else:
                for w in words:
                    if match_type == 'exact':
                        pattern = rf'(?<![\u0621-\u064A\u0671-\u06D3]){re.escape(w)}(?![\u0621-\u064A\u0671-\u06D3])'
                        total_occurrences += len(re.findall(pattern, row[target_col]))
                    else:
                        total_occurrences += row[target_col].count(w)

    results = [{
        'sura_id': r['sura_id'], 'sura_name': r['sura_name'], 'aya_num': r['aya_num'],
        'clean': r['text_clean'], 'tashkeel': r['text_tashkeel'], 'uthmani': r['text_uthmani']
    } for r in rows]

    collocations_data = get_collocations(rows, query, match_type, multi_word_logic, context_window, total_occurrences)
    chart_data = calculate_distribution(results)
    
    conn.close()

    return jsonify({
        'count': len(results), 
        'occurrences': total_occurrences, 
        'results': results, 
        'chart': chart_data,
        'collocations': collocations_data,
        'root_highlights': root_highlights
    })

@app.route('/export/word', methods=['POST'])
def export_word():
    data = request.get_json()
    file_stream = create_word_document(
        query=data.get('query', ''), 
        results=data.get('results', []), 
        display_type=data.get('display_type', 'clean'),
        stats_data=data.get('stats_data', None)
    )
    return send_file(
        file_stream, as_attachment=True, download_name="Quran_Search.docx",
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

@app.route('/shutdown', methods=['POST'])
def shutdown():
    os.kill(os.getpid(), signal.SIGINT)
    return jsonify({"success": True})

if __name__ == '__main__':
    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5555")
    
    # تأخير فتح المتصفح لثانية واحدة حتى يتأكد من عمل الخادم
    Timer(1, open_browser).start()
    
    # تم إيقاف وضع التصحيح (debug=False) لكي لا يفتح المتصفح مرتين، ولأنه الأنسب للنسخة النهائية
    app.run(debug=False, port=5555)