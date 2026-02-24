# noinspection PyProtectedMember,PyBroadException,PyTypeChecker,DuplicatedCode
# docx_generator.py

from pathlib import Path
import copy
import subprocess
from typing import Optional, Tuple

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from paths import (
    TEMPLATE_CONTRACT,
    TEMPLATE_SCHEDULE,
    ISTISNA_TEMPLATE,
)

# ВАЖНО: чтобы документ оставался 1:1 как шаблон, мы НЕ трогаем стили/шрифты/абзацы.
# Генератор делает только замену плейсхолдеров, сохраняя исходное форматирование шаблона.
PRESERVE_TEMPLATE_FORMAT = True


def _clone_run_rpr(src_run, dst_run) -> None:
    """
    Копирует XML-свойства символов (w:rPr) из src_run в dst_run.
    Нужно, чтобы при жёсткой замене плейсхолдера новый run унаследовал форматирование шаблона.
    """
    src_r = src_run._element
    dst_r = dst_run._element

    src_rpr = src_r.find(qn("w:rPr"))
    if src_rpr is None:
        return

    dst_rpr = dst_r.find(qn("w:rPr"))
    if dst_rpr is not None:
        dst_r.remove(dst_rpr)

    dst_r.insert(0, copy.deepcopy(src_rpr))


def _set_run_font(run, family: str, size_pt: int) -> None:
    """
    Явно фиксирует шрифт run на high/low level API.
    Нужен как fallback для шаблонов, где у донора нет явного rPr.
    """
    run.font.name = family
    run.font.size = Pt(size_pt)
    r = run._element
    rpr = r.get_or_add_rPr()
    rfonts = rpr.rFonts
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), family)
    rfonts.set(qn("w:hAnsi"), family)
    rfonts.set(qn("w:eastAsia"), family)
    rfonts.set(qn("w:cs"), family)
    half_points = str(int(size_pt * 2))
    sz = rpr.find(qn("w:sz"))
    if sz is None:
        sz = OxmlElement("w:sz")
        rpr.append(sz)
    sz.set(qn("w:val"), half_points)
    szcs = rpr.find(qn("w:szCs"))
    if szcs is None:
        szcs = OxmlElement("w:szCs")
        rpr.append(szcs)
    szcs.set(qn("w:val"), half_points)


# noinspection DuplicatedCode
def _force_font(run, pt=10, family="Times New Roman"):
    # python-docx high-level API
    run.font.size = Pt(pt)
    run.font.name = family

    # clear features that visually shrink glyphs
    try:
        run.font.superscript = False
        run.font.subscript = False
        run.font.small_caps = False
        run.font.all_caps = False
    except Exception:
        pass

    # Low-level XML to avoid Word reapplying theme/eastAsia/half-point size:
    r = run._element
    rpr = r.get_or_add_rPr()

    # ensure rFonts exists
    if rpr.rFonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    else:
        rfonts = rpr.rFonts

    rfonts.set(qn("w:ascii"), family)
    rfonts.set(qn("w:hAnsi"), family)
    rfonts.set(qn("w:eastAsia"), family)
    rfonts.set(qn("w:cs"), family)

    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:csTheme"):
        if rfonts.get(qn(attr)) is not None:
            del rfonts.attrib[qn(attr)]

    half_points = str(int(pt * 2))

    # w:sz
    sz = rpr.find(qn("w:sz"))
    if sz is None:
        sz = OxmlElement("w:sz")
        rpr.append(sz)
    sz.set(qn("w:val"), half_points)

    # w:szCs
    szcs = rpr.find(qn("w:szCs"))
    if szcs is None:
        szcs = OxmlElement("w:szCs")
        rpr.append(szcs)
    szcs.set(qn("w:val"), half_points)

    # strip XML attrs that may make text look smaller or raised/lowered
    for tag in ("w:vertAlign", "w:position", "w:spacing", "w:smallCaps", "w:caps"):
        node = rpr.find(qn(tag))
        if node is not None:
            rpr.remove(node)

    # force baseline
    va = OxmlElement("w:vertAlign")
    va.set(qn("w:val"), "baseline")
    rpr.append(va)

    # remove character style reference
    rstyle = rpr.find(qn("w:rStyle"))
    if rstyle is not None:
        rpr.remove(rstyle)


