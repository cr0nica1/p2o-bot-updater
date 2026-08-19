#!/usr/bin/env python3
"""One-shot generator for docs/2026-08-19-data-quality-audit.pdf."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).with_name("2026-08-19-data-quality-audit.pdf")

NAVY = colors.HexColor("#1B2A4A")
TEAL = colors.HexColor("#1F6F6A")
AMBER = colors.HexColor("#B45309")
RED = colors.HexColor("#991B1B")
OK_BG = colors.HexColor("#ECFDF5")
BAD_BG = colors.HexColor("#FEF2F2")
WARN_BG = colors.HexColor("#FFFBEB")
ROW = colors.HexColor("#F8FAFC")
LINE = colors.HexColor("#CBD5E1")
MUTED = colors.HexColor("#475569")


def styles():
    base = getSampleStyleSheet()
    s = {
        "title": ParagraphStyle(
            "T", parent=base["Title"], fontName="Times-Bold", fontSize=18,
            leading=22, textColor=NAVY, alignment=TA_LEFT, spaceAfter=4,
        ),
        "sub": ParagraphStyle(
            "S", parent=base["Normal"], fontName="Times-Italic", fontSize=9,
            leading=12, textColor=MUTED, spaceAfter=12,
        ),
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontName="Times-Bold", fontSize=13,
            leading=16, textColor=NAVY, spaceBefore=14, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName="Times-Bold", fontSize=11,
            leading=14, textColor=TEAL, spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "B", parent=base["Normal"], fontName="Times-Roman", fontSize=9,
            leading=12, textColor=colors.HexColor("#0F172A"), spaceAfter=6,
        ),
        "cell": ParagraphStyle(
            "C", parent=base["Normal"], fontName="Times-Roman", fontSize=7.5,
            leading=10, textColor=colors.HexColor("#0F172A"),
        ),
        "cellb": ParagraphStyle(
            "CB", parent=base["Normal"], fontName="Times-Bold", fontSize=7.5,
            leading=10, textColor=NAVY,
        ),
        "cellh": ParagraphStyle(
            "CH", parent=base["Normal"], fontName="Times-Bold", fontSize=7.5,
            leading=10, textColor=colors.white,
        ),
        "foot": ParagraphStyle(
            "F", parent=base["Normal"], fontName="Times-Italic", fontSize=8,
            leading=10, textColor=MUTED,
        ),
        "bullet": ParagraphStyle(
            "BU", parent=base["Normal"], fontName="Times-Roman", fontSize=9,
            leading=12, leftIndent=8, textColor=colors.HexColor("#0F172A"),
        ),
    }
    return s


def P(text, st):
    return Paragraph(text, st)


def table(headers, rows, col_widths, header_bg=NAVY):
    s = styles()
    data = [[P(h, s["cellh"]) for h in headers]]
    for row in rows:
        data.append([P(str(c), s["cell"]) for c in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW]),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    # highlight verdict-like last column if it contains BAD/WRONG/MISSED
    for i, row in enumerate(rows, start=1):
        last = str(row[-1]).upper()
        if "WRONG" in last or "FALSE" in last or "404" in last or "JUNK" in last:
            cmds.append(("BACKGROUND", (-1, i), (-1, i), BAD_BG))
        elif last.startswith("OK") or last.startswith("0 ") or last == "NONE PUBLISHED":
            cmds.append(("BACKGROUND", (-1, i), (-1, i), OK_BG))
        elif "MAY" in last or "SCOPE" in last or "SELF" in last:
            cmds.append(("BACKGROUND", (-1, i), (-1, i), WARN_BG))
    t.setStyle(TableStyle(cmds))
    return t


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, letter[1] - 28, letter[0], 28, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Times-Bold", 8)
    canvas.drawString(0.7 * inch, letter[1] - 18, "Pwn2Own updater  ·  data quality audit")
    canvas.setFont("Times-Roman", 8)
    canvas.drawRightString(letter[0] - 0.7 * inch, letter[1] - 18, "2026-08-19")
    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, letter[0], 22, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Times-Roman", 8)
    canvas.drawString(0.7 * inch, 8, "Internal audit artifact  ·  pwn2own_updater @ localhost")
    canvas.drawRightString(letter[0] - 0.7 * inch, 8, f"Page {doc.page}")
    canvas.restoreState()


def build():
    s = styles()
    story = []
    usable = letter[0] - 1.4 * inch

    story.append(P("Data quality audit", s["title"]))
    story.append(P(
        "Missed CVEs, latest-version correctness, and database integrity  ·  "
        "MongoDB <b>pwn2own_updater</b>  ·  2026-08-19",
        s["sub"],
    ))
    story.append(P(
        "Snapshot of what is in Mongo today versus vendor pages (live version checkers, "
        "GitHub/npm) and NVD 2.0 keyword search. Not a full recrawl of every possible alias.",
        s["body"],
    ))

    story.append(P("1. Verdict", s["h1"]))
    story.append(P(
        "The database is <b>structurally healthy</b> (no orphans, no duplicate IDs, "
        "versions resolve to real targets). Software latest-versions match vendor sources. "
        "The gaps are search quality and one version meaning:",
        s["body"],
    ))
    story.append(ListFlowable([
        ListItem(P("<b>~46+ real CVEs never stored</b> because seed used long official names and no aliases (<i>Claude Code</i>, <i>pgvector</i>).", s["bullet"])),
        ListItem(P("<b>~17 Chroma rows are false positives</b> (FFmpeg / Razer / ChromeOS “chroma”).", s["bullet"])),
        ListItem(P("<b>Samsung Galaxy S26 version is the global SMR bulletin</b>, not an S26 firmware string. The page does not mention S26.", s["bullet"])),
        ListItem(P("<b>Incremental NVD sync 404s</b> for any target that already has a 2026 CVE (<i>pubStartDate</i> without <i>pubEndDate</i>).", s["bullet"])),
    ], bulletType="bullet", leftIndent=14, spaceBefore=2, spaceAfter=8))

    story.append(P("2. Inventory", s["h1"]))
    story.append(table(
        ["Collection", "Count", "Integrity"],
        [
            ["targets", "11", "Unique normalized_name. No duplicates."],
            ["vendor_configs", "11", "One checker bound to each target (Oura included)."],
            ["target_versions", "12", "All target_ids resolve. One is_latest per target."],
            ["vulnerabilities", "78", "Unique advisory_id. NVD 73, ZDI 7 (2 overlap)."],
            ["target_vulnerabilities", "78", "0 orphan links. 0 unlinked vulns."],
        ],
        [1.7 * inch, 0.7 * inch, usable - 2.4 * inch],
    ))
    story.append(Spacer(1, 6))
    story.append(P(
        "Leftover empty database <b>p2o</b> has the same collection names and 0 documents. "
        "The bot <i>.env</i> points at <b>pwn2own_updater</b> only. Harmless.",
        s["body"],
    ))
    story.append(P(
        "Last vuln <i>created_at</i>: <b>2026-08-18 04:17 UTC</b> (no CVE written on 2026-08-19). "
        "Version scan <i>last_seen</i>: <b>2026-08-19 01:04 UTC</b> (08:04 UTC+7) — daily version pass ran.",
        s["body"],
    ))

    story.append(P("3. Latest versions", s["h1"]))
    story.append(P(
        "Live lookup used the same <i>FirmwareLookupService</i> path as /check-version. "
        "Independent check used GitHub Releases/tags or npm latest.",
        s["body"],
    ))
    story.append(table(
        ["Target", "DB / live", "Independent", "Verdict"],
        [
            ["Anthropic Claude Code", "2.1.235", "npm @anthropic-ai/claude-code 2.1.235", "OK"],
            ["Chroma", "1.5.9", "GitHub chroma-core/chroma 1.5.9", "OK"],
            ["Home Assistant Green", "18.2", "GitHub HA OS 18.2", "OK"],
            ["LiteLLM", "v1.97.0", "GitHub BerriAI/litellm v1.97.0", "OK"],
            ["NVIDIA Dynamo", "v1.4.0", "GitHub ai-dynamo/dynamo v1.4.0", "OK"],
            ["OpenAI Codex", "0.148.0", "npm @openai/codex 0.148.0", "OK"],
            ["Oracle Autonomous AI DB", "23.26.3", "same Oracle page / regex", "OK (self-consistent)"],
            ["Oura Ring 5", "2.1.3", "same Oura support page / regex", "OK (self-consistent)"],
            ["Philips Hue Bridge Pro", "2071401010", "same Hue release-notes page", "OK (self-consistent)"],
            ["Postgres pgvector", "0.8.6", "GitHub tags v0.8.6 (HTML 429)", "OK"],
            ["Samsung Galaxy S26", "Aug-2026 Release 1", "Global SMR bulletin; no “S26” on page", "WRONG kind of version"],
        ],
        [1.7 * inch, 1.25 * inch, 2.15 * inch, usable - 5.1 * inch],
    ))
    story.append(P(
        "Claude Code has two version rows (2.1.234 previous, 2.1.235 latest) — expected history.",
        s["body"],
    ))

    story.append(P("3.1 Samsung — wrong meaning, not a stale number", s["h2"]))
    story.append(P(
        "Checker regex <font face='Courier'>SMR Month-20xx Release N</font> on "
        "<font face='Courier'>security.samsungmobile.com/securityUpdate.smsb</font>. "
        "First match is the global “SMR Aug-2026 Release 1” paragraph. "
        "Strings S26, Galaxy S26, SM-S93, SM-S94 are <b>absent</b>. "
        "Stored value is this month’s Samsung-wide SMR label, not a Galaxy S26 firmware / One UI / AP build.",
        s["body"],
    ))
    story.append(P(
        "pgvector CHANGELOG.html returned HTTP 429 during the audit; tag v0.8.6 still matches the DB.",
        s["body"],
    ))

    story.append(P("4. CVE coverage vs NVD", s["h1"]))
    story.append(P(
        "The tool searches <b>exact</b> keywordSearch=&lt;target.name&gt; only. "
        "Seeded targets have empty aliases. samples/targets.csv aliases were never imported.",
        s["body"],
    ))
    story.append(table(
        ["Target", "Stored", "Tool query", "Better query", "Missed / extra"],
        [
            ["Anthropic Claude Code", "0", "Anthropic Claude Code → 0", "Claude Code → 44", "~39–44 missed Claude Code CVEs"],
            ["Chroma", "24", "Chroma → 24", "ChromaDB → 7 (all in DB)", "~17 junk extra"],
            ["Home Assistant Green", "4 ZDI", "Home Assistant Green → 0", "Home Assistant → ~45", "0 Green-specific; Core is a scope call"],
            ["LiteLLM", "30", "LiteLLM → 30", "subset", "0"],
            ["NVIDIA Dynamo", "15", "NVIDIA Dynamo → 15", "—", "0"],
            ["OpenAI Codex", "4", "OpenAI Codex → 3 NVD", "—", "0 NVD; +ZDI-26-305 valid"],
            ["Oracle Autonomous AI DB", "0", "0", "Autonomous AI Database → 0", "none published"],
            ["Oura Ring 5", "0", "0", "Oura Ring → 0", "none published"],
            ["Philips Hue Bridge Pro", "1", "…Bridge Pro → 1", "Philips Hue Bridge → 11", "8× 2026 Hue Bridge (may apply)"],
            ["Postgres pgvector", "0", "Postgres pgvector → 0", "pgvector → 6", "2 real missed + 4 adjacent"],
            ["Samsung Galaxy S26", "0", "0", "0", "none published"],
        ],
        [1.45 * inch, 0.55 * inch, 1.55 * inch, 1.55 * inch, usable - 5.1 * inch],
    ))

    story.append(P("4.1 Missed — Claude Code (high confidence)", s["h2"]))
    story.append(P(
        "“Anthropic Claude Code” exact = 0. “Claude Code” exact = 44. "
        "About 39/44 descriptions start as “Claude Code is an agentic coding tool…”. "
        "Examples not in Mongo: CVE-2025-52882, CVE-2025-54794, CVE-2025-54795, "
        "CVE-2025-55284, CVE-2025-58764, CVE-2025-59041, CVE-2025-59828, and ~36 more. "
        "Root cause: search uses the seeded display name, not alias <i>claude code</i>.",
        s["body"],
    ))

    story.append(P("4.2 Missed — pgvector (high confidence)", s["h2"]))
    story.append(table(
        ["CVE", "In DB?", "Notes"],
        [
            ["CVE-2026-3172", "No", "Buffer overflow in pgvector 0.6.0–0.8.1 — real product"],
            ["CVE-2026-18022", "No", "IVFFlat wraparound, fixed in 0.8.6 — real product"],
            ["CVE-2024-23751", "No", "LlamaIndex Text-to-SQL — mentions pgvector"],
            ["CVE-2026-25211", "No", "Llama Stack logs pgvector password"],
            ["CVE-2026-55405", "No", "LangChain4j embedding store"],
            ["CVE-2026-60090", "No", "PraisonAI PGVector backend"],
        ],
        [1.4 * inch, 0.7 * inch, usable - 2.1 * inch],
    ))

    story.append(P("4.3 Possible miss — Philips Hue Bridge 2026", s["h2"]))
    story.append(P(
        "Stored: CVE-2026-73669 only (Bridge <b>Pro</b> MQTT). "
        "“Philips Hue Bridge” also returns CVE-2026-3555 … CVE-2026-3562 "
        "(Zigbee / HomeKit RCE and auth bypass). Those say “Hue Bridge”, not “Bridge Pro”. "
        "Not stored. Whether they affect Pro is unconfirmed. "
        "Older non-Pro: CVE-2017-14797, CVE-2020-6007.",
        s["body"],
    ))

    story.append(P("5. Wrong CVEs already stored (Chroma)", s["h1"]))
    story.append(P(
        "All 7 “ChromaDB” NVD hits <b>are</b> in the DB. The other ~17 “Chroma” hits are not chroma-core.",
        s["body"],
    ))
    story.append(table(
        ["CVE (examples)", "Actual product"],
        [
            ["CVE-2012-0851, 2013-2277, 2015-8217, 2018-7557, 2026-65706", "FFmpeg / libavcodec “chroma format”"],
            ["CVE-2020-16602, 2021-30493, 2021-30494", "Razer Chroma SDK / Synapse"],
            ["CVE-2021-3941", "OpenEXR ImfChromaticities"],
            ["CVE-2023-3739", "ChromeOS Chromad"],
            ["CVE-2023-54353", "Chromacam"],
        ],
        [3.2 * inch, usable - 3.2 * inch],
    ))
    story.append(Spacer(1, 6))
    story.append(P(
        "Real ChromaDB already stored: CVE-2026-45829…45833, CVE-2026-8828, "
        "and borderline CVE-2024-45848 (MindsDB + ChromaDB integration). "
        "Stored severity mix of all 78 rows: CRITICAL 8, HIGH 44, MEDIUM 18, LOW 8.",
        s["body"],
    ))

    story.append(P("6. Incremental NVD sync 404", s["h1"]))
    story.append(P(
        "sync_all() sets since_year to the max CVE year already linked. "
        "NvdSource then sends pubStartDate=2026-01-01T00:00:00.000 and no pubEndDate. "
        "NVD 2.0 requires both (max 120-day window) → HTTP 404.",
        s["body"],
    ))
    story.append(table(
        ["Target", "NVD since", "ZDI since", "Effect on next sync_all"],
        [
            ["Chroma", "2026", "2025", "NVD 404"],
            ["LiteLLM", "2026", "2025", "NVD 404"],
            ["NVIDIA Dynamo", "2026", "—", "NVD 404"],
            ["OpenAI Codex", "2026", "2026", "NVD 404"],
            ["Philips Hue Bridge Pro", "2026", "—", "NVD 404"],
            ["Home Assistant Green", "—", "2026", "NVD full search (0 on official name)"],
            ["Claude / Oracle / Oura / pgvector / S26", "—", "—", "Full search; official name is 0"],
        ],
        [2.2 * inch, 0.9 * inch, 0.9 * inch, usable - 4.0 * inch],
    ))

    story.append(P("7. Recommended fixes (not applied in this audit)", s["h1"]))
    story.append(ListFlowable([
        ListItem(P("Import aliases and search them: at least <i>Claude Code</i>, <i>pgvector</i>, <i>Philips Hue Bridge</i>. Re-sync those targets with sync_one (no since_year).", s["bullet"])),
        ListItem(P("Unlink Chroma junk (FFmpeg / Razer / Chromad / OpenEXR / Chromacam). Prefer ChromaDB or chroma-core.", s["bullet"])),
        ListItem(P("Fix NvdSource: when since_year is set, send pubEndDate and walk 120-day windows.", s["bullet"])),
        ListItem(P("Samsung: do not treat the global SMR headline as S26 firmware, or label the checker “Samsung SMR (not model firmware)”.", s["bullet"])),
        ListItem(P("Optionally drop empty p2o so the next silent-empty-sync cannot target the wrong DB.", s["bullet"])),
    ], bulletType="1", leftIndent=16, spaceBefore=2, spaceAfter=8))

    story.append(P("8. Method", s["h1"]))
    story.append(P(
        "Mongo collections, indexes, link integrity, and since_year via "
        "SyncVulnerabilitiesService._compute_since_years. "
        "FirmwareLookupService.lookup for all 11 targets. "
        "GitHub /releases/latest or /tags; npm latest for Claude Code and Codex. "
        "NVD cves/2.0 with keywordSearch ± keywordExactMatch, paced ~6 s/request. "
        "Samsung bulletin HTML: first regex match plus S26 / SM-S9* presence. "
        "NVD totals can move after 2026-08-19.",
        s["body"],
    ))
    story.append(P(
        "Companion markdown (same facts): docs/2026-08-19-data-quality-audit.md",
        s["foot"],
    ))

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.45 * inch,
        title="Pwn2Own updater data quality audit — 2026-08-19",
        author="p2o-bot-updater audit",
    )
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
