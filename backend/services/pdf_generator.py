import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from services.emi import calculate_emi

class SanctionLetterGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom styles for the sanction letter"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=12,
            alignment=TA_LEFT
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkblue
        ))
    
    def generate_sanction_letter(
        self,
        applicant_name: str,
        pan_number: str,
        loan_amount: float,
        interest_rate: float,
        tenure_years: int,
        emi: float,
        application_id: str,
        sanction_date: datetime = None
    ) -> bytes:
        """Generate PDF sanction letter"""
        
        if sanction_date is None:
            sanction_date = datetime.now()
        
        # Create PDF buffer
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
        
        story = []
        
        # Header
        story.append(Paragraph("LOAN SANCTION LETTER", self.styles['CustomTitle']))
        story.append(Spacer(1, 20))
        
        # Date and Reference
        date_text = f"Date: {sanction_date.strftime('%d %B %Y')}"
        ref_text = f"Reference: {application_id}"
        
        story.append(Paragraph(date_text, self.styles['CustomNormal']))
        story.append(Paragraph(ref_text, self.styles['CustomNormal']))
        story.append(Spacer(1, 30))
        
        # Salutation
        story.append(Paragraph(f"Dear {applicant_name},", self.styles['CustomNormal']))
        story.append(Spacer(1, 20))
        
        # Main content
        approval_text = f"""
        We are pleased to inform you that your personal loan application has been approved. 
        The loan details are as follows:
        """
        story.append(Paragraph(approval_text, self.styles['CustomNormal']))
        story.append(Spacer(1, 20))
        
        # Loan details table
        loan_data = [
            ['Applicant Name', applicant_name],
            ['PAN Number', pan_number],
            ['Loan Amount', f"₹{loan_amount:,.2f}"],
            ['Interest Rate (p.a.)', f"{interest_rate}%"],
            ['Loan Tenure', f"{tenure_years} years"],
            ['Monthly EMI', f"₹{emi:,.2f}"],
            ['Application ID', application_id]
        ]
        
        table = Table(loan_data, colWidths=[2.5*inch, 3*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(table)
        story.append(Spacer(1, 30))
        
        # Terms and conditions
        story.append(Paragraph("Terms and Conditions:", self.styles['CustomHeading']))
        
        terms = """
        1. The loan is subject to successful completion of KYC verification.
        2. Interest rate is fixed for the entire loan tenure.
        3. EMI payments must be made on or before the due date each month.
        4. Prepayment charges may apply as per bank policy.
        5. The bank reserves the right to modify terms with prior notice.
        """
        
        story.append(Paragraph(terms, self.styles['CustomNormal']))
        story.append(Spacer(1, 30))
        
        # Next steps
        story.append(Paragraph("Next Steps:", self.styles['CustomHeading']))
        
        next_steps = """
        1. Complete the KYC verification process.
        2. Sign the loan agreement.
        3. Provide necessary documents for disbursement.
        4. Loan amount will be disbursed to your registered bank account.
        """
        
        story.append(Paragraph(next_steps, self.styles['CustomNormal']))
        story.append(Spacer(1, 30))
        
        # Closing
        closing_text = """
        Please feel free to contact us if you have any questions.
        
        We look forward to serving you.
        """
        
        story.append(Paragraph(closing_text, self.styles['CustomNormal']))
        story.append(Spacer(1, 30))
        
        # Signature
        story.append(Paragraph("Sincerely,", self.styles['CustomNormal']))
        story.append(Spacer(1, 10))
        story.append(Paragraph("LoanEase Team", self.styles['CustomNormal']))
        story.append(Paragraph("Digital Banking Division", self.styles['CustomNormal']))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF bytes
        buffer.seek(0)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        return pdf_bytes

# Global instance
_pdf_generator = None

def get_pdf_generator() -> SanctionLetterGenerator:
    """Get PDF generator instance"""
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = SanctionLetterGenerator()
    return _pdf_generator

def generate_sanction_letter(**kwargs) -> bytes:
    """Generate sanction letter with given parameters"""
    generator = get_pdf_generator()
    return generator.generate_sanction_letter(**kwargs)
