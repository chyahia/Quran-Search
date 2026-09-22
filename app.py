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

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

app = Flask(__name__, 
            template_folder=resource_path('templates'),
            static_folder=resource_path('static'))
DB_PATH = resource_path('quran.db')
IS_LOCAL = False    # غيرها إلى False عند الرفع على موقع الويب المجاني

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

DIACRITICS_REGEX = re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]')

def strip_diacritics(word):
    return DIACRITICS_REGEX.sub('', word)

def get_char_diacritics(word):
    res = []
    current_char = None
    current_diacs = set()
    for char in word:
        if not DIACRITICS_REGEX.match(char):
            if current_char is not None:
                res.append((current_char, current_diacs))
            current_char = char
            current_diacs = set()
        else:
            if current_char is not None:
                current_diacs.add(char)
    if current_char is not None:
        res.append((current_char, current_diacs))
    return res

PREFIXES = ["", "و", "ف", "ب", "ك", "ل", "ال", "وال", "فال", "بال", "كال", "لل", "ول", "فل", "وب", "فب"]

def should_exclude(ayah_tashkeel, ex_words_data):
    ayah_clean = strip_diacritics(ayah_tashkeel)
    for ex in ex_words_data:
        ex_c = ex['clean']
        
        # 1. هل الكلمة تنتهي بالكلمة المطلوبة؟ (للسماح بالسوابق القرآنية)
        if ayah_clean.endswith(ex_c):
            # استخراج السابقة (إن وجدت)
            prefix = ayah_clean[:-len(ex_c)] if len(ayah_clean) > len(ex_c) else ""
            
            # 2. التأكد من أن الزيادة هي سابقة معتمدة
            if prefix in PREFIXES:
                user_chars = get_char_diacritics(ex['tashkeel'])
                ayah_chars = get_char_diacritics(ayah_tashkeel)
                
                # 3. محاذاة الحروف من النهاية (لضبط التشكيل حتى لو طالت الكلمة بالسابقة)
                ayah_chars_suffix = ayah_chars[-len(user_chars):]
                
                if len(user_chars) == len(ayah_chars_suffix):
                    match = True
                    for (u_char, u_diacs), (a_char, a_diacs) in zip(user_chars, ayah_chars_suffix):
                        if not u_diacs.issubset(a_diacs):
                            match = False
                            break
                    if match:
                        return True # استبعاد الكلمة بنجاح
    return False

def normalize_and_strip(word):
    w = re.sub(r'[^\u0621-\u064A]', '', word)
    if not w or w in STOP_WORDS: 
        return None
    stripped = w
    if len(w) > 4 and w.startswith(('وال', 'فال', 'بال', 'كال')):
        stripped = w[3:]
    elif len(w) > 3 and w.startswith(('لل', 'ال')):
        stripped = w[2:]
    elif len(w) > 3 and w.startswith(('و', 'ف', 'ب', 'ك', 'ل')):
        stripped = w[1:]
    
    if not stripped or stripped in STOP_WORDS or len(stripped) < 2:
        return None
    return stripped

