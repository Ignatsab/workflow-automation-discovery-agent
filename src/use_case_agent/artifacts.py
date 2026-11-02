"""Generate standardized product cards and process diagrams."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from .scoring import score_case


NAVY = "17365D"
PALE_BLUE = "EAF2F8"
PALE_GRAY = "F5F6F7"
GRID = "D9D9D9"


def unwrap(value: Any, default: Any = "Unknown") -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value", default)
    return default if value in (None, "") else value


def evidence(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("evidence", "unknown")
    return "unknown"


def get(record: dict[str, Any], path: str, default: Any = "Unknown") -> Any:
    node: Any = record
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return unwrap(node, default)


def get_fact(record: dict[str, Any], path: str) -> tuple[Any, str, str]:
    node: Any = record
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return "Unknown", "unknown", ""
        node = node[key]
    if not isinstance(node, dict):
        return node, "unknown", ""
    return node.get("value", "Unknown"), node.get("evidence", "unknown"), node.get("notes", "")


def _text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value) if value else "Unknown"
    if isinstance(value, dict):
        return "; ".join(f"{key}: {val}" for key, val in value.items())
    return str(value)


def _set_cell_fill(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_cell_margins(cell, top=100, start=120, bottom=100, end=120) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _set_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = f"w:{edge}"
        node = borders.find(qn(tag))
        if node is None:
            node = OxmlElement(tag)
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:color"), GRID)


def _configure_document(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.72)
    section.right_margin = Inches(0.72)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.08
    for name, size in (("Title", 23), ("Heading 1", 16), ("Heading 2", 12)):
        style = styles[name]
        style.font.name = "Aptos Display" if name != "Normal" else "Aptos"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.bold = name != "Title"
        style.paragraph_format.space_before = Pt(12 if name != "Title" else 0)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.keep_with_next = True
        p_pr = style.element.get_or_add_pPr()
        p_bdr = p_pr.find(qn("w:pBdr"))
        if p_bdr is not None:
            p_pr.remove(p_bdr)


def _add_table(doc: Document, headers: list[str], rows: Iterable[Iterable[Any]], widths: list[float] | None = None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")
    if widths:
        for idx, width in enumerate(widths):
            table.columns[idx].width = Inches(width)
        grid_cols = table._tbl.tblGrid.gridCol_lst
        for idx, width in enumerate(widths):
            grid_cols[idx].set(qn("w:w"), str(int(width * 1440)))
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    for idx, header in enumerate(headers):
        cell = table.rows[0].cells[idx]
        cell.text = header
        _set_cell_fill(cell, NAVY)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for run in cell.paragraphs[0].runs:
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            run.font.size = Pt(9.5)
        if widths:
            cell.width = Inches(widths[idx])
        _set_cell_margins(cell)
    for row_idx, values in enumerate(rows):
        row = table.add_row()
        cant_split = OxmlElement("w:cantSplit")
        row._tr.get_or_add_trPr().append(cant_split)
        cells = row.cells
        for idx, value in enumerate(values):
            cells[idx].text = _text(value)
            cells[idx].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            _set_cell_margins(cells[idx])
            if row_idx % 2:
                _set_cell_fill(cells[idx], PALE_BLUE)
            if widths:
                cells[idx].width = Inches(widths[idx])
            for paragraph in cells[idx].paragraphs:
                paragraph.paragraph_format.space_after = Pt(2)
                for run in paragraph.runs:
                    run.font.size = Pt(9.2)
    _set_table_borders(table)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def _add_fact_table(doc: Document, record: dict[str, Any], fields: list[tuple[str, str]]) -> None:
    rows = []
    for label, path in fields:
        value, level, notes = get_fact(record, path)
        detail = _text(value)
        if notes:
            detail = f"{detail}\nNote: {notes}"
        rows.append((label, detail, level.replace("_", " ").title()))
    _add_table(doc, ["Field", "Recorded information", "Evidence"], rows, [1.55, 4.45, 1.05])


def generate_mermaid(record: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    steps = get(record, "current_state.steps", [])
    if not isinstance(steps, list):
        steps = [steps]
    current_lines = ["flowchart TD", '    A["Trigger"]']
    previous = "A"
    for idx, step in enumerate(steps, 1):
        node = f"S{idx}"
        safe = str(step).replace('"', "'")
        current_lines.append(f'    {node}["{safe}"]')
        current_lines.append(f"    {previous} --> {node}")
        previous = node
    current_lines.extend(['    Z["Outcome"]', f"    {previous} --> Z"])

    boundary = get(record, "target_state.automation_boundary", [])
    if not isinstance(boundary, list):
        boundary = [boundary]
    target_lines = [
        "flowchart TD",
        '    A["Request received"] --> V["Validate required inputs"]',
        '    V -->|Incomplete| H["Human follow up"]',
        '    V -->|Complete| C["Apply deterministic controls"]',
    ]
    previous = "C"
    for idx, step in enumerate(boundary, 1):
        node = f"T{idx}"
        safe = str(step).replace('"', "'")
        target_lines.append(f'    {node}["{safe}"]')
        target_lines.append(f"    {previous} --> {node}")
        previous = node
    target_lines.extend(
        [
            '    R["Human review and approval"]',
            f"    {previous} --> R",
            '    R --> O["Record outcome and audit evidence"]',
            '    R -->|Rejected or low confidence| F["Fallback to current process"]',
        ]
    )
    current_path = out / "current_state.mmd"
    target_path = out / "proposed_state.mmd"
    current_path.write_text("\n".join(current_lines) + "\n", encoding="utf-8")
    target_path.write_text("\n".join(target_lines) + "\n", encoding="utf-8")
    return current_path, target_path


def generate_product_card(record: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    score = score_case(record)
    doc = Document()
    _configure_document(doc)

    title = doc.add_paragraph(style="Title")
    title.add_run("Workflow Automation Product Card")
    title_pr = title._p.get_or_add_pPr()
    title_bdr = title_pr.find(qn("w:pBdr"))
    if title_bdr is not None:
        title_pr.remove(title_bdr)
    intro = doc.add_paragraph()
    intro.add_run(f"Case {record.get('case_id', 'Unknown')}  ").bold = True
    intro.add_run(f"Generated {date.today().isoformat()}  |  Schema {record.get('schema_version', 'Unknown')}  |  Score model {score.score_version}")
    doc.add_paragraph(
        "This document summarizes the evidence collected for an automation opportunity. It is a discovery output, not an approval to build, access data, or automate decisions. Unknowns and assumptions remain visible for review."
    )

    doc.add_heading("Decision Summary", level=1)
    _add_table(
        doc,
        ["Adjusted score", "Confidence", "Recommendation", "Current blockers"],
        [[f"{score.adjusted_score:.1f} of 100", f"{score.confidence:.0%}", score.recommendation, score.blockers or "None"]],
        [1.05, 0.9, 2.55, 2.55],
    )

    doc.add_heading("Opportunity Definition", level=1)
    _add_fact_table(
        doc,
        record,
        [
            ("Problem", "summary.problem_statement"),
            ("Goal", "summary.goal"),
            ("Process owner", "ownership.process_owner"),
            ("Requesting unit", "ownership.requesting_unit"),
        ],
    )

    doc.add_heading("Current Process", level=1)
    _add_fact_table(
        doc,
        record,
        [
            ("Trigger", "current_state.trigger"),
            ("Normal path", "current_state.steps"),
            ("Outcome", "current_state.outcome"),
            ("Exceptions", "current_state.exceptions"),
        ],
    )

    doc.add_heading("Value and Measurement", level=1)
    _add_fact_table(
        doc,
        record,
        [
            ("Annual manual hours", "value.annual_manual_hours"),
            ("Measurement plan", "value.measurement_plan"),
            ("Operational pain", "value.pain_severity_1_to_5"),
            ("Error and rework", "value.error_rework_severity_1_to_5"),
            ("Primary metric", "success_metrics.primary_metric"),
            ("Baseline", "success_metrics.baseline"),
            ("Target", "success_metrics.target"),
        ],
    )

    doc.add_heading("Systems Data and Access", level=1)
    _add_fact_table(
        doc,
        record,
        [
            ("Systems", "systems.primary_systems"),
            ("Interfaces", "systems.available_interfaces"),
            ("Data records", "data.records_in_scope"),
            ("Highest classification", "data.highest_classification"),
            ("Dependencies", "delivery.dependencies"),
        ],
    )

    doc.add_heading("Controls and Human Oversight", level=1)
    _add_fact_table(
        doc,
        record,
        [
            ("Human oversight", "controls.human_oversight_1_to_5"),
            ("Prohibited actions", "controls.prohibited_actions"),
            ("Approval points", "controls.approval_points"),
            ("Audit evidence", "controls.audit_requirements"),
        ],
    )

    doc.add_heading("Proposed Automated Process", level=1)
    _add_fact_table(
        doc,
        record,
        [
            ("User journey", "target_state.user_journey"),
            ("Automation boundary", "target_state.automation_boundary"),
            ("Fallback", "target_state.fallback_path"),
            ("User channels", "ui.channels"),
        ],
    )

    doc.add_heading("Priority Score", level=1)
    _add_table(
        doc,
        ["Dimension", "Points"],
        [(key.replace("_", " ").title(), f"{value:.1f}") for key, value in score.dimensions.items()],
        [5.9, 1.15],
    )
    doc.add_paragraph(
        "The adjusted score applies an evidence-confidence factor to the raw score. Missing information cannot improve priority, and the score does not replace architecture, security, privacy, compliance, or model-risk review."
    )

    doc.add_heading("Development Plan", level=1)
    plan_rows = [
        ("1", "Validate discovery", "Process owner confirms the current state, exceptions, volumes, and target outcome.", "Confirmed product card and process map"),
        ("2", "Measure baseline", _text(get(record, "value.measurement_plan")), "Reproducible baseline query and metric definition"),
        ("3", "Complete controls", "Classify data, define access, perform threat and privacy review, and approve the human oversight design.", "Approved control requirements"),
        ("4", "Build thin pilot", _text(get(record, "delivery.pilot_scope")), "Working pilot with audit logging and fallback"),
        ("5", "Evaluate", "Compare pilot results with the baseline and inspect errors, overrides, exceptions, and user feedback.", "Go, revise, or stop decision"),
        ("6", "Prepare production", "Harden integrations, monitoring, support, continuity, access recertification, and model change controls.", "Production readiness evidence"),
    ]
    _add_table(doc, ["Phase", "Purpose", "Work", "Exit evidence"], plan_rows, [0.55, 1.25, 3.6, 1.65])

    doc.add_heading("Required Reviews", level=1)
    reviews = [
        "Process owner confirmation",
        "Solution architecture and integration review",
        "Information security and threat review",
        "Privacy and data classification review",
        "Model risk or responsible AI review when a model influences decisions",
        "Operational resilience support and change review",
    ]
    for item in reviews:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("Evidence Register", level=1)
    evidence_rows = []
    for section_name, section in record.items():
        if not isinstance(section, dict) or section_name in {"score", "audit", "approvals"}:
            continue
        for field_name, fact in section.items():
            if isinstance(fact, dict) and "evidence" in fact:
                evidence_rows.append(
                    (
                        f"{section_name} {field_name}".replace("_", " ").title(),
                        fact.get("evidence", "unknown").replace("_", " ").title(),
                        fact.get("source_ref", ""),
                        fact.get("notes", ""),
                    )
                )
    _add_table(doc, ["Field", "Evidence", "Source", "Notes"], evidence_rows, [2.25, 1.1, 1.45, 2.25])

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Internal discovery draft  |  Validate before use").font.size = Pt(8)
    doc.save(path)
    return path
