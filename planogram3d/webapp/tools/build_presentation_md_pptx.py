"""Сборка docs/presentation_md.pptx — новой презентации на румынском языке
(язык страны, файл для показа заказчику).

Почему отдельный скрипт и отдельный файл: владелец решил новую
презентацию делать рядом со старой (`docs/presentation.pptx`), не трогая
её; см. задачу и `docs/HANDOFF.md`. Текст берём из того же каталога
переводов (`webapp/i18n.py`, ключи `p2.*`), которым пользуется HTML-версия
`/presentation2` — так формулировки не расходятся между HTML и pptx.

Запуск::

    .venv-planogram3d/bin/python -m planogram3d.webapp.tools.build_presentation_md_pptx

Скриншоты должны быть заранее сняты с реально работающей системы (см.
`docs/HANDOFF.md` §5) и лежать в `docs/img/md/` — заглушек не используем
(явное требование задачи). Если скриншот отсутствует, слайд собирается
без картинки, а не падает: RuntimeError не бросаем, чтобы не рассыпать
всю презентацию из-за одного не снятого кадра, но список пропущенных
картинок печатаем в конце для контроля.
"""

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

from ..i18n import t

LANG = "ro"  # презентация для заказчика — на румынском

ROOT = Path(__file__).resolve().parent.parent.parent  # planogram3d/
IMG = ROOT / "docs" / "img" / "md"
OUT = ROOT / "docs" / "presentation_md.pptx"

NAVY = RGBColor(0x1D, 0x2B, 0x3A)
NAVY2 = RGBColor(0x2F, 0x4B, 0x68)
BLUE = RGBColor(0x2F, 0x6F, 0xED)
GOLD = RGBColor(0xFF, 0xD5, 0x4F)
INK = RGBColor(0x23, 0x30, 0x3F)
MUTED = RGBColor(0x5B, 0x66, 0x72)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xF4, 0xF6, 0xF9)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

_missing_images = []


def _(key: str) -> str:
    """Короткая обёртка над t(лгано) для румынского текста презентации."""
    return t(LANG, key)


def _new_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs


def _blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])  # пустой layout


def _bg(slide, color: RGBColor):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def _text(slide, left, top, width, height, text, size=18, bold=False,
          color=INK, align=PP_ALIGN.LEFT, font="Calibri", italic=False,
          anchor=MSO_ANCHOR.TOP, line_spacing=1.15):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = line_spacing
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = font
    return box


def _bullets(slide, left, top, width, height, items, size=15, color=INK,
             gap_after=8, font="Calibri"):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "•  " + item
        p.font.size = Pt(size)
        p.font.color.rgb = color
        p.font.name = font
        p.line_spacing = 1.2
        p.space_after = Pt(gap_after)
    return box


def _image(slide, name, left, top, width=None, height=None):
    path = IMG / name
    if not path.exists():
        _missing_images.append(name)
        # рамка-заглушка с подписью — видно, что скриншот не найден,
        # а не падает вся сборка
        box = slide.shapes.add_shape(1, left, top, width or Inches(4),
                                      height or Inches(2.5))
        box.fill.solid()
        box.fill.fore_color.rgb = LIGHT
        box.line.color.rgb = MUTED
        tf = box.text_frame
        tf.text = f"[missing: {name}]"
        return box
    kwargs = {}
    if width is not None:
        kwargs["width"] = width
    if height is not None:
        kwargs["height"] = height
    return slide.shapes.add_picture(str(path), left, top, **kwargs)


def _footer(slide, n, total):
    _text(slide, Inches(11.9), Inches(7.05), Inches(1.2), Inches(0.35),
          f"{n} / {total}", size=10, color=MUTED, align=PP_ALIGN.RIGHT)


