from fpdf import FPDF
import os
from datetime import datetime

class AuditReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "AlphaPulse Pro - Treasury Intelligence Report", align="C", ln=True)
        self.set_font("Helvetica", "", 10)
        self.cell(0, 10, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", align="C", ln=True)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}} | Read-Only Data | Not Financial Advice", align="C")

def generate_pdf(alerts: list, output_dir: str = "./reports"):
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/AlphaPulse_Audit_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.pdf"
    
    pdf = AuditReport()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Executive Summary", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, f"Total alerts analyzed: {len(alerts)}\nHigh-risk events flagged: {len([a for a in alerts if a.get('risk_score', 0) >= 3])}")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Event Log", ln=True)
    
    for a in alerts:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 8, f"[Risk: {a.get('risk_score', 0)}/7] {a.get('title', 'Event')}", ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, f"Entity: {a.get('entity', 'N/A')}", ln=True)
        pdf.cell(0, 6, f"Chain: {a.get('chain', 'N/A')} | Amount: {a.get('amount', 'N/A')}", ln=True)
        pdf.cell(0, 6, f"Flags: {a.get('flags', 'None')}", ln=True)
        pdf.set_text_color(0, 0, 255)
        pdf.cell(0, 6, f"TX: {a.get('tx', 'N/A')}", ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(3)
        
    pdf.output(filename)
    return filename
