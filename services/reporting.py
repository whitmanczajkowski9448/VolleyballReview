from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#071425")
BLUE = colors.HexColor("#0A67C8")
SKY = colors.HexColor("#68D8FF")
MINT = colors.HexColor("#8CF0CB")
LAVENDER = colors.HexColor("#B9A7FF")
LIGHT_BG = colors.HexColor("#F4F8FC")
MID = colors.HexColor("#D9E5F1")
TEXT = colors.HexColor("#13253A")
MUTED = colors.HexColor("#5A6E84")


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def format_seconds(value):
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"


def _p(text, style):
    return Paragraph(escape(clean_text(text)) or "—", style)


def build_challenge_analytics_pdf(
    challenge_rows,
    *,
    report_start,
    report_end,
    conferences,
    statuses,
    summary,
):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.35 * inch,
        leftMargin=0.35 * inch,
        topMargin=0.35 * inch,
        bottomMargin=0.40 * inch,
        title="NCAA WVB Challenge Analytics",
        author="VolleyReview",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "VRTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=23,
        leading=26,
        textColor=NAVY,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    subtitle = ParagraphStyle(
        "VRSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=MUTED,
    )
    section = ParagraphStyle(
        "VRSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=NAVY,
        spaceBefore=7,
        spaceAfter=5,
    )
    cell = ParagraphStyle(
        "VRCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.2,
        leading=7.4,
        textColor=TEXT,
    )
    cell_bold = ParagraphStyle(
        "VRCellBold",
        parent=cell,
        fontName="Helvetica-Bold",
    )
    header_cell = ParagraphStyle(
        "VRHeaderCell",
        parent=cell_bold,
        textColor=colors.white,
    )
    note_style = ParagraphStyle(
        "VRNote",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.4,
        leading=11.5,
        textColor=TEXT,
    )

    story = []
    story.append(Paragraph("NCAA WOMEN'S VOLLEYBALL", subtitle))
    story.append(Paragraph("Challenge Analytics Report", title))
    story.append(Paragraph(
        f"{report_start:%B %d, %Y} – {report_end:%B %d, %Y}  •  "
        f"{', '.join(conferences) if conferences else 'All Conferences'}  •  "
        f"{', '.join(statuses) if statuses else 'All Review Statuses'}",
        subtitle,
    ))
    story.append(Spacer(1, 10))

    kpis = [
        ("Challenges", summary.get("total", 0), SKY),
        ("Complete", summary.get("complete", 0), MINT),
        ("Needs Additional Review", summary.get("needs_review", 0), LAVENDER),
        ("Reversal Rate", f"{summary.get('reversal_rate', 0):.1f}%", SKY),
        ("Avg. Review", format_seconds(summary.get("average_seconds")), MINT),
        ("Incorrect / Unclear", f"{summary.get('incorrect', 0)} / {summary.get('unclear', 0)}", LAVENDER),
    ]
    kpi_table = Table(
        [[
            Paragraph(
                f"<font size='7' color='#5A6E84'>{label.upper()}</font><br/>"
                f"<font size='16'><b>{value}</b></font>",
                styles["Normal"],
            )
            for label, value, _accent in kpis
        ]],
        colWidths=[1.16 * inch] * len(kpis),
    )
    kpi_style = [
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, MID),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, MID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]
    for index, (_label, _value, accent) in enumerate(kpis):
        kpi_style.append(("LINEABOVE", (index, 0), (index, 0), 3, accent))
    kpi_table.setStyle(TableStyle(kpi_style))
    story.append(kpi_table)
    story.append(Spacer(1, 10))

    outcome_rows = [
        ["Confirmed", summary.get("confirmed", 0)],
        ["Reversed", summary.get("reversed", 0)],
        ["Stands", summary.get("stands", 0)],
        ["Mechanical Failure", summary.get("mechanical", 0)],
    ]
    category_counts = summary.get("category_counts", {}) or {}
    category_rows = [[key, value] for key, value in category_counts.items()]

    left = Table(
        [[Paragraph("OUTCOMES", header_cell), Paragraph("COUNT", header_cell)]]
        + [[_p(a, cell), _p(b, cell)] for a, b in outcome_rows],
        colWidths=[1.55 * inch, 0.55 * inch],
    )
    right = Table(
        [[Paragraph("CHALLENGE CATEGORY", header_cell), Paragraph("COUNT", header_cell)]]
        + [[_p(a, cell), _p(b, cell)] for a, b in category_rows],
        colWidths=[2.1 * inch, 0.55 * inch],
    )
    for table in (left, right):
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ("GRID", (0, 0), (-1, -1), 0.35, MID),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

    summary_tables = Table([[left, right]], colWidths=[3.1 * inch, 3.1 * inch])
    summary_tables.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(summary_tables)
    story.append(Spacer(1, 8))

    story.append(Paragraph("All Challenges", section))

    headers = [
        "Date", "Conf", "Match", "Set / Score", "Category", "Original Call",
        "Outcome", "Changed / New Fault", "Judgment", "Length", "Status", "Video",
    ]
    table_data = [[Paragraph(h, header_cell) for h in headers]]

    for row in challenge_rows:
        url = clean_text(row.get("public_url"))
        link = (
            Paragraph(f"<link href='{escape(url, quote=True)}' color='#0A67C8'><u>Open</u></link>", cell)
            if url.startswith(("http://", "https://"))
            else Paragraph("—", cell)
        )
        set_score = " • ".join(
            part for part in [
                f"Set {clean_text(row.get('set_number'))}" if clean_text(row.get('set_number')) else "",
                clean_text(row.get("score")),
            ]
            if part
        )
        table_data.append([
            _p(row.get("match_date"), cell),
            _p(row.get("conference"), cell),
            _p(row.get("match_name"), cell),
            _p(set_score, cell),
            _p(row.get("category"), cell),
            _p(row.get("original_call"), cell),
            _p(row.get("outcome"), cell),
            _p(row.get("outcome_detail"), cell),
            _p(row.get("judgment"), cell),
            _p(format_seconds(row.get("length_seconds")), cell),
            _p(row.get("status"), cell),
            link,
        ])

    widths = [0.55, 0.48, 1.18, 0.62, 0.72, 0.86, 0.62, 0.78, 0.58, 0.45, 0.72, 0.38]
    challenge_table = Table(
        table_data,
        colWidths=[w * inch for w in widths],
        repeatRows=1,
    )
    challenge_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.28, MID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(challenge_table)

    notes = [row for row in challenge_rows if clean_text(row.get("weekly_summary_note"))]
    if notes:
        story.append(PageBreak())
        story.append(Paragraph("Challenges Requiring Coordinator Attention", title))
        story.append(Spacer(1, 6))
        for row in notes:
            heading = (
                f"{clean_text(row.get('match_name')) or 'Challenge'} • "
                f"Set {clean_text(row.get('set_number')) or '—'} • "
                f"{clean_text(row.get('score')) or '—'}"
            )
            link = clean_text(row.get("public_url"))
            pieces = [
                Paragraph(escape(heading), cell_bold),
                Spacer(1, 3),
                Paragraph(escape(clean_text(row.get("weekly_summary_note"))), note_style),
            ]
            if link.startswith(("http://", "https://")):
                pieces.extend([
                    Spacer(1, 4),
                    Paragraph(
                        f"<link href='{escape(link, quote=True)}' color='#0A67C8'><u>Open shared challenge</u></link>",
                        note_style,
                    ),
                ])
            card = Table([[pieces]], colWidths=[7.0 * inch])
            card.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                ("BOX", (0, 0), (-1, -1), 0.6, MID),
                ("LINEBEFORE", (0, 0), (0, -1), 4, BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(KeepTogether([card, Spacer(1, 8)]))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(MID)
        canvas.line(0.35 * inch, 0.28 * inch, 10.65 * inch, 0.28 * inch)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.35 * inch, 0.14 * inch, "VolleyReview • NCAA Women's Volleyball")
        canvas.drawRightString(10.65 * inch, 0.14 * inch, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer.getvalue()