def _replace_placeholder_in_paragraph_strict(
    paragraph,
    key: str,
    value: str,
    pt: int = 10,
    family: str = "Times New Roman",
    preferred_font: Optional[Tuple[str, int]] = None,
) -> bool:
    """
    Жёсткая замена плейсхолдера key на value в абзаце, даже если key разбит на несколько runs.
    Возвращает True если была произведена замена.
    """
    full = "".join(r.text or "" for r in paragraph.runs)
    idx = full.find(key)
    if idx < 0:
        return False

    spans = []
    pos = 0
    for r in paragraph.runs:
        txt = r.text or ""
        spans.append((pos, pos + len(txt), r))
        pos += len(txt)

    start = idx
    end = idx + len(key)

    first_i = next(i for i, (a, b, _) in enumerate(spans) if not (b <= start or a >= end))
    last_i = next(i for i in range(len(spans) - 1, -1, -1) if not (spans[i][1] <= start or spans[i][0] >= end))

    first_run = spans[first_i][2]
    last_run = spans[last_i][2]

    first_a, _, _ = spans[first_i]
    _, last_b, _ = spans[last_i]

    first_prefix_len = max(0, start - first_a)
    last_suffix_len = max(0, last_b - end)

    # донор форматирования (важно для underline/линий в шапке)
    donor_run = first_run

    # 1) Первый run: префикс до key
    first_text = first_run.text or ""
    first_run.text = first_text[:first_prefix_len]

    # 2) Промежуточные runs очистить
    for j in range(first_i + 1, last_i):
        spans[j][2].text = ""

    # 3) Последний run: суффикс после key
    last_text = last_run.text or ""
    last_run.text = last_text[len(last_text) - last_suffix_len:] if last_suffix_len > 0 else ""

    # 4) Вставляем новый run со значением сразу после first_run
    insert_after = first_run
    new_run = paragraph.add_run("")
    paragraph._p.insert(paragraph._p.index(insert_after._r) + 1, new_run._r)
    new_run.text = value

    if PRESERVE_TEMPLATE_FORMAT:
        _clone_run_rpr(donor_run, new_run)
        try:
            new_run.style = donor_run.style
        except Exception:
            pass
        # Fallback for runs without explicit rPr: copy high-level font attrs.
        try:
            new_run.font.name = donor_run.font.name
            new_run.font.size = donor_run.font.size
            new_run.bold = donor_run.bold
            new_run.italic = donor_run.italic
            new_run.underline = donor_run.underline
        except Exception:
            pass
        # If donor has no explicit font, pin configured default.
        if preferred_font and donor_run.font.name is None and donor_run.font.size is None:
            try:
                _set_run_font(new_run, preferred_font[0], preferred_font[1])
            except Exception:
                pass
    else:
        _force_font(new_run, pt, family)
        for j in range(first_i, last_i + 1):
            _force_font(spans[j][2], pt, family)
        _normalize_paragraph(paragraph, pt, family)

    return True


def _replace_in_paragraph(
    paragraph,
    mapping: dict,
    fallback_font_pt: int = 10,
    preferred_font: Optional[Tuple[str, int]] = None,
):
    changed = False

    # 1) Простые замены внутри отдельных runs
    for run in paragraph.runs:
        original = run.text or ""
        new_text = original
        for key, val in mapping.items():
            if key in new_text:
                new_text = new_text.replace(key, str(val))
        if new_text != original:
            run.text = new_text
            if preferred_font and run.font.name is None and run.font.size is None:
                try:
                    _set_run_font(run, preferred_font[0], preferred_font[1])
                except Exception:
                    pass
            if not PRESERVE_TEMPLATE_FORMAT:
                _force_font(run, fallback_font_pt, "Times New Roman")
            changed = True

    # 2) Жёсткая замена, если плейсхолдеры разбиты на несколько runs
    for key, val in mapping.items():
        if key in (paragraph.text or ""):
            if _replace_placeholder_in_paragraph_strict(
                paragraph,
                key,
                str(val),
                fallback_font_pt,
                "Times New Roman",
                preferred_font=preferred_font,
            ):
                changed = True

    if changed and not PRESERVE_TEMPLATE_FORMAT:
        _normalize_paragraph(paragraph, fallback_font_pt, "Times New Roman")


def _clear_paragraph_char_props(paragraph):
    """
    Очищает только проблемные символьные свойства на уровне абзаца (w:pPr/w:rPr),
    не удаляя весь rPr (иначе теряется формат нумерации).
    """
    p = paragraph._element
    pPr = p.find(qn("w:pPr"))
    if pPr is None:
        return
    rPr = pPr.find(qn("w:rPr"))
    if rPr is None:
        return
    for tag in ("w:vertAlign", "w:position", "w:spacing", "w:smallCaps", "w:caps", "w:rStyle"):
        node = rPr.find(qn(tag))
        if node is not None:
            rPr.remove(node)
    va = OxmlElement("w:vertAlign")
    va.set(qn("w:val"), "baseline")
    rPr.append(va)


