"""Минимальный рендерер Markdown → HTML для страниц документации.

Покрывает подмножество, используемое в документации planogram3d:
заголовки, списки, таблицы, код-блоки, инлайн-код, жирный/курсив,
ссылки, горизонтальные линии. Без внешних зависимостей.
"""

import html
import re


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", out)
    out = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)",
                 r'<img src="\2" alt="\1">', out)
    out = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)",
                 r'<a href="\2">\1</a>', out)
    return out


_BLOCK_START = re.compile(
    r"^(#{1,4} |[-*] |\d+\. |\||```|-{3,}\s*$|\s*$)")
_NO_MERGE_PREV = re.compile(r"^(#{1,4} |\||```|-{3,}\s*$)")


def _unwrap(lines):
    """Склейка мягких переносов: абзац/пункт списка — одной строкой."""
    merged, fence = [], False
    for line in lines:
        if line.startswith("```"):
            fence = not fence
            merged.append(line)
            continue
        if (not fence and merged and line.strip()
                and not _BLOCK_START.match(line)
                and merged[-1].strip()
                and not merged[-1].startswith("```")
                and not _NO_MERGE_PREV.match(merged[-1])):
            merged[-1] = merged[-1].rstrip() + " " + line.strip()
        else:
            merged.append(line)
    return merged


def md_to_html(md: str) -> str:
    lines = _unwrap(md.split("\n"))
    out, i = [], 0
    in_list = in_table = False

    def close():
        nonlocal in_list, in_table
        if in_list:
            out.append("</ul>")
            in_list = False
        if in_table:
            out.append("</table>")
            in_table = False

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            close()
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(html.escape(lines[i], quote=False))
                i += 1
            out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
        elif re.match(r"^#{1,4} ", line):
            close()
            level = len(line) - len(line.lstrip("#"))
            out.append(f"<h{level}>{_inline(line[level + 1:])}</h{level}>")
        elif re.match(r"^-{3,}\s*$", line):
            close()
            out.append("<hr>")
        elif re.match(r"^\s*([-*]|\d+\.)\s+", line):
            if not in_list:
                close()
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^\s*([-*]|\d+\.)\s+", "", line)
            out.append(f"<li>{_inline(item)}</li>")
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if re.match(r"^\|[\s\-|:]+\|?\s*$", line):
                pass                       # разделитель шапки
            else:
                if not in_table:
                    close()
                    out.append("<table>")
                    in_table = True
                    out.append("<tr>" + "".join(
                        f"<th>{_inline(c)}</th>" for c in cells) + "</tr>")
                else:
                    out.append("<tr>" + "".join(
                        f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
        elif line.strip() == "":
            close()
        else:
            close()
            out.append(f"<p>{_inline(line)}</p>")
        i += 1
    close()
    return "\n".join(out)