def get_collocations(rows, query, match_type, logic, window_size, total_occurrences, target_col='text_clean', ngram_size=1, ex_words_data=None):
    before_counter = Counter()
    after_counter = Counter()
    q_words = [query] if logic == 'phrase' else query.split()
    
    for row in rows:
        clean_tokens = row['text_clean'].split()
        target_indexes = []

        tash_tokens = row['text_tashkeel'].split()
        invalid_indices = set()
        if ex_words_data:
            for idx, t_word in enumerate(tash_tokens):
                if should_exclude(t_word, ex_words_data):
                    invalid_indices.add(idx)
        
        if logic == 'phrase':
            q_len = len(q_words)
            for i in range(len(clean_tokens) - q_len + 1):
                if any(idx in invalid_indices for idx in range(i, i + q_len)): continue
                match = True
                for j, qw in enumerate(q_words):
                    if match_type == 'exact':
                        if not re.search(rf'(?<![\u0621-\u064A\u0671-\u06D3]){re.escape(qw)}(?![\u0621-\u064A\u0671-\u06D3])', clean_tokens[i+j]):
                            match = False; break
                    elif match_type == 'contains' and qw not in clean_tokens[i+j]:
                        match = False; break
                if match:
                    target_indexes.append((i, i + q_len - 1))
        else:
            for i, t in enumerate(clean_tokens):
                if i in invalid_indices: continue
                for qw in q_words:
                    if match_type == 'exact':
                        if re.search(rf'(?<![\u0621-\u064A\u0671-\u06D3]){re.escape(qw)}(?![\u0621-\u064A\u0671-\u06D3])', t):
                            target_indexes.append((i, i)); break
                    elif match_type == 'contains' and qw in t:
                        target_indexes.append((i, i)); break

        # استخراج الكلمات التي قبلها وبعدها
        for start_idx, end_idx in target_indexes:
            # قبل الكلمة
            for k in range(max(0, start_idx - window_size), start_idx):
                if k + ngram_size <= len(clean_tokens):
                    normalized = [normalize_and_strip(clean_tokens[i]) for i in range(k, k + ngram_size)]
                    if all(normalized): # إذا لم تحتوي العبارة على أداة أو حرف سيتم إضافتها
                        before_counter[" ".join(normalized)] += 1
                        
            # بعد الكلمة
            for k in range(end_idx + 1, min(len(clean_tokens), end_idx + 1 + window_size)):
                if k + ngram_size <= len(clean_tokens):
                    normalized = [normalize_and_strip(clean_tokens[i]) for i in range(k, k + ngram_size)]
                    if all(normalized):
                        after_counter[" ".join(normalized)] += 1

    top_before, top_after = [], []
    if total_occurrences > 0:
        for k, v in before_counter.items():
            if v > 1: top_before.append({'word': k, 'count': v, 'percent': round((v / total_occurrences) * 100, 1)})
        for k, v in after_counter.items():
            if v > 1: top_after.append({'word': k, 'count': v, 'percent': round((v / total_occurrences) * 100, 1)})
    
    return {'before': sorted(top_before, key=lambda x: x['count'], reverse=True)[:10], 
            'after': sorted(top_after, key=lambda x: x['count'], reverse=True)[:10]}

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
    return render_template('index.html', suras=suras, is_local=IS_LOCAL)

