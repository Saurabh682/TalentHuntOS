"""Report Exporter Module for TalentHunt OS Analytics.

Supports exporting recruitment dashboard metrics and funnel insights
to PDF reports, CSV data files, and Excel spreadsheets.
"""

import io
import csv
from datetime import datetime, timezone
from typing import Dict, Any, Optional


def generate_analytics_csv(metrics_data: Dict[str, Any]) -> str:
    """Generate CSV string containing Executive KPI Summary, Funnel, and Time-to-Fill data."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(["TalentHunt OS - Executive Analytics Report"])
    writer.writerow(["Generated At", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")])
    writer.writerow([])

    # KPI Summary
    kpi = metrics_data.get("kpi", {})
    writer.writerow(["--- EXECUTIVE KPI SUMMARY ---"])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Total Talent Hunts", kpi.get("total_hunts", 0)])
    writer.writerow(["Active Hunts", kpi.get("active_hunts", 0)])
    writer.writerow(["Completed Hunts", kpi.get("completed_hunts", 0)])
    writer.writerow(["Total Candidates Sourced", kpi.get("total_sourced", 0)])
    writer.writerow(["Candidates Interviewing", kpi.get("interviewing_candidates", 0)])
    writer.writerow(["Candidates Hired", kpi.get("hired_candidates", 0)])
    writer.writerow(["Funnel Conversion Rate (%)", f"{kpi.get('conversion_rate', 0)}%"])
    writer.writerow(["Avg Time-to-Fill (Days)", f"{kpi.get('avg_time_to_fill_days', 0)} days"])
    writer.writerow(["Outreach Messages Sent", kpi.get("outreach_sent", 0)])
    writer.writerow(["Outreach Replies Received", kpi.get("outreach_replied", 0)])
    writer.writerow(["Outreach Response Rate (%)", f"{kpi.get('response_rate', 0)}%"])
    writer.writerow(["AI Operations Executed", kpi.get("ai_actions", 0)])
    writer.writerow(["Estimated Cost Saved ($)", f"${kpi.get('estimated_cost_saved', 0.0)}"])
    writer.writerow([])

    # Sourcing Funnel
    funnel = metrics_data.get("funnel", {})
    writer.writerow(["--- TALENT RECRUITMENT FUNNEL ---"])
    writer.writerow(["Stage Name", "Candidate Count", "Overall Conversion (%)", "Drop-off Rate (%)"])
    for stage_info in funnel.get("stages", []):
        writer.writerow([
            stage_info.get("stage"),
            stage_info.get("count"),
            f"{stage_info.get('overall_conversion')}%",
            f"{stage_info.get('dropoff_rate')}%",
        ])
    writer.writerow([])

    # Time-to-Fill Velocity
    velocity = metrics_data.get("velocity", {})
    writer.writerow(["--- HUNT VELOCITY & TIME-TO-FILL ---"])
    writer.writerow(["Hunt Title", "Target Role", "Status", "Total Candidates", "Hired Count", "Days Open", "Time to Fill (Days)"])
    for hunt_vel in velocity.get("hunts_velocity", []):
        writer.writerow([
            hunt_vel.get("title"),
            hunt_vel.get("target_role"),
            hunt_vel.get("status"),
            hunt_vel.get("total_candidates"),
            hunt_vel.get("hired_count"),
            hunt_vel.get("days_open"),
            hunt_vel.get("time_to_fill_days"),
        ])
    writer.writerow([])

    # AI Cost Tracker
    ai_cost = metrics_data.get("ai_cost", {})
    writer.writerow(["--- AI ENGINE COST TRACKER ---"])
    writer.writerow(["Total AI Operations", ai_cost.get("total_operations", 0)])
    writer.writerow(["Local Edge Operations (Llama 3)", ai_cost.get("local_operations", 0)])
    writer.writerow(["Cloud API Operations", ai_cost.get("cloud_operations", 0)])
    writer.writerow(["Actual Cloud API Cost ($)", f"${ai_cost.get('actual_cloud_cost', 0.0)}"])
    writer.writerow(["Net Cost Saved ($)", f"${ai_cost.get('total_cost_saved', 0.0)}"])
    writer.writerow([])

    return output.getvalue()


def generate_analytics_excel(metrics_data: Dict[str, Any]) -> bytes:
    """Generate Excel-compatible binary CSV/TSV report stream."""
    csv_content = generate_analytics_csv(metrics_data)
    return csv_content.encode("utf-8")


def generate_analytics_pdf(metrics_data: Dict[str, Any]) -> bytes:
    """Generate Executive Analytics PDF document using ReportLab (or fallback generator)."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            HRFlowable,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        
        # Custom dark-theme / teal accent styles
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
            fontName="Helvetica-Bold",
        )
        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#00d4aa"),
            fontName="Helvetica-Bold",
        )
        section_style = ParagraphStyle(
            "SectionHeader",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            fontName="Helvetica-Bold",
            spaceBefore=14,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "BodyDark",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#334155"),
        )
        cell_header_style = ParagraphStyle(
            "CellHeader",
            parent=styles["Normal"],
            fontSize=9,
            leading=11,
            textColor=colors.white,
            fontName="Helvetica-Bold",
        )
        cell_body_style = ParagraphStyle(
            "CellBody",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1e293b"),
        )

        story = []

        # Header Title
        story.append(Paragraph("TalentHunt OS - Analytics & Intelligence Report", title_style))
        story.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')} | Confidential Recruitment Executive Briefing", subtitle_style))
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#00d4aa"), spaceAfter=15))

        # KPI Summary Section
        kpi = metrics_data.get("kpi", {})
        story.append(Paragraph("Executive KPI Overview", section_style))
        
        kpi_table_data = [
            [
                Paragraph("<b>Metric</b>", cell_header_style),
                Paragraph("<b>Value</b>", cell_header_style),
                Paragraph("<b>Metric</b>", cell_header_style),
                Paragraph("<b>Value</b>", cell_header_style),
            ],
            [
                Paragraph("Total Talent Hunts", cell_body_style),
                Paragraph(str(kpi.get("total_hunts", 0)), cell_body_style),
                Paragraph("Total Candidates Sourced", cell_body_style),
                Paragraph(str(kpi.get("total_sourced", 0)), cell_body_style),
            ],
            [
                Paragraph("Active Talent Hunts", cell_body_style),
                Paragraph(str(kpi.get("active_hunts", 0)), cell_body_style),
                Paragraph("Candidates Hired", cell_body_style),
                Paragraph(str(kpi.get("hired_candidates", 0)), cell_body_style),
            ],
            [
                Paragraph("Funnel Conversion Rate", cell_body_style),
                Paragraph(f"{kpi.get('conversion_rate', 0)}%", cell_body_style),
                Paragraph("Avg Time-to-Fill", cell_body_style),
                Paragraph(f"{kpi.get('avg_time_to_fill_days', 0)} Days", cell_body_style),
            ],
            [
                Paragraph("Outreach Response Rate", cell_body_style),
                Paragraph(f"{kpi.get('response_rate', 0)}%", cell_body_style),
                Paragraph("Net AI Cost Saved", cell_body_style),
                Paragraph(f"${kpi.get('estimated_cost_saved', 0.0)}", cell_body_style),
            ],
        ]

        t_kpi = Table(kpi_table_data, colWidths=[150, 110, 160, 120])
        t_kpi.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t_kpi)
        story.append(Spacer(1, 15))

        # Recruitment Funnel Section
        funnel = metrics_data.get("funnel", {})
        story.append(Paragraph("Recruitment Funnel & Stage Breakdown", section_style))

        funnel_table_data = [
            [
                Paragraph("<b>Pipeline Stage</b>", cell_header_style),
                Paragraph("<b>Candidate Count</b>", cell_header_style),
                Paragraph("<b>Overall Conversion</b>", cell_header_style),
                Paragraph("<b>Stage Drop-off</b>", cell_header_style),
            ]
        ]
        for stage_info in funnel.get("stages", []):
            funnel_table_data.append([
                Paragraph(str(stage_info.get("stage")), cell_body_style),
                Paragraph(str(stage_info.get("count")), cell_body_style),
                Paragraph(f"{stage_info.get('overall_conversion')}%", cell_body_style),
                Paragraph(f"{stage_info.get('dropoff_rate')}%", cell_body_style),
            ])

        t_funnel = Table(funnel_table_data, colWidths=[150, 120, 135, 135])
        t_funnel.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t_funnel)
        story.append(Spacer(1, 15))

        # Time-to-Fill Velocity Section
        velocity = metrics_data.get("velocity", {})
        story.append(Paragraph("Hunt Velocity & Time-to-Fill Metrics", section_style))

        vel_table_data = [
            [
                Paragraph("<b>Hunt Title</b>", cell_header_style),
                Paragraph("<b>Status</b>", cell_header_style),
                Paragraph("<b>Sourced</b>", cell_header_style),
                Paragraph("<b>Hired</b>", cell_header_style),
                Paragraph("<b>Days Open</b>", cell_header_style),
                Paragraph("<b>Time-to-Fill</b>", cell_header_style),
            ]
        ]
        for h_vel in velocity.get("hunts_velocity", []):
            vel_table_data.append([
                Paragraph(str(h_vel.get("title")), cell_body_style),
                Paragraph(str(h_vel.get("status")), cell_body_style),
                Paragraph(str(h_vel.get("total_candidates")), cell_body_style),
                Paragraph(str(h_vel.get("hired_count")), cell_body_style),
                Paragraph(f"{h_vel.get('days_open')} d", cell_body_style),
                Paragraph(f"{h_vel.get('time_to_fill_days')} d", cell_body_style),
            ])

        t_vel = Table(vel_table_data, colWidths=[170, 75, 75, 65, 75, 80])
        t_vel.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t_vel)
        story.append(Spacer(1, 15))

        # AI Cost & Resource Efficiency Section
        ai_cost = metrics_data.get("ai_cost", {})
        story.append(Paragraph("AI Engine Cost & Token Savings", section_style))
        ai_summary_text = (
            f"TalentHunt OS executed <b>{ai_cost.get('total_operations', 0)} AI operations</b>. "
            f"By leveraging local GGUF models on llama-server for <b>{ai_cost.get('local_operations', 0)} operations ({int(ai_cost.get('local_operations', 0)/max(1, ai_cost.get('total_operations', 1))*100)}%)</b>, "
            f"the platform saved <b>${ai_cost.get('total_cost_saved', 0.0)} USD</b> compared to standard cloud API LLM rates."
        )
        story.append(Paragraph(ai_summary_text, body_style))

        doc.build(story)
        return buffer.getvalue()

    except Exception as e:
        raise RuntimeError(f"PDF report generation failed: {e}") from e
