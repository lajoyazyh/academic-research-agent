"""Portable exports for a research session without persisting credentials."""
from __future__ import annotations

import html
import io
import json
import re
import textwrap
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape


SUPPORTED_FORMATS = {"md", "html", "txt", "json", "docx", "pdf", "zip"}


def safe_slug(value: str) -> str:
    value = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", value or "research-output", flags=re.UNICODE)
    return value.strip("-")[:80] or "research-output"


def collect_artifacts(session: dict) -> dict:
    papers = session.get("papers") or []
    repositories = session.get("repositories") or []
    analysis = session.get("analysis") or {}
    return {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "session_id": session.get("session_id", ""),
        "topic": session.get("topic", ""),
        "review": session.get("review") or session.get("draft") or "",
        "review_quality": session.get("review_quality") or {},
        "notes": session.get("notes") or "",
        "analysis": analysis.get("document") if isinstance(analysis, dict) else analysis,
        "plan": session.get("initial_plan") or "",
        "keywords": session.get("keywords") or [],
        "papers": [
            {
                key: paper.get(key)
                for key in ("paper_id", "title", "authors", "year", "doi", "url", "status", "source", "notes")
                if paper.get(key) not in (None, "")
            }
            for paper in papers
        ],
        "repositories": [
            {
                key: repo.get(key)
                for key in ("full_name", "html_url", "description", "default_branch", "report", "files")
                if repo.get(key) not in (None, "")
            }
            for repo in repositories
        ],
    }


def artifact_markdown(data: dict, include_all: bool = True) -> str:
    title = data.get("topic") or "研究产物"
    parts = [f"# {title}"]
    review = str(data.get("review") or "").strip()
    if review:
        parts.append(review)
    else:
        parts.append("> 当前项目尚未生成综述。")
    if include_all:
        if str(data.get("analysis") or "").strip():
            parts.extend(["# 综合分析", str(data["analysis"]).strip()])
        if str(data.get("notes") or "").strip():
            parts.extend(["# 调研笔记", str(data["notes"]).strip()])
        if str(data.get("plan") or "").strip():
            parts.extend(["# 研究计划", str(data["plan"]).strip()])
        repos = data.get("repositories") or []
        if repos:
            lines = ["# GitHub 仓库来源"]
            for repo in repos:
                lines.append(f"- [{repo.get('full_name', 'repository')}]({repo.get('html_url', '')})")
            parts.append("\n".join(lines))
    return "\n\n".join(part for part in parts if part).strip() + "\n"


def _inline_markdown(value: str) -> str:
    escaped = html.escape(value)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def _table_cells(line: str) -> list[str]:
    return [
        item.strip().replace("\\|", "|")
        for item in line.strip().strip("|").split("|")
    ]


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return len(cells) >= 2 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _mermaid_labels(code: str) -> list[str]:
    labels = []
    for value in re.findall(r'\["([^"]+)"\]', code):
        cleaned = re.sub(r"\s+", " ", value).strip()
        if cleaned and cleaned not in labels:
            labels.append(cleaned)
    return labels


