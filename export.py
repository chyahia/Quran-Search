import io
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

def create_word_document(query, results, display_type, stats_data=None):
    doc = Document()

    # --- إجبار اتجاه القسم كله RTL ---
    sectPr = doc.sections[0]._sectPr
    if sectPr.find(qn('w:bidi')) is None:
        sectPr.append(OxmlElement('w:bidi'))

    # --- الإصلاح الحاسم لمشكلة المحاذاة في Word 2010 ---
    settings_element = doc.settings.element
    theme_font_lang = settings_element.find(qn('w:themeFontLang'))
    if theme_font_lang is not None:
        theme_font_lang.set(qn('w:bidi'), 'ar-SA')

    def make_rtl(p):
        pPr = p._p.get_or_add_pPr()
        bidi = OxmlElement('w:bidi')
        pPr.append(bidi)

        mark_rPr = OxmlElement('w:rPr')
        mark_rtl = OxmlElement('w:rtl')
        mark_rPr.append(mark_rtl)
        pPr.append(mark_rPr)

        # مهم جدًا: مع bidi، وورد يعكس دلالة jc
        # LEFT هنا = محاذاة بصرية إلى اليمين (وليس RIGHT كما هو متوقع منطقيًا)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    def set_run_rtl(run, cs_font=None):
        run.font.rtl = True
        rPr = run._r.get_or_add_rPr()
        
        rFonts = rPr.find(qn('w:rFonts'))
        if rFonts is None:
            rFonts = OxmlElement('w:rFonts')
            rPr.append(rFonts)
        font_name = cs_font or run.font.name or 'Arial'
        rFonts.set(qn('w:cs'), font_name)
        rFonts.set(qn('w:hint'), 'cs')
        
        # --- مزامنة حجم النص المعقّد (szCs) مع الحجم العادي (sz) ---
        if run.font.size is not None:
            half_points = run.font.size.pt * 2  # الوحدة في XML نصف نقطة
            szCs = rPr.find(qn('w:szCs'))
            if szCs is None:
                szCs = OxmlElement('w:szCs')
                rPr.append(szCs)
            szCs.set(qn('w:val'), str(int(half_points)))

    title = doc.add_paragraph()
    make_rtl(title)
    run_title = title.add_run(f'\u200Fنتائج البحث في القرآن الكريم عن: "{query}"\u200F\n')
    run_title.font.size = Pt(18)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(27, 94, 32)
    set_run_rtl(run_title)

    meta = doc.add_paragraph()
    make_rtl(meta)
    meta_run = meta.add_run(f'\u200Fعدد الآيات المستخرجة: {len(results)}\u200F\n')
    meta_run.font.size = Pt(12)
    set_run_rtl(meta_run)

    RLM = "\u200F"

    # ================= إضافة الجدول الإحصائي =================
    if stats_data:
        labels = stats_data.get('labels', [])
        counts = stats_data.get('counts', [])
        total = sum(counts)
        
        if total > 0:
            table_title = doc.add_paragraph()
            make_rtl(table_title)
            t_run = table_title.add_run(f"{RLM}الإحصائيات التحليلية لتوزيع الكلمة:{RLM}")
            t_run.font.size = Pt(14)
            t_run.font.bold = True
            set_run_rtl(t_run)
            
            # إنشاء الجدول وإجبار اتجاهه (من اليمين لليسار)
            table = doc.add_table(rows=1, cols=3)
            table.style = 'Table Grid'
            tblPr = table._tbl.tblPr
            bidiVisual = OxmlElement('w:bidiVisual')
            tblPr.append(bidiVisual)

            hdr_cells = table.rows[0].cells
            headers = ['القسم', 'عدد الآيات', 'النسبة المئوية']
            for i, text in enumerate(headers):
                p = hdr_cells[i].paragraphs[0]
                make_rtl(p)
                run = p.add_run(RLM + text + RLM)
                run.font.size = Pt(12)
                run.font.bold = True
                set_run_rtl(run)

            for idx, label in enumerate(labels):
                count = counts[idx]
                if count > 0:  # إدراج القطاعات التي تحتوي على نتائج فقط
                    row_cells = table.add_row().cells
                    percent = round((count / total) * 100, 1)
                    row_data = [label, str(count), f"{percent}%"]
                    for i, text in enumerate(row_data):
                        p = row_cells[i].paragraphs[0]
                        make_rtl(p)
                        run = p.add_run(RLM + text + RLM)
                        run.font.size = Pt(12)
                        set_run_rtl(run)
            
            doc.add_paragraph() # مسافة فارغة بعد الجدول
    # ==========================================================

    for idx, item in enumerate(results, 1):
        p = doc.add_paragraph()
        make_rtl(p)

        run_num = p.add_run(f'{RLM}{idx}. {RLM}')
        run_num.font.bold = True
        run_num.font.size = Pt(14)
        set_run_rtl(run_num)

        text_to_show = item[display_type]
        run_aya = p.add_run(f"{RLM}﴿ {text_to_show} ﴾{RLM} ")
        run_aya.font.size = Pt(16)
        run_aya.font.name = 'Traditional Arabic'
        set_run_rtl(run_aya, cs_font='Traditional Arabic')

        run_ref = p.add_run(f"{RLM}[{item['sura_name']}:{item['aya_num']}]{RLM}")
        run_ref.font.bold = True
        run_ref.font.size = Pt(12)
        run_ref.font.color.rgb = RGBColor(100, 100, 100)
        set_run_rtl(run_ref)

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    return file_stream