def _ensure_para_numbering_font(paragraph, font_name="Times New Roman", font_size_pt=10):
    """
    Выставляет шрифт/размер для НУМЕРАЦИИ абзаца (цифры списков 1., 2.1, ...),
    т.к. Word берёт их из w:pPr/w:rPr.
    """
    p = paragraph._element
    pPr = p.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p.insert(0, pPr)

    rPr = pPr.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        pPr.append(rPr)

    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)

    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rFonts.set(qn(a), font_name)
        theme_attr = a + "Theme"
        if rFonts.get(qn(theme_attr)) is not None:
            del rFonts.attrib[qn(theme_attr)]

    hp = str(int(font_size_pt * 2))
    sz = rPr.find(qn("w:sz"))
    if sz is None:
        sz = OxmlElement("w:sz")
        rPr.append(sz)
    sz.set(qn("w:val"), hp)

    szcs = rPr.find(qn("w:szCs"))
    if szcs is None:
        szcs = OxmlElement("w:szCs")
        rPr.append(szcs)
    szcs.set(qn("w:val"), hp)

    va = rPr.find(qn("w:vertAlign"))
    if va is not None:
        rPr.remove(va)
    va = OxmlElement("w:vertAlign")
    va.set(qn("w:val"), "baseline")
    rPr.append(va)


def _normalize_paragraph(paragraph, pt: int = 10, family: str = "Times New Roman"):
    """
    Полная нормализация абзаца (используется только если PRESERVE_TEMPLATE_FORMAT=False)
    """
    try:
        paragraph.style = paragraph.part.styles["Normal"]
    except Exception:
        pass

    try:
        pf = paragraph.paragraph_format
        pf.keep_with_next = False
        pf.keep_together = False
        pf.page_break_before = False
        pf.space_before = None
        pf.space_after = None
    except Exception:
        pass

    _clear_paragraph_char_props(paragraph)
    _desuperscript_paragraph(paragraph)
    _ensure_para_numbering_font(paragraph, family, pt)

    for run in paragraph.runs:
        _force_font(run, pt, family)


_SUPERSCRIPT_MAP = str.maketrans({
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "ˣ": "x", "ᵃ": "a", "ᵇ": "b", "ᶜ": "c", "ᵈ": "d", "ᵉ": "e"
})


# noinspection DuplicatedCode
def _desuperscript_paragraph(paragraph):
    """
    Убирает надстрочное форматирование (x² → x2) в абзаце
    """
    p = paragraph._element
    pPr = p.find(qn("w:pPr"))
    if pPr is not None:
        rPr = pPr.find(qn("w:rPr"))
        if rPr is not None:
            va = rPr.find(qn("w:vertAlign"))
            if va is not None:
                rPr.remove(va)
            va_new = OxmlElement("w:vertAlign")
            va_new.set(qn("w:val"), "baseline")
            rPr.append(va_new)

    for run in paragraph.runs:
        try:
            run.font.superscript = False
            run.font.subscript = False
        except Exception:
            pass

        r = run._element
        rPr = r.find(qn("w:rPr"))
        if rPr is not None:
            va = rPr.find(qn("w:vertAlign"))
            if va is not None:
                rPr.remove(va)

        if run.text:
            run.text = run.text.translate(_SUPERSCRIPT_MAP)


def _replace_in_document(
    doc: DocxDocument,
    mapping: dict,
    preferred_font: Optional[Tuple[str, int]] = None,
):
    for para in doc.paragraphs:
        _replace_in_paragraph(para, mapping, preferred_font=preferred_font)

    def process_table(table):
        for row in table.rows:
            for cell in row.cells:
                for cell_para in cell.paragraphs:
                    _replace_in_paragraph(cell_para, mapping, preferred_font=preferred_font)
                for inner_tbl in cell.tables:
                    process_table(inner_tbl)

    for tbl in doc.tables:
        process_table(tbl)

    for section in doc.sections:
        for header_para in section.header.paragraphs:
            _replace_in_paragraph(header_para, mapping, preferred_font=preferred_font)
        for header_tbl in section.header.tables:
            process_table(header_tbl)
        for footer_para in section.footer.paragraphs:
            _replace_in_paragraph(footer_para, mapping, preferred_font=preferred_font)
        for footer_tbl in section.footer.tables:
            process_table(footer_tbl)