def markdown_to_html(markdown: str, title: str) -> str:
    body = []
    in_list = False
    in_code = False
    code_lines = []
    code_language = ""
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code:
                code = "\n".join(code_lines)
                if code_language.lower() == "mermaid":
                    labels = _mermaid_labels(code)
                    body.append(
                        '<figure class="concept-flow"><figcaption>Conceptual flow</figcaption>'
                        + "<ol>"
                        + "".join(f"<li>{html.escape(label)}</li>" for label in labels)
                        + "</ol><details><summary>Mermaid source</summary><pre><code>"
                        + html.escape(code)
                        + "</code></pre></details></figure>"
                    )
                else:
                    body.append("<pre><code>" + html.escape(code) + "</code></pre>")
                code_lines = []
                code_language = ""
            else:
                code_language = line.removeprefix("```").strip()
            in_code = not in_code
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if (
            line.strip().startswith("|")
            and index + 1 < len(lines)
            and _is_table_separator(lines[index + 1])
        ):
            headers = _table_cells(line)
            index += 2
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(_table_cells(lines[index]))
                index += 1
            body.append("<div class=\"table-wrap\"><table><thead><tr>")
            body.extend(f"<th>{_inline_markdown(cell)}</th>" for cell in headers)
            body.append("</tr></thead><tbody>")
            for row in rows:
                body.append("<tr>")
                body.extend(f"<td>{_inline_markdown(cell)}</td>" for cell in row)
                body.append("</tr>")
            body.append("</tbody></table></div>")
            continue
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            if in_list:
                body.append("</ul>")
                in_list = False
            level = len(match.group(1))
            body.append(f"<h{level}>{_inline_markdown(match.group(2))}</h{level}>")
        elif re.match(r"^[-*]\s+", line):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append("<li>" + _inline_markdown(re.sub(r"^[-*]\s+", "", line)) + "</li>")
        elif line.startswith(">"):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append("<blockquote>" + _inline_markdown(line.lstrip("> ")) + "</blockquote>")
        elif line.strip():
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append("<p>" + _inline_markdown(line) + "</p>")
        index += 1
    if in_list:
        body.append("</ul>")
    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{max-width:1060px;margin:48px auto;padding:0 24px;color:#172033;font:16px/1.75 system-ui,-apple-system,"Segoe UI",sans-serif}}h1,h2,h3{{line-height:1.3;color:#102a56;margin-top:1.6em}}h1{{border-bottom:2px solid #dce6f8;padding-bottom:.35em}}blockquote{{border-left:4px solid #2f6edb;margin:1em 0;padding:.6em 1em;background:#f5f8fd;color:#46546a}}code{{background:#eef2f8;padding:.1em .3em;border-radius:4px}}pre{{overflow:auto;background:#111827;color:#f8fafc;padding:16px;border-radius:10px}}a{{color:#1456b8}}.table-wrap{{overflow:auto;margin:1.2em 0}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{border:1px solid #cbd5e1;padding:8px 10px;vertical-align:top}}th{{background:#eef4ff;text-align:left}}.concept-flow{{margin:1.2em 0;padding:16px;border:1px solid #cbd5e1;border-radius:12px}}.concept-flow ol{{display:flex;flex-wrap:wrap;gap:10px;list-style:none;padding:0}}.concept-flow li{{padding:8px 12px;background:#eef4ff;border-radius:999px}}.concept-flow li+li:before{{content:"→";margin-right:10px;color:#2f6edb}}@media print{{body{{margin:0;max-width:none}}.table-wrap{{overflow:visible}}}}</style></head><body>{body}</body></html>""".format(title=html.escape(title), body="\n".join(body))


def _docx_bytes(markdown: str) -> bytes:
    paragraphs = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if (
            line.strip().startswith("|")
            and index + 1 < len(lines)
            and _is_table_separator(lines[index + 1])
        ):
            rows = [_table_cells(line)]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(_table_cells(lines[index]))
                index += 1
            table_rows = []
            for row_index, row in enumerate(rows):
                cells = []
                for cell in row:
                    bold = "<w:b/>" if row_index == 0 else ""
                    cells.append(
                        "<w:tc><w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/></w:tcPr>"
                        "<w:p><w:r><w:rPr>"
                        f"<w:rFonts w:eastAsia=\"Microsoft YaHei\"/>{bold}</w:rPr>"
                        f"<w:t>{xml_escape(cell)}</w:t></w:r></w:p></w:tc>"
                    )
                table_rows.append("<w:tr>" + "".join(cells) + "</w:tr>")
            paragraphs.append(
                "<w:tbl><w:tblPr><w:tblBorders>"
                "<w:top w:val=\"single\" w:sz=\"4\"/><w:left w:val=\"single\" w:sz=\"4\"/>"
                "<w:bottom w:val=\"single\" w:sz=\"4\"/><w:right w:val=\"single\" w:sz=\"4\"/>"
                "<w:insideH w:val=\"single\" w:sz=\"4\"/><w:insideV w:val=\"single\" w:sz=\"4\"/>"
                "</w:tblBorders></w:tblPr>" + "".join(table_rows) + "</w:tbl>"
            )
            continue
        if line.startswith("```mermaid"):
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                code_lines.append(lines[index])
                index += 1
            labels = _mermaid_labels("\n".join(code_lines))
            flow = " → ".join(labels) or "Conceptual flow (see Mermaid source in Markdown export)"
            paragraphs.append(
                "<w:p><w:r><w:rPr><w:b/><w:rFonts w:eastAsia=\"Microsoft YaHei\"/></w:rPr>"
                f"<w:t xml:space=\"preserve\">{xml_escape(flow)}</w:t></w:r></w:p>"
            )
            index += 1
            continue
        text = re.sub(r"^#{1,6}\s+", "", line)
        text = re.sub(r"^[-*]\s+", "• ", text)
        text = re.sub(r"\*\*|`", "", text)
        if not text.strip():
            paragraphs.append("<w:p/>")
            index += 1
            continue
        paragraphs.append(
            "<w:p><w:r><w:rPr><w:rFonts w:eastAsia=\"Microsoft YaHei\"/></w:rPr>"
            f"<w:t xml:space=\"preserve\">{xml_escape(text)}</w:t></w:r></w:p>"
        )
        index += 1
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{paragraphs}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>""".format(paragraphs="".join(paragraphs))
    content_types = """<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
    return output.getvalue()


def _pdf_bytes_legacy(markdown: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    y = 48
    source_lines = markdown.splitlines()
    printable = []
    index = 0
    while index < len(source_lines):
        line = source_lines[index]
        if (
            line.strip().startswith("|")
            and index + 1 < len(source_lines)
            and _is_table_separator(source_lines[index + 1])
        ):
            printable.append("TABLE")
            printable.append("  |  ".join(_table_cells(line)))
            index += 2
            while index < len(source_lines) and source_lines[index].strip().startswith("|"):
                printable.append("  |  ".join(_table_cells(source_lines[index])))
                index += 1
            continue
        if line.startswith("```mermaid"):
            code_lines = []
            index += 1
            while index < len(source_lines) and not source_lines[index].startswith("```"):
                code_lines.append(source_lines[index])
                index += 1
            printable.append("CONCEPTUAL FLOW: " + " → ".join(_mermaid_labels("\n".join(code_lines))))
            index += 1
            continue
        printable.append(line)
        index += 1
    for raw_line in printable:
        clean = re.sub(r"^#{1,6}\s+", "", raw_line)
        clean = re.sub(r"\*\*|`", "", clean)
        wrapped = textwrap.wrap(clean, width=46, replace_whitespace=False, drop_whitespace=False) or [""]
        for line in wrapped:
            if y > 800:
                page = document.new_page()
                y = 48
            page.insert_text((48, y), line, fontsize=10.5, fontname="china-s", color=(0.08, 0.12, 0.2))
            y += 16
        y += 4
    return document.tobytes(garbage=4, deflate=True)


def _pdf_bytes(markdown: str) -> bytes:
    """Render Markdown as a paginated, table-aware academic PDF."""
    from pathlib import Path

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        KeepTogether,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    regular_candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    bold_candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    if "ResearchSans" not in pdfmetrics.getRegisteredFontNames():
        regular = next((path for path in regular_candidates if path.exists()), None)
        if regular:
            pdfmetrics.registerFont(TTFont("ResearchSans", str(regular)))
    if "ResearchSansBold" not in pdfmetrics.getRegisteredFontNames():
        bold = next((path for path in bold_candidates if path.exists()), None)
        if bold:
            pdfmetrics.registerFont(TTFont("ResearchSansBold", str(bold)))
    if "ResearchSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    body_font = (
        "ResearchSans"
        if "ResearchSans" in pdfmetrics.getRegisteredFontNames()
        else "STSong-Light"
    )
    bold_font = (
        "ResearchSansBold"
        if "ResearchSansBold" in pdfmetrics.getRegisteredFontNames()
        else body_font
    )

    stylesheet = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "ResearchBody",
        parent=stylesheet["BodyText"],
        fontName=body_font,
        fontSize=9.2,
        leading=15,
        textColor=colors.HexColor("#172033"),
        spaceAfter=5,
        wordWrap="CJK",
        splitLongWords=True,
    )
    styles = {
        "body": body_style,
        "quote": ParagraphStyle(
            "ResearchQuote",
            parent=body_style,
            leftIndent=9,
            rightIndent=6,
            borderColor=colors.HexColor("#2F6EDB"),
            borderWidth=2,
            borderPadding=7,
            backColor=colors.HexColor("#F4F7FC"),
            textColor=colors.HexColor("#42526A"),
            spaceBefore=4,
            spaceAfter=10,
        ),
        "bullet": ParagraphStyle(
            "ResearchBullet",
            parent=body_style,
            leftIndent=14,
            firstLineIndent=-8,
            bulletIndent=4,
        ),
        "code": ParagraphStyle(
            "ResearchCode",
            parent=body_style,
            fontSize=8,
            leading=12,
            leftIndent=8,
            rightIndent=8,
            borderPadding=6,
            backColor=colors.HexColor("#F1F5F9"),
        ),
    }
    heading_sizes = {1: 20, 2: 14, 3: 11.5, 4: 10.5, 5: 10, 6: 9.5}
    for level, size in heading_sizes.items():
        styles[f"h{level}"] = ParagraphStyle(
            f"ResearchHeading{level}",
            parent=body_style,
            fontName=bold_font,
            fontSize=size,
            leading=size * 1.45,
            textColor=colors.HexColor("#102A56"),
            spaceBefore=14 if level <= 2 else 9,
            spaceAfter=7,
            keepWithNext=True,
        )

    def inline(value: str) -> str:
        value = html.escape(value)
        value = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', value)
        value = re.sub(
            r"\*\*([^*]+)\*\*",
            rf'<font name="{bold_font}">\1</font>',
            value,
        )
        value = re.sub(
            r"\[([^\]]+)\]\((https?://[^)]+)\)",
            r'<link href="\2" color="#1456B8">\1</link>',
            value,
        )
        return value

    output = io.BytesIO()
    page_width, page_height = A4
    left = right = 18 * mm
    top = 19 * mm
    bottom = 18 * mm
    frame = Frame(
        left,
        bottom,
        page_width - left - right,
        page_height - top - bottom,
        id="research-frame",
    )

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D7DFEA"))
        canvas.line(left, 13 * mm, page_width - right, 13 * mm)
        canvas.setFont(body_font, 7.5)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(left, 8.5 * mm, "Academic Research Agent · Evidence Review")
        canvas.drawRightString(page_width - right, 8.5 * mm, f"{document.page}")
        canvas.restoreState()

    document = BaseDocTemplate(
        output,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title="Academic Research Agent Evidence Review",
        author="Academic Research Agent",
    )
    document.addPageTemplates(
        [PageTemplate(id="research", frames=[frame], onPage=footer)]
    )

    story = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index].rstrip()
        stripped = raw.strip()
        if (
            stripped.startswith("|")
            and index + 1 < len(lines)
            and _is_table_separator(lines[index + 1])
        ):
            table_rows = [_table_cells(raw)]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_rows.append(_table_cells(lines[index]))
                index += 1
            column_count = max(len(row) for row in table_rows)
            available = page_width - left - right
            column_widths = [available / column_count] * column_count
            cell_style = ParagraphStyle(
                "ResearchTableCell",
                parent=body_style,
                fontSize=6.5 if column_count >= 6 else 7.3,
                leading=9 if column_count >= 6 else 10.5,
                spaceAfter=0,
            )
            header_style = ParagraphStyle(
                "ResearchTableHeader",
                parent=cell_style,
                fontName=bold_font,
                textColor=colors.HexColor("#102A56"),
            )
            formatted = []
            for row_index, row in enumerate(table_rows):
                padded = row + [""] * (column_count - len(row))
                formatted.append(
                    [
                        Paragraph(
                            inline(cell),
                            header_style if row_index == 0 else cell_style,
                        )
                        for cell in padded
                    ]
                )
            table = Table(
                formatted,
                colWidths=column_widths,
                repeatRows=1,
                hAlign="LEFT",
                splitByRow=True,
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1FC")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#102A56")),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#BCC9DA")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#F8FAFD")],
                        ),
                    ]
                )
            )
            story.extend([table, Spacer(1, 7)])
            continue
        if stripped.startswith("```"):
            language = stripped.removeprefix("```").strip().lower()
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += 1
            code = "\n".join(code_lines)
            if language == "mermaid":
                labels = _mermaid_labels(code)
                if labels:
                    cells = []
                    for cell_index, label in enumerate(labels):
                        if cell_index:
                            cells.append(
                                Paragraph(
                                    "→",
                                    ParagraphStyle(
                                        "ResearchFlowArrow",
                                        parent=body_style,
                                        fontName=bold_font,
                                        fontSize=12,
                                        alignment=TA_CENTER,
                                        textColor=colors.HexColor("#2F6EDB"),
                                    ),
                                )
                            )
                        cells.append(
                            Paragraph(
                                inline(label),
                                ParagraphStyle(
                                    "ResearchFlowNode",
                                    parent=body_style,
                                    fontName=bold_font,
                                    fontSize=7.3,
                                    leading=10,
                                    alignment=TA_CENTER,
                                    textColor=colors.HexColor("#102A56"),
                                ),
                            )
                        )
                    node_count = len(labels)
                    arrow_count = max(node_count - 1, 0)
                    arrow_width = 8 * mm
                    node_width = (
                        page_width
                        - left
                        - right
                        - arrow_count * arrow_width
                    ) / node_count
                    widths = [
                        arrow_width if cell_index % 2 else node_width
                        for cell_index in range(len(cells))
                    ]
                    flow = Table([cells], colWidths=widths, hAlign="LEFT")
                    flow.setStyle(
                        TableStyle(
                            [
                                (
                                    "BACKGROUND",
                                    (0, 0),
                                    (-1, 0),
                                    colors.HexColor("#F4F7FC"),
                                ),
                                (
                                    "BOX",
                                    (0, 0),
                                    (-1, 0),
                                    0.6,
                                    colors.HexColor("#B9C8DF"),
                                ),
                                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                                ("TOPPADDING", (0, 0), (-1, 0), 8),
                                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                                ("LEFTPADDING", (0, 0), (-1, 0), 4),
                                ("RIGHTPADDING", (0, 0), (-1, 0), 4),
                            ]
                        )
                    )
                    story.extend([KeepTogether(flow), Spacer(1, 8)])
            else:
                story.append(
                    Paragraph(
                        inline(code).replace("\n", "<br/>"),
                        styles["code"],
                    )
                )
            continue
        if not stripped:
            story.append(Spacer(1, 3))
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", raw)
        if heading:
            level = len(heading.group(1))
            story.append(Paragraph(inline(heading.group(2)), styles[f"h{level}"]))
        elif stripped.startswith(">"):
            story.append(
                Paragraph(inline(stripped.lstrip("> ")), styles["quote"])
            )
        elif re.match(r"^[-*]\s+", stripped):
            text = re.sub(r"^[-*]\s+", "", stripped)
            story.append(
                Paragraph(inline(text), styles["bullet"], bulletText="•")
            )
        elif re.match(r"^\d+\.\s+", stripped):
            text = re.sub(r"^\d+\.\s+", "", stripped)
            story.append(
                Paragraph(inline(text), styles["bullet"], bulletText="•")
            )
        else:
            story.append(Paragraph(inline(stripped), styles["body"]))
        index += 1

    document.build(story)
    return output.getvalue()


