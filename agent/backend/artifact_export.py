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


def markdown_to_html(markdown: str, title: str) -> str:
    body = []
    in_list = False
    in_code = False
    code_lines = []
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code:
                body.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
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
    if in_list:
        body.append("</ul>")
    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{max-width:860px;margin:48px auto;padding:0 24px;color:#172033;font:16px/1.75 system-ui,-apple-system,"Segoe UI",sans-serif}}h1,h2,h3{{line-height:1.3;color:#102a56;margin-top:1.6em}}h1{{border-bottom:2px solid #dce6f8;padding-bottom:.35em}}blockquote{{border-left:4px solid #2f6edb;margin:1em 0;padding:.6em 1em;background:#f5f8fd;color:#46546a}}code{{background:#eef2f8;padding:.1em .3em;border-radius:4px}}pre{{overflow:auto;background:#111827;color:#f8fafc;padding:16px;border-radius:10px}}a{{color:#1456b8}}@media print{{body{{margin:0;max-width:none}}}}</style></head><body>{body}</body></html>""".format(title=html.escape(title), body="\n".join(body))


def _docx_bytes(markdown: str) -> bytes:
    paragraphs = []
    for line in markdown.splitlines():
        text = re.sub(r"^#{1,6}\s+", "", line)
        text = re.sub(r"^[-*]\s+", "• ", text)
        text = re.sub(r"\*\*|`", "", text)
        if not text.strip():
            paragraphs.append("<w:p/>")
            continue
        paragraphs.append(
            "<w:p><w:r><w:rPr><w:rFonts w:eastAsia=\"Microsoft YaHei\"/></w:rPr>"
            f"<w:t xml:space=\"preserve\">{xml_escape(text)}</w:t></w:r></w:p>"
        )
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


def _pdf_bytes(markdown: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    y = 48
    for raw_line in markdown.splitlines():
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