def get_grammar_stats(rows, match_type, clean_root=None, root_highlights=None):
    if match_type != 'root': return None

    conn = get_db_connection()
    cur = conn.cursor()
    queries = []
    
    # فلترة ذكية: نأخذ فقط أرقام الآيات التي لم يتم استبعادها
    valid_ayahs = {(r['sura_id'], r['aya_num']) for r in rows}

    try:
        if clean_root:
            cur.execute("""
                SELECT rw.sura_id, rw.aya_num, rw.word_location
                FROM root_words rw
                JOIN roots r ON rw.root_id = r.id
                WHERE REPLACE(r.arabic_trilateral, ' ', '') = ?
            """, (clean_root,))
            for loc in cur.fetchall():
                s_id, a_num = loc['sura_id'], loc['aya_num']
                if (s_id, a_num) in valid_ayahs:
                    try: 
                        w_idx = int(loc['word_location'].split(':')[2]) - 1
                        # التحقق الذكي: هل هذه الكلمة تم تلوينها (أي غير مستبعدة)؟
                        if root_highlights:
                            key = f"{s_id}_{a_num}"
                            if key not in root_highlights or w_idx not in root_highlights[key]:
                                continue
                        queries.append((s_id, a_num, w_idx + 1))
                    except: pass

        queries = list(set(queries))
        categories = {'nouns': [], 'verbs': []}
        
        for s_id, a_num, w_num in queries:
            cur.execute("SELECT arabic_grammar FROM morphology WHERE sura_id=? AND aya_num=? AND word_num=?", (s_id, a_num, w_num))
            for r in cur.fetchall():
                gr = r['arabic_grammar']
                if not gr: continue
                
                # تجاهل الضمائر والأدوات
                if any(x in gr for x in ['أداة', 'حرف', 'استئنافية', 'موصول', 'إشارة', 'ضمير']): continue 
                
                if any(x in gr for x in ['اسم', 'صفة']):
                    if 'مرفوع' in gr: categories['nouns'].append(('اسم (مرفوع)', s_id))
                    elif 'منصوب' in gr: categories['nouns'].append(('اسم (منصوب)', s_id))
                    elif 'مجرور' in gr: categories['nouns'].append(('اسم (مجرور)', s_id))
                    else: categories['nouns'].append(('اسم (غير محدد الحالة)', s_id))
                elif 'فعل' in gr:
                    categories['verbs'].append((gr, s_id))
                
    except sqlite3.OperationalError: pass
    conn.close()

    def process_cat(cat_list):
        counter = Counter([x[0] for x in cat_list])
        total = len(cat_list)
        details = []
        mushaf_bins = [(1, 11), (12, 22), (23, 34), (35, 45), (46, 57), (58, 68), (69, 79), (80, 91), (92, 102), (103, 114)]
        rev_bins = [(1, 11), (12, 22), (23, 34), (35, 45), (46, 57), (58, 68), (69, 79), (80, 91), (92, 102), (103, 114)]
        
        for gr, count in counter.most_common(10):
            sura_ids = [x[1] for x in cat_list if x[0] == gr]
            dist_mushaf = [0]*10
            dist_rev = [0]*10
            
            for sid in sura_ids:
                for i, (start, end) in enumerate(mushaf_bins):
                    if start <= sid <= end: dist_mushaf[i] += 1; break
                r_id = REV_ORDER_MAP.get(sid, 1)
                for i, (start, end) in enumerate(rev_bins):
                    if start <= r_id <= end: dist_rev[i] += 1; break
                    
            details.append({
                'name': gr, 'count': count, 'percent': round((count/total)*100, 1) if total>0 else 0, 
                'dist_mushaf': dist_mushaf, 'dist_revelation': dist_rev
            })
        return {'total': total, 'details': details}

    return {'nouns': process_cat(categories['nouns']), 'verbs': process_cat(categories['verbs'])}

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
    ngram_size = int(data.get('ngram_size', 1))
    excluded_ids = data.get('excluded_ids', [])
    excluded_words_input = data.get('excluded_words', '').strip()
    ex_words_data = []
    if excluded_words_input:
        for w in excluded_words_input.split():
            w_strip = w.strip()
            if w_strip:
                ex_words_data.append({'clean': strip_diacritics(w_strip), 'tashkeel': w_strip})

    if not query:
        return jsonify({'count': 0, 'occurrences': 0, 'results': [], 'chart': {}, 'collocations': {}, 'root_highlights': {}, 'grammar_dashboard': None})

    words = [query] if multi_word_logic == 'phrase' else query.split()
    if not words:
        return jsonify({'count': 0, 'occurrences': 0, 'results': [], 'chart': {}, 'collocations': {}, 'root_highlights': {}, 'grammar_dashboard': None})

    target_col = {'clean': 'text_clean', 'tashkeel': 'text_tashkeel', 'uthmani': 'text_uthmani'}.get(search_target, 'text_clean')

    conn = get_db_connection()
    cur = conn.cursor()

    conditions, params = [], []
    word_conditions = []
    root_highlights = {}
    root_matches_cache = []

    for w in words:
        if match_type == 'root':
            clean_root = w.replace(" ", "")
            cur.execute("""
                SELECT rw.sura_id, rw.aya_num, rw.word_location 
                FROM root_words rw 
                JOIN roots r ON rw.root_id = r.id 
                WHERE REPLACE(r.arabic_trilateral, ' ', '') = ?
            """, (clean_root,))
            root_matches_cache.extend(cur.fetchall())
            
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

    if excluded_ids:
        placeholders = ','.join('?' * len(excluded_ids))
        conditions.append(f"a.id NOT IN ({placeholders})")
        params.extend(excluded_ids)

    sql = f"""
        SELECT a.id, a.sura_id, a.aya_num, a.text_clean, a.text_tashkeel, a.text_uthmani, s.name as sura_name
        FROM ayas a JOIN suras s ON a.sura_id = s.id
        WHERE {" AND ".join(conditions)} ORDER BY a.id ASC
    """
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    
    valid_rows = []
    total_occurrences = 0
    root_highlights = {}
    
    root_cache_dict = {}
    if match_type == 'root':
        for r_sura, r_aya, r_loc in root_matches_cache:
            key = (r_sura, r_aya)
            if key not in root_cache_dict: root_cache_dict[key] = []
            try: root_cache_dict[key].append(int(r_loc.split(':')[2]) - 1)
            except: pass

    for row in rows:
        s_id = row['sura_id']
        a_num = row['aya_num']
        tash_words = row['text_tashkeel'].split()
        target_text = row[target_col]
        
        # 1. تحديد الكلمات المستبعدة في هذه الآية حصراً بذكاء شديد
        invalid_indices = set()
        if ex_words_data:
            for idx, t_word in enumerate(tash_words):
                if should_exclude(t_word, ex_words_data):
                    invalid_indices.add(idx)
                    
        # 2. طمس الكلمات المستبعدة مؤقتاً لكي لا يقرأها عداد (التطابق)
        if invalid_indices and len(target_text.split()) == len(tash_words):
            target_words_list = target_text.split()
            for idx in invalid_indices:
                target_words_list[idx] = "@@@"
            filtered_target_text = " ".join(target_words_list)
        else:
            filtered_target_text = target_text

        # 3. إحصاء التطابقات الناجية فقط
        if match_type == 'root':
            indices = root_cache_dict.get((s_id, a_num), [])
            valid_indices = []
            matched_invalids = set()
            
            for idx in indices:
                # خوارزمية "التقارب المرن" لمعالجة اختلاف الفهارس بين Corpus والنص العادي
                closest = None
                for offset in [0, 1, -1, 2, -2]:
                    if (idx + offset) in invalid_indices and (idx + offset) not in matched_invalids:
                        closest = idx + offset
                        break
                
                if closest is not None:
                    matched_invalids.add(closest) # الكلمة مطابقة للمستبعدة (تم الطمس)
                else:
                    valid_indices.append(idx) # الكلمة ناجية
            
            if valid_indices:
                valid_rows.append(row)
                total_occurrences += len(valid_indices)
                root_highlights[f"{s_id}_{a_num}"] = valid_indices
        else:
            aya_occurrences = 0
            if multi_word_logic == 'phrase':
                if match_type == 'exact':
                    pattern = rf'(?<![\u0621-\u064A\u0671-\u06D3]){re.escape(query)}(?![\u0621-\u064A\u0671-\u06D3])'
                    aya_occurrences = len(re.findall(pattern, filtered_target_text))
                else:
                    aya_occurrences = filtered_target_text.count(query)
            else:
                for w in words:
                    if match_type == 'exact':
                        pattern = rf'(?<![\u0621-\u064A\u0671-\u06D3]){re.escape(w)}(?![\u0621-\u064A\u0671-\u06D3])'
                        aya_occurrences += len(re.findall(pattern, filtered_target_text))
                    else:
                        aya_occurrences += filtered_target_text.count(w)
            
            if aya_occurrences > 0:
                valid_rows.append(row)
                total_occurrences += aya_occurrences

    results = [{
        'id': r['id'], 'sura_id': r['sura_id'], 'sura_name': r['sura_name'], 'aya_num': r['aya_num'],
        'clean': r['text_clean'], 'tashkeel': r['text_tashkeel'], 'uthmani': r['text_uthmani']
    } for r in valid_rows]

    clean_root = query.replace(" ", "") if match_type == 'root' else None
    grammar_chart_data = get_grammar_stats(valid_rows, match_type, clean_root, root_highlights)
    
    # تحديث استدعاء الكلمات المصاحبة بالمتغير الجديد
    collocations_data = get_collocations(valid_rows, query, match_type, multi_word_logic, context_window, total_occurrences, target_col, ngram_size, ex_words_data)
    chart_data = calculate_distribution(results)
    
    conn.close()

    return jsonify({
        'count': len(results), 
        'occurrences': total_occurrences, 
        'results': results, 
        'chart': chart_data,
        'collocations': collocations_data,
        'root_highlights': root_highlights,
        'grammar_dashboard': grammar_chart_data
    })

@app.route('/export/word', methods=['POST'])
def export_word():
    data = request.get_json()
    file_stream = create_word_document(
        query=data.get('query', ''), 
        query2=data.get('query2', None),
        results=data.get('results', []), 
        display_type=data.get('display_type', 'clean'),
        stats_data=data.get('stats_data', None),
        stats_data2=data.get('stats_data2', None),
        chart_image_mushaf=data.get('chart_image_mushaf', None),
        chart_image_rev=data.get('chart_image_rev', None),
        grammar_data=data.get('grammar_data', None),
        collocations=data.get('collocations', None),
        notes=data.get('notes', {})
    )
    return send_file(
        file_stream, as_attachment=True, 
        download_name="Quran_Search.docx",
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

@app.route('/shutdown', methods=['POST'])
def shutdown():
    os.kill(os.getpid(), signal.SIGINT)
    return jsonify({"success": True})

if __name__ == '__main__':
    def open_browser(): webbrowser.open_new("http://127.0.0.1:5555")
    Timer(1, open_browser).start()
    app.run(debug=False, port=5555)