from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# Register Helvetica replacement with rupee support
_FONT_REGISTERED = False
def _register_font():
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    # Use NotoSans if available, else fallback to Rs.
    font_paths = [
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
        '/Library/Fonts/Arial Unicode.ttf',
        '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont('UniFont', fp))
                _FONT_REGISTERED = True
                return
            except:
                pass
_register_font()
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from io import BytesIO
from datetime import datetime
from decimal import Decimal

UNIVERIN = {
    'name':    'Univerin Private Limited',
    'address': '4/11, Sankarapuram, Govindampalli, Obulavaripalle - 516105, Andhra Pradesh',
    'gstin':   '37AADCU8846J1ZP',
    'pan':     'AADCU8846J',
    'tan':     'HYDV12345A',
    'email':   'contact@univerin.in',
    'phone':   '9000869619',
}

BLUE  = colors.HexColor('#2563eb')
DARK  = colors.HexColor('#111827')
GRAY  = colors.HexColor('#6b7280')
LIGHT = colors.HexColor('#f3f4f6')
WHITE = colors.white

def _p(text, font='Helvetica', size=8, color=None, align='LEFT', bold=False):
    fn = 'Helvetica-Bold' if bold else font
    al = {'LEFT':0,'CENTER':1,'RIGHT':2}.get(align,0)
    c  = color or DARK
    return Paragraph(text, ParagraphStyle('s', fontName=fn, fontSize=size, textColor=c, alignment=al, leading=size+3))

def inv_num(order, prefix='INV'):
    y = datetime.now().year
    return f'{prefix}/{y}-{str(y+1)[-2:]}/{str(order.id)[:6].upper()}'

def header_table(order, title, extra=''):
    inv = inv_num(order, title)
    dt  = order.created_at.strftime('%d %b %Y')
    left  = _p('<b><font color="#2563eb" size="22">Univerin</font></b>', size=22)
    right = _p(f'<b>TAX INVOICE</b><br/><font size="8" color="#6b7280">No: {inv}</font><br/><font size="8" color="#6b7280">Date: {dt}</font><br/><font size="8" color="#6b7280">Order: {str(order.id)[:12].upper()}</font>{extra}', size=10, align='RIGHT')
    t = Table([[left, right]], colWidths=[90*mm, 90*mm])
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),0.5,colors.HexColor('#e5e7eb'))]))
    return t