def build() -> Presentation:
    prs = _new_deck()
    total = 14

    # 1. Титул -----------------------------------------------------------
    s = _blank(prs); _bg(s, NAVY)
    _text(s, Inches(0.8), Inches(2.1), Inches(11.5), Inches(1.2),
          "planogram3d", size=54, bold=True, color=WHITE, font="Cambria")
    _text(s, Inches(0.8), Inches(3.15), Inches(11.7), Inches(1.0),
          _("p2.s1.tag"), size=20, color=GOLD)
    _text(s, Inches(0.8), Inches(4.15), Inches(11.5), Inches(2.6),
          _("p2.s1.desc"), size=14, color=RGBColor(0xC8, 0xD4, 0xE2))
    _footer(s, 1, total)

    # 2. Возможности -------------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.7),
          _("p2.s2.title"), size=28, bold=True, color=INK, font="Cambria")
    cards = [
        (_("p2.s2.c1.title"), _("p2.s2.c1.desc")),
        (_("p2.s2.c2.title"), _("p2.s2.c2.desc")),
        (_("p2.s2.c3.title"), _("p2.s2.c3.desc")),
        (_("p2.s2.c4.title"), _("p2.s2.c4.desc")),
        (_("p2.s2.c5.title"), _("p2.s2.c5.desc")),
        (_("p2.s2.c6.title"), _("p2.s2.c6.desc")),
    ]
    cw, ch, gap = Inches(3.95), Inches(2.6), Inches(0.25)
    for i, (title, desc) in enumerate(cards):
        col, row = i % 3, i // 3
        left = Inches(0.55) + col * (cw + gap)
        top = Inches(1.3) + row * (ch + gap)
        box = s.shapes.add_shape(1, left, top, cw, ch)
        box.fill.solid(); box.fill.fore_color.rgb = LIGHT
        box.line.color.rgb = RGBColor(0xDF, 0xE6, 0xEE)
        tf = box.text_frame; tf.word_wrap = True
        tf.margin_left = Pt(12); tf.margin_top = Pt(10)
        p0 = tf.paragraphs[0]
        p0.text = title; p0.font.size = Pt(16); p0.font.bold = True
        p0.font.color.rgb = INK
        p1 = tf.add_paragraph()
        p1.text = desc; p1.font.size = Pt(11.5); p1.font.color.rgb = MUTED
        p1.space_before = Pt(6); p1.line_spacing = 1.2
    _footer(s, 2, total)

    # 3. Архитектура -------------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.7),
          _("p2.s3.title"), size=26, bold=True, color=INK, font="Cambria")
    boxes = [
        (_("p2.s3.box1.title"), _("p2.s3.box1.desc"), NAVY),
        (_("p2.s3.box2.title"), _("p2.s3.box2.desc"), NAVY2),
        (_("p2.s3.box3.title"), _("p2.s3.box3.desc"), BLUE),
    ]
    bw, bh, bgap = Inches(3.9), Inches(2.2), Inches(0.3)
    for i, (title, desc, color) in enumerate(boxes):
        left = Inches(0.55) + i * (bw + bgap)
        box = s.shapes.add_shape(1, left, Inches(1.3), bw, bh)
        box.fill.solid(); box.fill.fore_color.rgb = color
        box.line.fill.background()
        tf = box.text_frame; tf.word_wrap = True
        tf.margin_left = Pt(12); tf.margin_top = Pt(10)
        p0 = tf.paragraphs[0]
        p0.text = title; p0.font.size = Pt(15); p0.font.bold = True
        p0.font.color.rgb = WHITE
        p1 = tf.add_paragraph()
        p1.text = desc; p1.font.size = Pt(11); p1.font.color.rgb = RGBColor(
            0xDC, 0xE6, 0xF2)
        p1.space_before = Pt(6); p1.line_spacing = 1.2
    box = s.shapes.add_shape(1, Inches(0.55), Inches(3.9), Inches(11.9),
                              Inches(2.6))
    box.fill.solid(); box.fill.fore_color.rgb = LIGHT
    box.line.color.rgb = RGBColor(0xDF, 0xE6, 0xEE)
    tf = box.text_frame; tf.word_wrap = True
    tf.margin_left = Pt(14); tf.margin_top = Pt(12)
    p0 = tf.paragraphs[0]
    p0.text = _("p2.s3.card.title"); p0.font.size = Pt(17); p0.font.bold = True
    p0.font.color.rgb = INK
    p1 = tf.add_paragraph()
    p1.text = _("p2.s3.card.desc"); p1.font.size = Pt(13); p1.font.color.rgb = MUTED
    p1.space_before = Pt(8); p1.line_spacing = 1.3
    _footer(s, 3, total)

    # 4. 3D-планограмма ------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.7),
          _("p2.s4.title"), size=25, bold=True, color=INK, font="Cambria")
    _bullets(s, Inches(0.6), Inches(1.25), Inches(6.6), Inches(5.8), [
        _("p2.s4.li1"), _("p2.s4.li2"), _("p2.s4.li3"),
        _("p2.s4.li4"), _("p2.s4.li5"), _("p2.s4.li6"),
    ])
    _image(s, "planogram_ro.png", Inches(7.4), Inches(1.25), width=Inches(5.4))
    _footer(s, 4, total)

    # 5. Соответствие ----------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.7),
          _("p2.s5.title"), size=25, bold=True, color=INK, font="Cambria")
    _bullets(s, Inches(0.6), Inches(1.25), Inches(8.4), Inches(5.5), [
        _("p2.s5.li1"), _("p2.s5.li2"), _("p2.s5.li3"),
        _("p2.s5.li4"), _("p2.s5.li5"),
    ])
    _text(s, Inches(9.4), Inches(1.4), Inches(3.3), Inches(2.0), "16",
          size=64, bold=True, color=GOLD, align=PP_ALIGN.CENTER)
    _text(s, Inches(9.4), Inches(2.75), Inches(3.3), Inches(1.0),
          "încălcări găsite de\nmagazinul demo (6 critice)",
          size=13, color=MUTED, align=PP_ALIGN.CENTER)
    _footer(s, 5, total)

    # 6. Карта сети --------------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.7),
          _("p2.s6.title"), size=23, bold=True, color=INK, font="Cambria")
    _bullets(s, Inches(0.6), Inches(1.2), Inches(6.3), Inches(5.8), [
        _("p2.s6.li1"), _("p2.s6.li2"), _("p2.s6.li3"),
        _("p2.s6.li4"), _("p2.s6.li5"),
    ], size=13.5)
    _image(s, "map_ro.png", Inches(7.1), Inches(1.2), width=Inches(5.7))
    _footer(s, 6, total)

    # 7. Симуляция зала ------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.7),
          _("p2.s7.title"), size=23, bold=True, color=INK, font="Cambria")
    _bullets(s, Inches(0.6), Inches(1.2), Inches(6.3), Inches(5.8), [
        _("p2.s7.li1"), _("p2.s7.li2"), _("p2.s7.li3"),
        _("p2.s7.li4"), _("p2.s7.li5"),
    ], size=13.5)
    _image(s, "hall_ro.png", Inches(7.1), Inches(1.2), width=Inches(5.7))
    _footer(s, 7, total)

    # 8. Тренажёр + Roblox -------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.7),
          _("p2.s8.title"), size=24, bold=True, color=INK, font="Cambria")
    _bullets(s, Inches(0.6), Inches(1.25), Inches(11.9), Inches(5.6), [
        _("p2.s8.li1"), _("p2.s8.li2"), _("p2.s8.li3"),
        _("p2.s8.li4"), _("p2.s8.li5"), _("p2.s8.li6"),
    ])
    _footer(s, 8, total)

    # 9. Доставка -----------------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.7),
          _("p2.s9.title"), size=22, bold=True, color=INK, font="Cambria")
    _bullets(s, Inches(0.6), Inches(1.25), Inches(6.3), Inches(5.6), [
        _("p2.s9.li1"), _("p2.s9.li2"), _("p2.s9.li3"),
        _("p2.s9.li4"), _("p2.s9.li5"),
    ], size=13.5)
    _image(s, "delivery_ro.png", Inches(7.1), Inches(1.25), width=Inches(5.7))
    _footer(s, 9, total)

    # 10. ИИ-табло -----------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.55),
          _("p2.s10.title"), size=22, bold=True, color=INK, font="Cambria")
    _text(s, Inches(0.6), Inches(1.0), Inches(11.9), Inches(0.6),
          _("p2.s10.sub"), size=12.5, italic=True, color=MUTED)
    _bullets(s, Inches(0.6), Inches(1.75), Inches(11.9), Inches(5.2), [
        _("p2.s10.li1"), _("p2.s10.li2"), _("p2.s10.li3"),
        _("p2.s10.li4"), _("p2.s10.li5"),
    ])
    _footer(s, 10, total)

    # 11. Топливный контур --------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.3), Inches(12), Inches(0.55),
          _("p2.s11.title"), size=21, bold=True, color=INK, font="Cambria")
    _text(s, Inches(0.6), Inches(0.9), Inches(11.9), Inches(0.6),
          _("p2.s11.sub"), size=12, italic=True, color=MUTED)
    _bullets(s, Inches(0.6), Inches(1.6), Inches(6.3), Inches(5.6), [
        _("p2.s11.li1"), _("p2.s11.li2"), _("p2.s11.li3"),
        _("p2.s11.li4"), _("p2.s11.li5"), _("p2.s11.li6"),
    ], size=12.5)
    _image(s, "fuel_ro.png", Inches(7.1), Inches(1.6), width=Inches(5.7))
    _footer(s, 11, total)

    # 12. Bon fiscal -----------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.3), Inches(12), Inches(0.55),
          _("p2.s12.title"), size=22, bold=True, color=INK, font="Cambria")
    _text(s, Inches(0.6), Inches(0.9), Inches(11.9), Inches(0.6),
          _("p2.s12.sub"), size=12.5, italic=True, color=MUTED)
    _bullets(s, Inches(0.6), Inches(1.6), Inches(7.0), Inches(5.4), [
        _("p2.s12.li1"), _("p2.s12.li2"), _("p2.s12.li3"),
        _("p2.s12.li4"), _("p2.s12.li5"),
    ], size=13)
    _image(s, "receipt_ro.png", Inches(7.9), Inches(1.4), width=Inches(4.7))
    _footer(s, 12, total)

    # 13. Трёхъязычность ------------------------------------------------
    s = _blank(prs); _bg(s, WHITE)
    _text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.6),
          _("p2.s13.title"), size=24, bold=True, color=INK, font="Cambria")
    _text(s, Inches(0.6), Inches(1.0), Inches(11.9), Inches(0.6),
          _("p2.s13.sub"), size=12.5, italic=True, color=MUTED)
    _bullets(s, Inches(0.6), Inches(1.75), Inches(11.9), Inches(5.0), [
        _("p2.s13.li1"), _("p2.s13.li2"), _("p2.s13.li3"),
        _("p2.s13.li4"), _("p2.s13.li5"),
    ])
    _footer(s, 13, total)

    # 14. Итоги ------------------------------------------------------------
    s = _blank(prs); _bg(s, NAVY)
    _text(s, Inches(0.6), Inches(0.5), Inches(12), Inches(0.8),
          _("p2.sf.title"), size=32, bold=True, color=WHITE, font="Cambria")
    stats = [("6", "magazine ale rețelei\ndin Chișinău"),
             ("46", "stații în conturul\nde combustibil"),
             ("3", "limbi ale\ninterfeței"),
             ("1", "obiect Store\npentru toate datele")]
    sw, sh, sgap = Inches(2.75), Inches(1.9), Inches(0.25)
    for i, (num, label) in enumerate(stats):
        left = Inches(0.6) + i * (sw + sgap)
        box = s.shapes.add_shape(1, left, Inches(1.6), sw, sh)
        box.fill.solid(); box.fill.fore_color.rgb = NAVY2
        box.line.fill.background()
        tf = box.text_frame; tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p0 = tf.paragraphs[0]; p0.alignment = PP_ALIGN.CENTER
        p0.text = num; p0.font.size = Pt(40); p0.font.bold = True
        p0.font.color.rgb = GOLD
        p1 = tf.add_paragraph(); p1.alignment = PP_ALIGN.CENTER
        p1.text = label; p1.font.size = Pt(11)
        p1.font.color.rgb = RGBColor(0xC8, 0xD4, 0xE2)
    _text(s, Inches(0.6), Inches(4.0), Inches(11.9), Inches(1.4),
          _("p2.sf.desc"), size=14, color=RGBColor(0xDC, 0xE6, 0xF2))
    _text(s, Inches(0.6), Inches(5.5), Inches(11.9), Inches(1.2),
          _("p2.sf.next"), size=15, bold=True, color=GOLD)
    _footer(s, 14, total)

    return prs


def main() -> None:
    prs = build()
    prs.save(str(OUT))
    print(f"saved {OUT} ({len(prs.slides._sldIdLst)} slides)")
    if _missing_images:
        print("MISSING IMAGES:", ", ".join(_missing_images))


if __name__ == "__main__":
    main()