def fill_placeholders(
    doc_path: Path,
    output_path: Path,
    replacements: dict,
    preferred_font: Optional[Tuple[str, int]] = None,
):
    doc = Document(str(doc_path))

    if not PRESERVE_TEMPLATE_FORMAT:
        try:
            normal_style = doc.styles["Normal"]
            normal_style.font.name = "Times New Roman"
            normal_style.font.size = Pt(10)
        except Exception:
            pass

    _replace_in_document(doc, replacements, preferred_font=preferred_font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


def convert_docx_to_pdf(docx_path: Path) -> Path:
    """
    Конвертация DOCX → PDF через LibreOffice (headless).
    Сейчас НЕ используется (PDF отключён), но оставлено для будущего.
    """
    out_dir = docx_path.parent
    cmd = [
        "soffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(out_dir),
        str(docx_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return docx_path.with_suffix(".pdf")


# noinspection SpellCheckingInspection,PyPep8Naming
def generate_contract_and_schedule(data: dict, out_dir: Path):
    """
    Формирует два готовых docx:
    1) Договор (templates/murabaha_template.docx)
    2) График (templates/murabaha_schedule.docx)
    Имена файлов используют data['contract_number'].
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    contract_template = TEMPLATE_CONTRACT
    schedule_template = TEMPLATE_SCHEDULE

    safe_number = str(data["contract_number"]).replace("/", "_")
    contract_out = out_dir / f"dogovor_{safe_number}.docx"
    schedule_out = out_dir / f"schedule_{safe_number}.docx"

    fill_placeholders(contract_template, contract_out, data)
    fill_placeholders(schedule_template, schedule_out, data)

    return contract_out, schedule_out


def generate_istisna_documents(data: dict, out_dir: Path):
    """
    Формирует единый docx по Истисна (3 страницы в одном файле).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_number = str(data["contract_number"]).replace("/", "_")
    out = out_dir / f"istisna_{safe_number}.docx"
    fill_placeholders(ISTISNA_TEMPLATE, out, data, preferred_font=("Aptos", 11))

    # Post-process Istisna document: clean highlight and fit item rows count.
    doc = Document(str(out))
    for para in doc.paragraphs:
        if "Стоимость доставки Товара не включена в стоимость настоящего Договора." in (para.text or ""):
            for run in para.runs:
                run.font.highlight_color = None
                run.font.color.rgb = None

    item_qty = int(data.get("{{item_qty}}", 1) or 1)
    if item_qty < 1:
        item_qty = 1
    spec_table = None
    for table in doc.tables:
        if table.rows and "НАИМЕНОВАНИЕ ТОВАРА" in " | ".join(c.text for c in table.rows[0].cells):
            spec_table = table
            break

    if spec_table is not None and len(spec_table.rows) >= 3:
        total_idx = None
        for i, row in enumerate(spec_table.rows):
            if "Итого:" in " ".join(c.text for c in row.cells):
                total_idx = i
                break
        if total_idx is not None and total_idx > 1:
            item_start = 1
            existing_items = total_idx - item_start
            template_row = spec_table.rows[item_start]

            # Expand rows if requested qty is larger than template item rows.
            while existing_items < item_qty:
                new_tr = copy.deepcopy(template_row._tr)
                spec_table._tbl.insert(total_idx, new_tr)
                existing_items += 1
                total_idx += 1

            # Remove extra rows from bottom (keep exactly item_qty rows).
            while existing_items > item_qty:
                drop_idx = item_start + existing_items - 1
                spec_table._tbl.remove(spec_table.rows[drop_idx]._tr)
                existing_items -= 1
                total_idx -= 1

            # Fill item rows to avoid empty cells and keep visible numbering.
            item_name = str(data.get("{{item_name}}", ""))
            item_price = str(data.get("{{item_price}}", ""))
            total_cost = str(data.get("{{total_cost_final}}", ""))
            per_row_qty = "1" if item_qty > 1 else str(item_qty)
            per_row_total = item_price if item_qty > 1 else total_cost
            for n in range(item_qty):
                row = spec_table.rows[item_start + n]
                if len(row.cells) >= 6:
                    row.cells[0].text = str(n + 1)
                    row.cells[1].text = item_name
                    row.cells[2].text = item_name
                    row.cells[3].text = item_price
                    row.cells[4].text = per_row_qty
                    row.cells[5].text = per_row_total

            # Ensure inserted values in table rows are explicitly Aptos 11.
            for n in range(item_qty):
                row = spec_table.rows[item_start + n]
                for cell in row.cells:
                    for para in cell.paragraphs:
                        for run in para.runs:
                            if run.text:
                                _set_run_font(run, "Aptos", 11)

    doc.save(str(out))
    return (out,)