def render_export(data: dict, export_format: str, include_all: bool = True) -> tuple[bytes, str, str]:
    export_format = export_format.lower().strip()
    if export_format not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的导出格式：{export_format}")
    slug = safe_slug(data.get("topic") or "research-output")
    markdown = artifact_markdown(data, include_all=include_all)
    if export_format == "md":
        return markdown.encode("utf-8"), "text/markdown; charset=utf-8", f"{slug}.md"
    if export_format == "txt":
        plain = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", markdown)
        plain = re.sub(r"(?m)^#{1,6}\s+|\*\*|`", "", plain)
        return plain.encode("utf-8"), "text/plain; charset=utf-8", f"{slug}.txt"
    if export_format == "html":
        rendered = markdown_to_html(markdown, data.get("topic") or "研究产物")
        return rendered.encode("utf-8"), "text/html; charset=utf-8", f"{slug}.html"
    if export_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), "application/json", f"{slug}.json"
    if export_format == "docx":
        return _docx_bytes(markdown), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"{slug}.docx"
    if export_format == "pdf":
        return _pdf_bytes(markdown), "application/pdf", f"{slug}.pdf"

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for fmt in ("md", "html", "txt", "json"):
            payload, _, name = render_export(data, fmt, include_all=include_all)
            archive.writestr(name, payload)
    return output.getvalue(), "application/zip", f"{slug}-research-package.zip"