def generate_buyer_invoice(order):
    """Doc 1 — Combined Buyer Invoice (Wrapper with Section A + Section B)"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from io import BytesIO
    from decimal import Decimal
    from .tax_utils import calc_gst, is_interstate, get_state_code, PLATFORM_STATE, PLATFORM_GSTIN, amount_in_words
    from .models import InvoiceSequence

    BLUE  = colors.HexColor("#2563eb")
    DARK  = colors.HexColor("#111827")
    GRAY  = colors.HexColor("#6b7280")
    LIGHT = colors.HexColor("#f3f4f6")
    GREEN = colors.HexColor("#16a34a")

    def p(text, font="Helvetica", size=8, color=None, align="LEFT", bold=False):
        fn = "Helvetica-Bold" if bold else font
        al = {"LEFT":0,"CENTER":1,"RIGHT":2}.get(align,0)
        return Paragraph(text, ParagraphStyle("s", fontName=fn, fontSize=size, textColor=color or DARK, alignment=al, leading=size+3))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)
    s = []

    buyer        = order.buyer
    vendor       = order.vendor
    bn           = getattr(buyer, 'full_name', None) or buyer.phone_number
    sg           = getattr(vendor, 'gstin', None) or "N/A"
    vendor_state = getattr(vendor, 'state', PLATFORM_STATE) or PLATFORM_STATE
    buyer_state  = PLATFORM_STATE
    try:
        addr = buyer.addresses.filter(is_default=True).first() or buyer.addresses.first()
        if addr and addr.state:
            buyer_state = addr.state
    except:
        pass

    vendor_sc   = get_state_code(vendor_state)
    buyer_sc    = get_state_code(buyer_state)
    platform_sc = get_state_code(PLATFORM_STATE)
    dt          = order.created_at.strftime("%d %b %Y")
    pm          = "COD — Paid" if order.payment_mode == "cod" else "Online — Paid"
    fy          = "2526"

    # Wrapper invoice number
    wrapper_no  = InvoiceSequence.next_number("UNV-BI", fy)

    # Section A invoice numbers
    seller_code = vendor.shop_name[:3].upper()
    sec_a_no    = InvoiceSequence.next_number(f"{seller_code}-SI", fy)
    sec_b_no    = InvoiceSequence.next_number("UNV-PF", fy)

    # ── Header ──────────────────────────────────────────────────
    left  = p('<b><font color="#2563eb" size="20">Univerin</font></b>', size=20)
    right = p(f'<b>ORDER SUMMARY & TAX INVOICES</b><br/><font size="8" color="#6b7280">Order #: {order.order_number}</font><br/><font size="8" color="#6b7280">Date: {dt}</font><br/><font size="8" color="#6b7280">Payment: {pm}</font><br/><font size="8" color="#6b7280">Ref: {wrapper_no}</font>', size=10, align='RIGHT')
    ht = Table([[left, right]], colWidths=[90*mm, 90*mm])
    ht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),1,BLUE)]))
    s.append(ht)
    s.append(Spacer(1,3*mm))

    # Billed to
    pd = [[
        p("<b>Billed to:</b>",bold=True),
        p(f"{bn} | Ph: {buyer.phone_number}<br/>{order.delivery_address or 'N/A'} | State: {buyer_state} ({buyer_sc})")
    ]]
    bt = Table(pd, colWidths=[25*mm, 155*mm])
    bt.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),4),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb"))]))
    s.append(bt)
    s.append(Spacer(1,5*mm))

    # ══════════════════════════════════════════════════════════
    # SECTION A — TAX INVOICE FROM SELLER
    # ══════════════════════════════════════════════════════════
    s.append(p("[ SECTION A — TAX INVOICE FROM SELLER ]", bold=True, size=9, color=BLUE))
    s.append(Spacer(1,2*mm))

    sec_a_interstate = is_interstate(vendor_state, buyer_state)
    sec_a_info = [
        [p(f"Issued by: {vendor.shop_name}",bold=True), p(f"GSTIN: {sg}",align="RIGHT")],
        [p(f"Invoice #: {sec_a_no} | Date: {dt}"), p(f"Place of supply: {buyer_state} ({buyer_sc}) | Reverse charge: No",align="RIGHT")],
    ]
    sit = Table(sec_a_info, colWidths=[90*mm,90*mm])
    sit.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#eff6ff")),("PADDING",(0,0),(-1,-1),4),("BOX",(0,0),(-1,-1),0.5,BLUE)]))
    s.append(sit)
    s.append(Spacer(1,2*mm))

    # Seller items table
    if sec_a_interstate:
        hdr = [p("<b>Item</b>",bold=True),p("<b>HSN</b>",bold=True,align="CENTER"),p("<b>Qty</b>",bold=True,align="CENTER"),p("<b>Rate</b>",bold=True,align="RIGHT"),p("<b>Taxable</b>",bold=True,align="RIGHT"),p("<b>GST%</b>",bold=True,align="CENTER"),p("<b>IGST</b>",bold=True,align="RIGHT"),p("<b>Total</b>",bold=True,align="RIGHT")]
        cw = [45*mm,16*mm,12*mm,22*mm,22*mm,12*mm,20*mm,22*mm]
    else:
        hdr = [p("<b>Item</b>",bold=True),p("<b>HSN</b>",bold=True,align="CENTER"),p("<b>Qty</b>",bold=True,align="CENTER"),p("<b>Rate</b>",bold=True,align="RIGHT"),p("<b>Taxable</b>",bold=True,align="RIGHT"),p("<b>GST%</b>",bold=True,align="CENTER"),p("<b>CGST</b>",bold=True,align="RIGHT"),p("<b>SGST</b>",bold=True,align="RIGHT"),p("<b>Total</b>",bold=True,align="RIGHT")]
        cw = [38*mm,14*mm,10*mm,18*mm,18*mm,10*mm,16*mm,16*mm,18*mm]

    rows = [hdr]
    sec_a_taxable = Decimal("0")
    sec_a_cgst    = Decimal("0")
    sec_a_sgst    = Decimal("0")
    sec_a_igst    = Decimal("0")

    for item in order.items.all():
        pr      = Decimal(str(item.price))
        taxable = pr * item.quantity
        gst_pct = Decimal(str(item.product.gst_percentage or 0))
        hsn     = getattr(item.product, 'hsn_code', None) or "—"
        cgst, sgst, igst = calc_gst(taxable, gst_pct, vendor_state, buyer_state)
        total_line = taxable + cgst + sgst + igst
        sec_a_taxable += taxable
        sec_a_cgst    += cgst
        sec_a_sgst    += sgst
        sec_a_igst    += igst
        if sec_a_interstate:
            rows.append([p(item.product.name),p(hsn,align="CENTER"),p(str(item.quantity),align="CENTER"),p(f"Rs.{pr:.2f}",align="RIGHT"),p(f"Rs.{taxable:.2f}",align="RIGHT"),p(f"{gst_pct:.0f}%",align="CENTER"),p(f"Rs.{igst:.2f}",align="RIGHT"),p(f"Rs.{total_line:.2f}",align="RIGHT")])
        else:
            rows.append([p(item.product.name),p(hsn,align="CENTER"),p(str(item.quantity),align="CENTER"),p(f"Rs.{pr:.2f}",align="RIGHT"),p(f"Rs.{taxable:.2f}",align="RIGHT"),p(f"{gst_pct:.0f}%",align="CENTER"),p(f"Rs.{cgst:.2f}",align="RIGHT"),p(f"Rs.{sgst:.2f}",align="RIGHT"),p(f"Rs.{total_line:.2f}",align="RIGHT")])

    it = Table(rows, colWidths=cw)
    it.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),3),("FONTSIZE",(0,0),(-1,-1),7)]))
    s.append(it)

    sec_a_total = sec_a_taxable + sec_a_cgst + sec_a_sgst + sec_a_igst
    sec_a_summary = [[p("Taxable"), p(f"Rs.{sec_a_taxable:.2f}",align="RIGHT")]]
    if sec_a_interstate:
        sec_a_summary.append([p("IGST"), p(f"Rs.{sec_a_igst:.2f}",align="RIGHT")])
    else:
        sec_a_summary.append([p("CGST"), p(f"Rs.{sec_a_cgst:.2f}",align="RIGHT")])
        sec_a_summary.append([p("SGST"), p(f"Rs.{sec_a_sgst:.2f}",align="RIGHT")])
    sec_a_summary.append([p("<b>Section A Total</b>",bold=True,color=BLUE), p(f"<b>Rs.{sec_a_total:.2f}</b>",bold=True,color=BLUE,align="RIGHT")])
    sat = Table(sec_a_summary, colWidths=[130*mm,40*mm], hAlign="RIGHT")
    sat.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("LINEABOVE",(0,-1),(-1,-1),1,BLUE),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#eff6ff")),("PADDING",(0,0),(-1,-1),3)]))
    s.append(sat)
    s.append(Spacer(1,5*mm))

    # ══════════════════════════════════════════════════════════
    # SECTION B — TAX INVOICE FROM UNIVERIN (Platform)
    # ══════════════════════════════════════════════════════════
    s.append(p("[ SECTION B — TAX INVOICE FROM UNIVERIN (Platform service) ]", bold=True, size=9, color=GREEN))
    s.append(Spacer(1,2*mm))

    sec_b_interstate = is_interstate(PLATFORM_STATE, buyer_state)
    sec_b_info = [
        [p("Issued by: Univerin Private Limited",bold=True), p(f"GSTIN: {PLATFORM_GSTIN}",align="RIGHT")],
        [p(f"Invoice #: {sec_b_no} | Date: {dt}"), p(f"Place of supply: {buyer_state} ({buyer_sc}) | Reverse charge: No",align="RIGHT")],
    ]
    sbit = Table(sec_b_info, colWidths=[90*mm,90*mm])
    sbit.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f0fdf4")),("PADDING",(0,0),(-1,-1),4),("BOX",(0,0),(-1,-1),0.5,GREEN)]))
    s.append(sbit)
    s.append(Spacer(1,2*mm))

    pf  = Decimal(str(order.platform_fee or 10))
    df  = Decimal(str(order.delivery_fee or 0))
    pf_cgst, pf_sgst, pf_igst = calc_gst(pf, 18, PLATFORM_STATE, buyer_state)
    df_cgst, df_sgst, df_igst = calc_gst(df, 18, PLATFORM_STATE, buyer_state)
    pf_total = pf + pf_cgst + pf_sgst + pf_igst
    df_total = df + df_cgst + df_sgst + df_igst
    sec_b_total = pf_total + df_total

    if sec_b_interstate:
        hdr_b = [p("<b>Description</b>",bold=True),p("<b>SAC</b>",bold=True,align="CENTER"),p("<b>Base</b>",bold=True,align="RIGHT"),p("<b>GST 18%</b>",bold=True,align="RIGHT"),p("<b>IGST</b>",bold=True,align="RIGHT"),p("<b>Total</b>",bold=True,align="RIGHT")]
        rows_b = [hdr_b]
        if pf > 0:
            rows_b.append([p("Platform fee — Marketplace facilitation"),p("998599",align="CENTER"),p(f"Rs.{pf:.2f}",align="RIGHT"),p("18%",align="RIGHT"),p(f"Rs.{pf_igst:.2f}",align="RIGHT"),p(f"Rs.{pf_total:.2f}",align="RIGHT")])
        if df > 0:
            rows_b.append([p("Delivery fee — Logistics service"),p("996813",align="CENTER"),p(f"Rs.{df:.2f}",align="RIGHT"),p("18%",align="RIGHT"),p(f"Rs.{df_igst:.2f}",align="RIGHT"),p(f"Rs.{df_total:.2f}",align="RIGHT")])
        bt2 = Table(rows_b, colWidths=[60*mm,18*mm,25*mm,20*mm,25*mm,25*mm])
    else:
        hdr_b = [p("<b>Description</b>",bold=True),p("<b>SAC</b>",bold=True,align="CENTER"),p("<b>Base</b>",bold=True,align="RIGHT"),p("<b>CGST 9%</b>",bold=True,align="RIGHT"),p("<b>SGST 9%</b>",bold=True,align="RIGHT"),p("<b>Total</b>",bold=True,align="RIGHT")]
        rows_b = [hdr_b]
        if pf > 0:
            rows_b.append([p("Platform fee — Marketplace facilitation"),p("998599",align="CENTER"),p(f"Rs.{pf:.2f}",align="RIGHT"),p(f"Rs.{pf_cgst:.2f}",align="RIGHT"),p(f"Rs.{pf_sgst:.2f}",align="RIGHT"),p(f"Rs.{pf_total:.2f}",align="RIGHT")])
        if df > 0:
            rows_b.append([p("Delivery fee — Logistics service"),p("996813",align="CENTER"),p(f"Rs.{df:.2f}",align="RIGHT"),p(f"Rs.{df_cgst:.2f}",align="RIGHT"),p(f"Rs.{df_sgst:.2f}",align="RIGHT"),p(f"Rs.{df_total:.2f}",align="RIGHT")])
        bt2 = Table(rows_b, colWidths=[60*mm,18*mm,25*mm,22*mm,22*mm,26*mm])

    bt2.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),3),("FONTSIZE",(0,0),(-1,-1),7)]))
    s.append(bt2)

    sec_b_summary = [[p("<b>Section B Total</b>",bold=True,color=GREEN), p(f"<b>Rs.{sec_b_total:.2f}</b>",bold=True,color=GREEN,align="RIGHT")]]
    sbt2 = Table(sec_b_summary, colWidths=[130*mm,40*mm], hAlign="RIGHT")
    sbt2.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f0fdf4")),("PADDING",(0,0),(-1,-1),3)]))
    s.append(sbt2)
    s.append(Spacer(1,5*mm))

    # ══════════════════════════════════════════════════════════
    # GRAND TOTAL
    # ══════════════════════════════════════════════════════════
    gt = Decimal(str(order.total_amount))
    td = [
        [p("Section A — Seller goods total"), p(f"Rs.{sec_a_total:.2f}",align="RIGHT")],
        [p("Section B — Platform charges total"), p(f"Rs.{sec_b_total:.2f}",align="RIGHT")],
        [p("<b>Grand total paid</b>",bold=True,size=11,color=DARK), p(f"<b>Rs.{gt:.2f}</b>",bold=True,size=11,align="RIGHT")],
    ]
    tt = Table(td, colWidths=[130*mm,40*mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("LINEABOVE",(0,-1),(-1,-1),1.5,DARK),("BACKGROUND",(0,-1),(-1,-1),LIGHT),("PADDING",(0,0),(-1,-1),5)]))
    s.append(tt)
    s.append(Spacer(1,2*mm))
    s.append(p(f"Amount in words: {amount_in_words(gt)}", color=GRAY, size=7))
    s.append(Spacer(1,5*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    for n in [
        "This is a presentation wrapper over two separate tax invoices (Section A from seller, Section B from Univerin).",
        "Goods are supplied by the respective seller. Univerin is a marketplace facilitator only.",
        "Platform and delivery services are provided by Univerin Private Limited (GSTIN: 37AADCU8846J1ZP).",
        "This is a computer-generated document and does not require a physical signature.",
        "For support: contact@univerin.in | Ph: 9000869619"
    ]:
        s.append(p("• "+n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(p(f"Univerin Private Limited | GSTIN: {PLATFORM_GSTIN} | contact@univerin.in | 9000869619", color=GRAY, align="CENTER", size=7))
    s.append(p("Thank you for shopping with Univerin!", bold=True, color=DARK, align="CENTER"))
    doc.build(s)
    buf.seek(0)
    return buf

def generate_commission_invoice(order):
    """Doc 4 — Commission Invoice (Platform to Seller) with CGST/SGST or IGST"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from io import BytesIO
    from decimal import Decimal
    from .tax_utils import calc_gst, is_interstate, get_state_code, PLATFORM_STATE, PLATFORM_GSTIN, amount_in_words
    from .models import InvoiceSequence

    BLUE  = colors.HexColor("#2563eb")
    DARK  = colors.HexColor("#111827")
    GRAY  = colors.HexColor("#6b7280")
    LIGHT = colors.HexColor("#f3f4f6")

    def p(text, font="Helvetica", size=8, color=None, align="LEFT", bold=False):
        fn = "Helvetica-Bold" if bold else font
        al = {"LEFT":0,"CENTER":1,"RIGHT":2}.get(align,0)
        return Paragraph(text, ParagraphStyle("s", fontName=fn, fontSize=size, textColor=color or DARK, alignment=al, leading=size+3))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)
    s = []

    vendor       = order.vendor
    vendor_state = getattr(vendor, "state", PLATFORM_STATE) or PLATFORM_STATE
    sg           = getattr(vendor, "gstin", None) or "N/A"
    vendor_sc    = get_state_code(vendor_state)
    platform_sc  = get_state_code(PLATFORM_STATE)
    interstate   = is_interstate(PLATFORM_STATE, vendor_state)
    order_date   = order.created_at.strftime("%d %b %Y")
    fy           = "2526"
    inv_no       = InvoiceSequence.next_number("UNV-CM", fy)

    sub  = Decimal(str(order.subtotal or 0))
    cr   = Decimal(str(order.commission_rate or 6))
    ca   = (sub * cr / 100).quantize(Decimal("0.01"))
    cgst, sgst, igst = calc_gst(ca, 18, PLATFORM_STATE, vendor_state)
    total = ca + cgst + sgst + igst

    # Header
    left  = p('<b><font color="#2563eb" size="22">Univerin</font></b>', size=22)
    right = p(f'<b>TAX INVOICE</b><br/><font size="8" color="#6b7280">No: {inv_no}</font><br/><font size="8" color="#6b7280">Date: {order_date}</font><br/><font size="8" color="#6b7280">Order: {str(order.id)[:12].upper()}</font>', size=10, align='RIGHT')
    ht = Table([[left, right]], colWidths=[90*mm, 90*mm])
    ht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),0.5,colors.HexColor("#e5e7eb"))]))
    s.append(ht)
    s.append(Spacer(1,3*mm))
    s.append(p("Hyperlocal Marketplace", color=GRAY, align="CENTER"))
    s.append(Spacer(1,2*mm))
    pos_text = f"Place of supply: {vendor_state} ({vendor_sc}) | Reverse charge: No"
    s.append(p(pos_text, color=GRAY, align="CENTER", size=7))
    s.append(Spacer(1,4*mm))

    # Parties
    pd = [
        [p("<b>From (Univerin)</b>", bold=True), p("<b>To (Seller)</b>", bold=True)],
        [p(f"Univerin Private Limited<br/>4/11, Sankarapuram, Govindampalli,<br/>Obulavaripalle - 516105, AP<br/>State: {PLATFORM_STATE} ({platform_sc})<br/>GSTIN: {PLATFORM_GSTIN}"),
         p(f"{vendor.shop_name}<br/>State: {vendor_state} ({vendor_sc})<br/>GSTIN: {sg}<br/>Category: {vendor.category or 'N/A'}")]
    ]
    pt = Table(pd, colWidths=[90*mm,90*mm])
    pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)]))
    s.append(pt)
    s.append(Spacer(1,4*mm))

    # Commission table
    ct = Table([
        [p("<b>Description</b>",bold=True), p("<b>Order value</b>",bold=True,align="RIGHT"), p("<b>Rate</b>",bold=True,align="CENTER"), p("<b>SAC</b>",bold=True,align="CENTER"), p("<b>Commission</b>",bold=True,align="RIGHT")],
        [p(f"Marketplace commission — {cr:.0f}%<br/>on order {order.order_number}"), p(f"Rs.{sub:.2f}",align="RIGHT"), p(f"{cr:.1f}%",align="CENTER"), p("998599",align="CENTER"), p(f"Rs.{ca:.2f}",align="RIGHT")]
    ], colWidths=[55*mm,35*mm,20*mm,20*mm,35*mm])
    ct.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),4)]))
    s.append(ct)
    s.append(Spacer(1,3*mm))

    # Tax summary
    td = [[p("Commission (excl. GST)"), p(f"Rs.{ca:.2f}",align="RIGHT")]]
    if interstate:
        td.append([p("IGST @ 18% on commission"), p(f"Rs.{igst:.2f}",align="RIGHT")])
    else:
        td.append([p("CGST @ 9% on commission"), p(f"Rs.{cgst:.2f}",align="RIGHT")])
        td.append([p("SGST @ 9% on commission"), p(f"Rs.{sgst:.2f}",align="RIGHT")])
    td.append([p("<b>Total commission payable</b>",bold=True,size=10,color=BLUE), p(f"<b>Rs.{total:.2f}</b>",bold=True,size=10,color=BLUE,align="RIGHT")])
    tt = Table(td, colWidths=[130*mm,40*mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("LINEABOVE",(0,-1),(-1,-1),1,BLUE),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#eff6ff")),("PADDING",(0,0),(-1,-1),4)]))
    s.append(tt)
    s.append(Spacer(1,2*mm))
    s.append(p(f"Amount in words: {amount_in_words(total)}", color=GRAY, size=7))
    s.append(Spacer(1,4*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    tax_note = "GST of 18% (IGST)" if interstate else "GST of 18% (CGST 9% + SGST 9%)"
    for n in [
        "This commission is charged by Univerin Private Limited for marketplace services rendered per order.",
        f"{tax_note} is applicable on commission as per SAC 998599.",
        "Commission will be deducted from your order settlement.",
        "This is a computer-generated invoice and does not require a physical signature.",
        "For disputes: contact@univerin.in | Ph: 9000869619"
    ]:
        s.append(p("• "+n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(p("Univerin Private Limited | GSTIN: 37AADCU8846J1ZP | contact@univerin.in | 9000869619", color=GRAY, align="CENTER", size=7))
    s.append(p("Powering your local business.", bold=True, color=BLUE, align="CENTER"))
    doc.build(s)
    buf.seek(0)
    return buf

def generate_settlement_statement(vendor, period_start, period_end):
    """Doc 6 — Settlement Statement with TCS 0.5% and TDS 194-O 1%"""
    from orders.models import Order
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from io import BytesIO
    from datetime import datetime, timedelta
    from decimal import Decimal
    from .tax_utils import calc_gst, calc_tcs, calc_tds_194o, is_interstate, get_state_code, PLATFORM_STATE, PLATFORM_GSTIN, amount_in_words
    from .models import InvoiceSequence

    BLUE  = colors.HexColor("#2563eb")
    DARK  = colors.HexColor("#111827")
    GRAY  = colors.HexColor("#6b7280")
    LIGHT = colors.HexColor("#f3f4f6")
    GREEN = colors.HexColor("#16a34a")
    RED   = colors.HexColor("#dc2626")

    def p(text, font="Helvetica", size=8, color=None, align="LEFT", bold=False):
        fn = "Helvetica-Bold" if bold else font
        al = {"LEFT":0,"CENTER":1,"RIGHT":2}.get(align,0)
        return Paragraph(text, ParagraphStyle("s", fontName=fn, fontSize=size, textColor=color or DARK, alignment=al, leading=size+3))

    orders = Order.objects.filter(
        vendor=vendor, status="delivered",
        created_at__date__gte=period_start,
        created_at__date__lte=period_end
    ).prefetch_related("items__product").order_by("created_at")

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)
    s = []
    today     = datetime.now()
    fy        = "2526"
    stmt_no   = InvoiceSequence.next_number("UNV-SS", fy)
    pay_date  = (period_end + timedelta(days=3)).strftime("%d %b %Y")

    vendor_state = getattr(vendor, "state", PLATFORM_STATE) or PLATFORM_STATE
    sg = getattr(vendor, "gstin", None) or "N/A"
    sp = getattr(vendor, "pan",   None) or "N/A"
    sb = getattr(vendor, "bank_name",           "State Bank of India") or "State Bank of India"
    sa = getattr(vendor, "bank_account_number", "XXXX XXXX 0000")      or "XXXX XXXX 0000"
    si = getattr(vendor, "bank_ifsc_code",      "SBIN0000000")         or "SBIN0000000"

    # Header
    left  = p('<b><font color="#2563eb" size="22">Univerin</font></b>', size=22)
    right = p(f'<b>SETTLEMENT STATEMENT</b><br/><font size="8" color="#6b7280">No: {stmt_no}</font><br/><font size="8" color="#6b7280">Date: {today.strftime("%d %b %Y")}</font><br/><font size="8" color="#6b7280">Cycle: Weekly</font><br/><font size="8" color="#6b7280">Period: {period_start.strftime("%d %b %Y")} to {period_end.strftime("%d %b %Y")}</font><br/><font size="8" color="#6b7280">Payment date: {pay_date}</font>', size=10, align='RIGHT')
    ht = Table([[left, right]], colWidths=[90*mm, 90*mm])
    ht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),0.5,colors.HexColor("#e5e7eb"))]))
    s.append(ht)
    s.append(Spacer(1,3*mm))
    s.append(p("Hyperlocal Marketplace — Seller Settlement Statement", color=GRAY, align="CENTER"))
    s.append(Spacer(1,4*mm))

    # Parties
    pd = [
        [p("<b>Settled by (Univerin)</b>",bold=True), p("<b>Settled to (Seller)</b>",bold=True)],
        [p(f"Univerin Private Limited<br/>4/11, Sankarapuram, Govindampalli,<br/>Obulavaripalle - 516105, AP<br/>GSTIN: {PLATFORM_GSTIN}<br/>contact@univerin.in | Ph: 9000869619"),
         p(f"{vendor.shop_name}<br/>GSTIN: {sg}<br/>PAN: {sp}<br/>Category: {vendor.category or 'N/A'}<br/>Bank: {sb} | A/C: {sa}<br/>IFSC: {si}")]
    ]
    pt = Table(pd, colWidths=[90*mm,90*mm])
    pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)]))
    s.append(pt)
    s.append(Spacer(1,4*mm))

    # Calculate totals with new TCS 0.5% and TDS 194-O 1%
    gross        = Decimal("0")
    t_comm       = Decimal("0")
    t_comm_gst   = Decimal("0")
    t_gst_tcs    = Decimal("0")
    t_tds        = Decimal("0")

    order_rows = []
    for o in orders:
        ov        = Decimal(str(o.subtotal or 0))
        comm_base = Decimal(str(o.commission_amount or 0))
        comm_cgst, comm_sgst, comm_igst = calc_gst(comm_base, 18, PLATFORM_STATE, vendor_state)
        comm_gst  = comm_cgst + comm_sgst + comm_igst
        comm_total = comm_base + comm_gst
        cgst_tcs, sgst_tcs, igst_tcs = calc_tcs(ov, vendor_state, PLATFORM_STATE)
        gst_tcs   = cgst_tcs + sgst_tcs + igst_tcs
        tds       = calc_tds_194o(ov)
        ded       = comm_total + gst_tcs + tds
        net_o     = ov - ded

        gross      += ov
        t_comm     += comm_base
        t_comm_gst += comm_gst
        t_gst_tcs  += gst_tcs
        t_tds      += tds
        order_rows.append((o, ov, comm_base, comm_gst, gst_tcs, tds, ded, net_o))

    t_comm_total = t_comm + t_comm_gst
    t_ded        = t_comm_total + t_gst_tcs + t_tds
    net          = gross - t_ded

    # Summary boxes
    sb_data = [[
        Table([[p("Gross order value",color=GRAY,size=7,align="CENTER")],[p(f"Rs.{gross:.2f}",bold=True,size=14,align="CENTER")]],colWidths=[55*mm]),
        Table([[p("Total deductions",color=GRAY,size=7,align="CENTER")],[p(f"Rs.{t_ded:.2f}",bold=True,size=14,align="CENTER")]],colWidths=[55*mm]),
        Table([[p("Net payout to seller",color=GRAY,size=7,align="CENTER")],[p(f"Rs.{net:.2f}",bold=True,size=14,color=GREEN,align="CENTER")]],colWidths=[55*mm]),
    ]]
    sbt = Table(sb_data, colWidths=[60*mm,60*mm,60*mm])
    sbt.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    s.append(sbt)
    s.append(Spacer(1,4*mm))

    # Order breakdown
    s.append(p("<b>Order-wise breakdown</b>",bold=True,size=9))
    s.append(Spacer(1,2*mm))
    rows = [[p("<b>Order ID</b>",bold=True),p("<b>Date</b>",bold=True),p("<b>Order value</b>",bold=True,align="RIGHT"),p("<b>Commission</b>",bold=True,align="RIGHT"),p("<b>GST TCS 0.5%</b>",bold=True,align="RIGHT"),p("<b>TDS 194-O 1%</b>",bold=True,align="RIGHT"),p("<b>Net payout</b>",bold=True,align="RIGHT")]]
    for o, ov, comm_base, comm_gst, gst_tcs, tds, ded, net_o in order_rows:
        rows.append([
            p(str(o.id)[:12].upper()),
            p(o.created_at.strftime("%d %b %Y"),align="CENTER"),
            p(f"Rs.{ov:.2f}",align="RIGHT"),
            p(f"Rs.{comm_base:.2f}",align="RIGHT"),
            p(f"Rs.{gst_tcs:.2f}",align="RIGHT"),
            p(f"Rs.{tds:.2f}",align="RIGHT"),
            p(f"Rs.{net_o:.2f}",align="RIGHT"),
        ])
    rows.append([
        p("<b>Total</b>",bold=True),p(""),
        p(f"<b>Rs.{gross:.2f}</b>",bold=True,align="RIGHT"),
        p(f"<b>Rs.{t_comm:.2f}</b>",bold=True,align="RIGHT"),
        p(f"<b>Rs.{t_gst_tcs:.2f}</b>",bold=True,align="RIGHT"),
        p(f"<b>Rs.{t_tds:.2f}</b>",bold=True,align="RIGHT"),
        p(f"<b>Rs.{net:.2f}</b>",bold=True,align="RIGHT"),
    ])
    ot = Table(rows, colWidths=[32*mm,22*mm,25*mm,25*mm,25*mm,25*mm,26*mm])
    ot.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#f0fdf4")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),3),("FONTSIZE",(0,0),(-1,-1),7)]))
    s.append(ot)
    s.append(Spacer(1,4*mm))

    # Summary breakdown
    sd = [
        [p("Gross order value (products excl. GST)"), p(f"Rs.{gross:.2f}",align="RIGHT")],
        [p(f"Commission charged ({vendor.category or ''})"), p(f"Rs.{t_comm:.2f}",align="RIGHT")],
        [p("GST on commission (18%)"), p(f"Rs.{t_comm_gst:.2f}",align="RIGHT")],
        [p("GST TCS deducted (0.5%)"), p(f"Rs.{t_gst_tcs:.2f}",align="RIGHT")],
        [p("TDS u/s 194-O deducted (1%)"), p(f"Rs.{t_tds:.2f}",align="RIGHT")],
        [p("Total deductions"), p(f"Rs.{t_ded:.2f}",align="RIGHT")],
        [p("<b>Net payout to seller</b>",bold=True,size=10,color=GREEN), p(f"<b>Rs.{net:.2f}</b>",bold=True,size=10,color=GREEN,align="RIGHT")],
    ]
    st = Table(sd, colWidths=[130*mm,40*mm], hAlign="RIGHT")
    st.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("LINEABOVE",(0,-1),(-1,-1),1,GREEN),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#f0fdf4")),("PADDING",(0,0),(-1,-1),4)]))
    s.append(st)
    s.append(Spacer(1,4*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    for n in [
        f"Commission is charged per order based on seller category. Groceries: 6%, Vegetables: 3%, Restaurant/Bakery/FastFood: 20%.",
        "GST on commission is 18% (CGST 9% + SGST 9%) charged by Univerin on the commission amount.",
        "GST TCS @ 0.5% (CGST 0.25% + SGST 0.25%) is deducted as per Section 52 of CGST Act, 2017 (w.e.f. 10-Jul-2024).",
        "TDS u/s 194-O @ 1% is deducted as per Income Tax Act on gross sale value.",
        "This is a computer-generated statement and does not require a physical signature.",
        "For disputes: contact@univerin.in | Ph: 9000869619"
    ]:
        s.append(p("• "+n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(p(f"Univerin Private Limited | GSTIN: {PLATFORM_GSTIN} | contact@univerin.in | 9000869619", color=GRAY, align="CENTER", size=7))
    s.append(p("Powering your local business.", bold=True, color=BLUE, align="CENTER"))
    doc.build(s)
    buf.seek(0)
    return buf

def generate_tcs_certificate(vendor, quarter_start, quarter_end, quarter_name):
    """Doc 6 — TCS Certificate with 0.5% rate (w.e.f. 10-Jul-2024)"""
    from orders.models import Order
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from io import BytesIO
    from datetime import datetime
    from decimal import Decimal
    from .tax_utils import calc_tcs, is_interstate, PLATFORM_STATE, PLATFORM_GSTIN
    from .models import InvoiceSequence

    BLUE  = colors.HexColor("#2563eb")
    DARK  = colors.HexColor("#111827")
    GRAY  = colors.HexColor("#6b7280")
    LIGHT = colors.HexColor("#f3f4f6")
    GREEN = colors.HexColor("#16a34a")

    def p(text, font="Helvetica", size=8, color=None, align="LEFT", bold=False):
        fn = "Helvetica-Bold" if bold else font
        al = {"LEFT":0,"CENTER":1,"RIGHT":2}.get(align,0)
        return Paragraph(text, ParagraphStyle("s", fontName=fn, fontSize=size, textColor=color or DARK, alignment=al, leading=size+3))

    orders = Order.objects.filter(
        vendor=vendor, status="delivered",
        created_at__date__gte=quarter_start,
        created_at__date__lte=quarter_end
    ).order_by("created_at")

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)
    s = []
    today    = datetime.now()
    fy       = "2526"
    cert_no  = InvoiceSequence.next_number(f"UNV-TCS-{quarter_name}", fy)
    vendor_state = getattr(vendor, "state", PLATFORM_STATE) or PLATFORM_STATE
    sg = getattr(vendor, "gstin", None) or "N/A"
    sp = getattr(vendor, "pan",   None) or "N/A"
    interstate = is_interstate(vendor_state, PLATFORM_STATE)

    left  = p('<b><font color="#2563eb" size="22">Univerin</font></b>', size=22)
    right = p(f'<b>TCS CERTIFICATE</b><br/><font size="8" color="#6b7280">Certificate No: {cert_no}</font><br/><font size="8" color="#6b7280">Issue Date: {today.strftime("%d %b %Y")}</font><br/><font size="8" color="#6b7280">Quarter: {quarter_name}</font><br/><font size="8" color="#6b7280">Period: {quarter_start.strftime("%d %b %Y")} to {quarter_end.strftime("%d %b %Y")}</font><br/><font size="8" color="#6b7280">u/s 52 of CGST Act, 2017</font>', size=10, align='RIGHT')
    ht = Table([[left, right]], colWidths=[90*mm, 90*mm])
    ht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),0.5,colors.HexColor("#e5e7eb"))]))
    s.append(ht)
    s.append(Spacer(1,3*mm))
    s.append(p("Tax Collected at Source — E-Commerce Operator Certificate", color=GRAY, align="CENTER"))
    s.append(Spacer(1,4*mm))

    pd = [
        [p("<b>Collector (E-Commerce Operator)</b>",bold=True), p("<b>Collectee (Seller)</b>",bold=True)],
        [p(f"Univerin Private Limited<br/>4/11, Sankarapuram, Govindampalli,<br/>Obulavaripalle - 516105, AP<br/>GSTIN: {PLATFORM_GSTIN}<br/>PAN: AADCU8846J<br/>TAN: HYDV12345A<br/>contact@univerin.in | Ph: 9000869619"),
         p(f"{vendor.shop_name}<br/>GSTIN: {sg}<br/>PAN: {sp}<br/>Category: {vendor.category or 'N/A'}")]
    ]
    pt = Table(pd, colWidths=[90*mm,90*mm])
    pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)]))
    s.append(pt)
    s.append(Spacer(1,4*mm))

    total_taxable = Decimal("0")
    total_cgst_tcs = Decimal("0")
    total_sgst_tcs = Decimal("0")
    total_igst_tcs = Decimal("0")
    order_rows = []

    for o in orders:
        ov = Decimal(str(o.subtotal or 0))
        cgst_tcs, sgst_tcs, igst_tcs = calc_tcs(ov, vendor_state, PLATFORM_STATE)
        tcs_total = cgst_tcs + sgst_tcs + igst_tcs
        total_taxable  += ov
        total_cgst_tcs += cgst_tcs
        total_sgst_tcs += sgst_tcs
        total_igst_tcs += igst_tcs
        order_rows.append((o, ov, cgst_tcs, sgst_tcs, igst_tcs, tcs_total))

    total_tcs = total_cgst_tcs + total_sgst_tcs + total_igst_tcs
    tcs_rate_text = "0.5% IGST" if interstate else "0.5% (CGST 0.25% + SGST 0.25%)"

    sb_data = [[
        Table([[p("Total taxable value",color=GRAY,size=7,align="CENTER")],[p(f"Rs.{total_taxable:.2f}",bold=True,size=14,align="CENTER")]],colWidths=[55*mm]),
        Table([[p("TCS rate",color=GRAY,size=7,align="CENTER")],[p(tcs_rate_text,bold=True,size=9,align="CENTER")]],colWidths=[55*mm]),
        Table([[p("Total TCS collected",color=GRAY,size=7,align="CENTER")],[p(f"Rs.{total_tcs:.2f}",bold=True,size=14,color=GREEN,align="CENTER")]],colWidths=[55*mm]),
    ]]
    sbt = Table(sb_data, colWidths=[60*mm,60*mm,60*mm])
    sbt.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),8)]))
    s.append(sbt)
    s.append(Spacer(1,4*mm))

    s.append(p("<b>Order-wise TCS breakdown</b>",bold=True,size=9))
    s.append(Spacer(1,2*mm))
    if interstate:
        hdr = [p("<b>Order ID</b>",bold=True),p("<b>Order date</b>",bold=True),p("<b>Taxable value</b>",bold=True,align="RIGHT"),p("<b>TCS rate</b>",bold=True,align="CENTER"),p("<b>IGST TCS</b>",bold=True,align="RIGHT"),p("<b>TCS amount</b>",bold=True,align="RIGHT")]
        cw  = [38*mm,28*mm,32*mm,20*mm,32*mm,30*mm]
    else:
        hdr = [p("<b>Order ID</b>",bold=True),p("<b>Order date</b>",bold=True),p("<b>Taxable value</b>",bold=True,align="RIGHT"),p("<b>TCS rate</b>",bold=True,align="CENTER"),p("<b>CGST TCS</b>",bold=True,align="RIGHT"),p("<b>SGST TCS</b>",bold=True,align="RIGHT"),p("<b>TCS amount</b>",bold=True,align="RIGHT")]
        cw  = [32*mm,24*mm,28*mm,16*mm,22*mm,22*mm,26*mm]
    rows = [hdr]
    for o, ov, cgst_tcs, sgst_tcs, igst_tcs, tcs_total in order_rows:
        if interstate:
            rows.append([p(str(o.id)[:12].upper()),p(o.created_at.strftime("%d %b %Y"),align="CENTER"),p(f"Rs.{ov:.2f}",align="RIGHT"),p("0.5%",align="CENTER"),p(f"Rs.{igst_tcs:.2f}",align="RIGHT"),p(f"Rs.{tcs_total:.2f}",align="RIGHT")])
        else:
            rows.append([p(str(o.id)[:12].upper()),p(o.created_at.strftime("%d %b %Y"),align="CENTER"),p(f"Rs.{ov:.2f}",align="RIGHT"),p("0.5%",align="CENTER"),p(f"Rs.{cgst_tcs:.2f}",align="RIGHT"),p(f"Rs.{sgst_tcs:.2f}",align="RIGHT"),p(f"Rs.{tcs_total:.2f}",align="RIGHT")])
    if interstate:
        rows.append([p("<b>Total</b>",bold=True),p(""),p(f"<b>Rs.{total_taxable:.2f}</b>",bold=True,align="RIGHT"),p(""),p(f"<b>Rs.{total_igst_tcs:.2f}</b>",bold=True,align="RIGHT"),p(f"<b>Rs.{total_tcs:.2f}</b>",bold=True,align="RIGHT")])
    else:
        rows.append([p("<b>Total</b>",bold=True),p(""),p(f"<b>Rs.{total_taxable:.2f}</b>",bold=True,align="RIGHT"),p(""),p(f"<b>Rs.{total_cgst_tcs:.2f}</b>",bold=True,align="RIGHT"),p(f"<b>Rs.{total_sgst_tcs:.2f}</b>",bold=True,align="RIGHT"),p(f"<b>Rs.{total_tcs:.2f}</b>",bold=True,align="RIGHT")])
    ot = Table(rows, colWidths=cw)
    ot.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#f0fdf4")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),3),("FONTSIZE",(0,0),(-1,-1),7)]))
    s.append(ot)
    s.append(Spacer(1,4*mm))

    sd = [[p("Total taxable value (quarter)"), p(f"Rs.{total_taxable:.2f}",align="RIGHT")]]
    if interstate:
        sd.append([p("IGST TCS @ 0.5%"), p(f"Rs.{total_igst_tcs:.2f}",align="RIGHT")])
    else:
        sd.append([p("CGST TCS @ 0.25%"), p(f"Rs.{total_cgst_tcs:.2f}",align="RIGHT")])
        sd.append([p("SGST TCS @ 0.25%"), p(f"Rs.{total_sgst_tcs:.2f}",align="RIGHT")])
    sd.append([p("<b>Total TCS collected & remitted</b>",bold=True,color=GREEN), p(f"<b>Rs.{total_tcs:.2f}</b>",bold=True,color=GREEN,align="RIGHT")])
    st = Table(sd, colWidths=[130*mm,40*mm], hAlign="RIGHT")
    st.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("LINEABOVE",(0,-1),(-1,-1),1,GREEN),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#f0fdf4")),("PADDING",(0,0),(-1,-1),4)]))
    s.append(st)
    s.append(Spacer(1,4*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(p("<b>How to claim this TCS credit</b>", bold=True, size=8))
    for n in [
        "The TCS amount shown above has been deposited with the Government by Univerin Private Limited.",
        f"This amount will reflect in your GSTR-2A / GSTR-2B for {quarter_name} after GSTR-8 is filed.",
        "You can claim this TCS as a credit against your GST liability while filing your GSTR-3B.",
        f"Reference this certificate number ({cert_no}) for any disputes or reconciliation.",
        "TCS rate: 0.5% as per Notification 15/2024 (Central Tax) w.e.f. 10-Jul-2024.",
        "This is a computer-generated certificate and does not require a physical signature.",
        "For queries: contact@univerin.in | Ph: 9000869619"
    ]:
        s.append(p("• "+n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(p(f"Univerin Private Limited | GSTIN: {PLATFORM_GSTIN} | PAN: AADCU8846J | TAN: HYDV12345A", color=GRAY, align="CENTER", size=7))
    s.append(p("Powering your local business.", bold=True, color=BLUE, align="CENTER"))
    doc.build(s)
    buf.seek(0)
    return buf

def generate_seller_dashboard_invoice(order):
    """Doc 2 — Seller Tax Invoice (GST compliant with CGST/SGST or IGST)"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from io import BytesIO
    from datetime import datetime
    from decimal import Decimal
    from .tax_utils import calc_gst, is_interstate, get_state_code, PLATFORM_STATE, PLATFORM_GSTIN, amount_in_words
    from .models import InvoiceSequence

    BLUE  = colors.HexColor("#2563eb")
    DARK  = colors.HexColor("#111827")
    GRAY  = colors.HexColor("#6b7280")
    LIGHT = colors.HexColor("#f3f4f6")
    GREEN = colors.HexColor("#16a34a")
    RED   = colors.HexColor("#dc2626")

    def p(text, font="Helvetica", size=8, color=None, align="LEFT", bold=False):
        fn = "Helvetica-Bold" if bold else font
        al = {"LEFT":0,"CENTER":1,"RIGHT":2}.get(align,0)
        return Paragraph(text, ParagraphStyle("s", fontName=fn, fontSize=size, textColor=color or DARK, alignment=al, leading=size+3))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)
    s = []

    vendor       = order.vendor
    buyer        = order.buyer
    vendor_state = getattr(vendor, "state", PLATFORM_STATE) or PLATFORM_STATE
    # Get buyer state from delivery address
    buyer_state  = PLATFORM_STATE
    try:
        addr = buyer.addresses.filter(is_default=True).first() or buyer.addresses.first()
        if addr and addr.state:
            buyer_state = addr.state
    except:
        pass

    interstate   = is_interstate(vendor_state, buyer_state)
    vendor_sc    = get_state_code(vendor_state)
    buyer_sc     = get_state_code(buyer_state)
    sg           = getattr(vendor, "gstin", None) or "N/A"
    sp           = getattr(vendor, "pan", None) or "N/A"
    order_date   = order.created_at.strftime("%d %b %Y")
    fy           = "2526"

    # Generate sequential invoice number
    seller_code  = vendor.shop_name[:3].upper()
    inv_no       = InvoiceSequence.next_number(f"{seller_code}-SI", fy)

    # Header
    left  = p(f'<b><font color="#2563eb" size="16">{vendor.shop_name}</font></b>', size=16)
    right = p(f'<b>TAX INVOICE</b><br/><font size="8" color="#6b7280">Invoice #: {inv_no}</font><br/><font size="8" color="#6b7280">Date: {order_date}</font><br/><font size="8" color="#6b7280">Order #: {order.order_number}</font>', size=10, align='RIGHT')
    ht = Table([[left, right]], colWidths=[90*mm, 90*mm])
    ht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),0.5,colors.HexColor("#e5e7eb"))]))
    s.append(ht)
    s.append(Spacer(1,3*mm))

    pos_text = f"Place of supply: {buyer_state} ({buyer_sc}) | Reverse charge: No"
    s.append(p(pos_text, color=GRAY, align="CENTER", size=7))
    s.append(Spacer(1,4*mm))

    # Parties
    bn = getattr(buyer, 'full_name', None) or buyer.phone_number
    pd = [
        [p("<b>Supplier (Seller)</b>", bold=True), p("<b>Recipient (Buyer)</b>", bold=True)],
        [p(f"{vendor.shop_name}<br/>{vendor.address or vendor.town}<br/>State: {vendor_state} ({vendor_sc})<br/>GSTIN: {sg}<br/>PAN: {sp}"),
         p(f"{bn}<br/>Ph: {buyer.phone_number}<br/>{order.delivery_address or 'N/A'}<br/>State: {buyer_state} ({buyer_sc})")]
    ]
    pt = Table(pd, colWidths=[90*mm,90*mm])
    pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)]))
    s.append(pt)
    s.append(Spacer(1,4*mm))

    # Items table
    s.append(p("<b>Goods supplied</b>", bold=True, size=9))
    s.append(Spacer(1,2*mm))

    if interstate:
        headers = [p("<b>Item</b>",bold=True), p("<b>HSN</b>",bold=True,align="CENTER"), p("<b>Qty</b>",bold=True,align="CENTER"), p("<b>Rate</b>",bold=True,align="RIGHT"), p("<b>Taxable</b>",bold=True,align="RIGHT"), p("<b>GST%</b>",bold=True,align="CENTER"), p("<b>IGST</b>",bold=True,align="RIGHT"), p("<b>Total</b>",bold=True,align="RIGHT")]
        col_widths = [45*mm,16*mm,12*mm,22*mm,22*mm,12*mm,20*mm,22*mm]
    else:
        headers = [p("<b>Item</b>",bold=True), p("<b>HSN</b>",bold=True,align="CENTER"), p("<b>Qty</b>",bold=True,align="CENTER"), p("<b>Rate</b>",bold=True,align="RIGHT"), p("<b>Taxable</b>",bold=True,align="RIGHT"), p("<b>GST%</b>",bold=True,align="CENTER"), p("<b>CGST</b>",bold=True,align="RIGHT"), p("<b>SGST</b>",bold=True,align="RIGHT"), p("<b>Total</b>",bold=True,align="RIGHT")]
        col_widths = [40*mm,14*mm,10*mm,18*mm,18*mm,10*mm,16*mm,16*mm,18*mm]

    rows = [headers]
    subtotal = Decimal("0")
    total_cgst = Decimal("0")
    total_sgst = Decimal("0")
    total_igst = Decimal("0")

    for item in order.items.all():
        pr       = Decimal(str(item.price))
        taxable  = pr * item.quantity
        gst_pct  = Decimal(str(item.product.gst_percentage or 0))
        hsn      = getattr(item.product, 'hsn_code', None) or '—'
        cgst, sgst, igst = calc_gst(taxable, gst_pct, vendor_state, buyer_state)
        total_line = taxable + cgst + sgst + igst
        subtotal   += taxable
        total_cgst += cgst
        total_sgst += sgst
        total_igst += igst

        if interstate:
            rows.append([p(item.product.name), p(hsn,align="CENTER"), p(str(item.quantity),align="CENTER"), p(f"Rs.{pr:.2f}",align="RIGHT"), p(f"Rs.{taxable:.2f}",align="RIGHT"), p(f"{gst_pct:.0f}%",align="CENTER"), p(f"Rs.{igst:.2f}",align="RIGHT"), p(f"Rs.{total_line:.2f}",align="RIGHT")])
        else:
            rows.append([p(item.product.name), p(hsn,align="CENTER"), p(str(item.quantity),align="CENTER"), p(f"Rs.{pr:.2f}",align="RIGHT"), p(f"Rs.{taxable:.2f}",align="RIGHT"), p(f"{gst_pct:.0f}%",align="CENTER"), p(f"Rs.{cgst:.2f}",align="RIGHT"), p(f"Rs.{sgst:.2f}",align="RIGHT"), p(f"Rs.{total_line:.2f}",align="RIGHT")])

    it = Table(rows, colWidths=col_widths)
    it.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),4)]))
    s.append(it)
    s.append(Spacer(1,3*mm))

    # Tax summary
    invoice_total = subtotal + total_cgst + total_sgst + total_igst
    td = [[p("<b>Taxable value</b>",bold=True), p(f"Rs.{subtotal:.2f}",align="RIGHT")]]
    if interstate:
        td.append([p(f"IGST"), p(f"Rs.{total_igst:.2f}",align="RIGHT")])
    else:
        td.append([p(f"CGST"), p(f"Rs.{total_cgst:.2f}",align="RIGHT")])
        td.append([p(f"SGST"), p(f"Rs.{total_sgst:.2f}",align="RIGHT")])
    td.append([p("<b>Invoice Total</b>",bold=True,size=10,color=BLUE), p(f"<b>Rs.{invoice_total:.2f}</b>",bold=True,size=10,color=BLUE,align="RIGHT")])
    tt = Table(td, colWidths=[130*mm,40*mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("LINEABOVE",(0,-1),(-1,-1),1,BLUE),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#eff6ff")),("PADDING",(0,0),(-1,-1),4)]))
    s.append(tt)
    s.append(Spacer(1,2*mm))
    s.append(p(f"Amount in words: {amount_in_words(invoice_total)}", color=GRAY, size=7))
    s.append(Spacer(1,4*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(Spacer(1,2*mm))
    for n in [
        f"This is a tax invoice issued by {vendor.shop_name} for goods supplied.",
        f"GSTIN of supplier: {sg} | State: {vendor_state} ({vendor_sc})",
        "This is a computer-generated invoice and does not require a physical signature.",
        "For queries: contact@univerin.in | Ph: 9000869619"
    ]:
        s.append(p("• "+n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(p(f"{vendor.shop_name} | GSTIN: {sg} | Powered by Univerin", color=GRAY, align="CENTER", size=7))
    s.append(p("Powering your local business.", bold=True, color=BLUE, align="CENTER"))
    doc.build(s)
    buf.seek(0)
    return buf

def generate_platform_invoice(order):
    """Platform Invoice — Univerin charges to buyer"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from io import BytesIO
    from datetime import datetime
    from decimal import Decimal

    BLUE  = colors.HexColor("#2563eb")
    DARK  = colors.HexColor("#111827")
    GRAY  = colors.HexColor("#6b7280")
    LIGHT = colors.HexColor("#f3f4f6")

    def p(text, font="Helvetica", size=8, color=None, align="LEFT", bold=False):
        fn = "Helvetica-Bold" if bold else font
        al = {"LEFT":0,"CENTER":1,"RIGHT":2}.get(align,0)
        return Paragraph(text, ParagraphStyle("s", fontName=fn, fontSize=size, textColor=color or DARK, alignment=al, leading=size+3))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)
    s = []
    today = datetime.now()
    inv_no = f"PINV/{today.year}-{str(today.year+1)[-2:]}/{str(order.id)[:6].upper()}"
    order_date = order.created_at.strftime("%d %b %Y")
    buyer = order.buyer

    left  = p('<b><font color="#2563eb" size="22">Univerin</font></b>', size=22)
    right = p(f'<b>PLATFORM INVOICE</b><br/><font size="8" color="#6b7280">Invoice No: {inv_no}</font><br/><font size="8" color="#6b7280">Date: {order_date}</font><br/><font size="8" color="#6b7280">Order ID: {str(order.id)[:12].upper()}</font>', size=10, align='RIGHT')
    ht = Table([[left, right]], colWidths=[90*mm, 90*mm])
    ht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),0.5,colors.HexColor("#e5e7eb"))]))
    s.append(ht)
    s.append(Spacer(1,3*mm))
    s.append(p("Hyperlocal Marketplace — Platform Service Charges", color=GRAY, align="CENTER"))
    s.append(Spacer(1,4*mm))

    bn = buyer.full_name or buyer.phone_number
    pd = [
        [p("<b>Billed by (Platform)</b>", bold=True), p("<b>Billed to (Buyer)</b>", bold=True)],
        [p(f"Univerin Private Limited<br/>GSTIN: 37AADCU8846J1ZP<br/>contact@univerin.in | Ph: 9000869619"),
         p(f"{bn}<br/>Ph: {buyer.phone_number}")]
    ]
    pt = Table(pd, colWidths=[90*mm, 90*mm])
    pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)]))
    s.append(pt)
    s.append(Spacer(1,4*mm))

    pf  = Decimal(str(order.platform_fee or 10))
    df  = Decimal(str(order.delivery_fee or 0))
    gst_on_delivery = Decimal(str(order.gst_on_delivery or 0))
    gst_on_platform = Decimal(str(order.gst_on_platform or 0))
    pf_total = pf + gst_on_platform
    df_total = df + gst_on_delivery
    total_platform = pf_total + df_total

    rows = [[p("<b>Description</b>",bold=True), p("<b>Base</b>",bold=True,align="RIGHT"), p("<b>GST 18%</b>",bold=True,align="RIGHT"), p("<b>Total</b>",bold=True,align="RIGHT")]]
    rows.append([p("Platform fee — Marketplace facilitation"), p(f"Rs.{pf:.2f}",align="RIGHT"), p(f"Rs.{gst_on_platform:.2f}",align="RIGHT"), p(f"Rs.{pf_total:.2f}",align="RIGHT")])
    rows.append([p("Delivery fee — Logistics service"), p(f"Rs.{df:.2f}",align="RIGHT"), p(f"Rs.{gst_on_delivery:.2f}",align="RIGHT"), p(f"Rs.{df_total:.2f}",align="RIGHT")])
    ct = Table(rows, colWidths=[80*mm, 30*mm, 30*mm, 30*mm])
    ct.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),5)]))
    s.append(ct)
    s.append(Spacer(1,3*mm))

    td = [
        [p("Platform fee (incl. GST)"), p(f"Rs.{pf_total:.2f}",align="RIGHT")],
        [p("Delivery fee (incl. GST)"), p(f"Rs.{df_total:.2f}",align="RIGHT")],
        [p("<b>Total platform charges</b>",bold=True,size=10,color=BLUE), p(f"<b>Rs.{total_platform:.2f}</b>",bold=True,size=10,color=BLUE,align="RIGHT")],
    ]
    tt = Table(td, colWidths=[130*mm, 40*mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("LINEABOVE",(0,-1),(-1,-1),1,BLUE),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#eff6ff")),("PADDING",(0,0),(-1,-1),5)]))
    s.append(tt)
    s.append(Spacer(1,4*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    for n in ["Platform fee and delivery fee are charged by Univerin Private Limited.", "GST @ 18% (CGST 9% + SGST 9%) on platform and delivery fees as per SAC 998599.", "For queries: contact@univerin.in | Ph: 9000869619"]:
        s.append(p("• "+n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(p("Univerin Private Limited | GSTIN: 37AADCU8846J1ZP | contact@univerin.in | 9000869619", color=GRAY, align="CENTER", size=7))
    s.append(p("Powering your local business.", bold=True, color=BLUE, align="CENTER"))
    doc.build(s)
    buf.seek(0)
    return buf
