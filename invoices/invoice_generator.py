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
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)
    s   = []
    buyer  = order.buyer
    vendor = order.vendor
    bn  = buyer.full_name or buyer.phone_number
    sg  = getattr(vendor, 'gstin', 'N/A') or 'N/A'
    dt  = order.created_at.strftime('%d %b %Y')
    inv = inv_num(order, 'INV')
    pm  = 'COD — Paid' if order.payment_mode == 'cod' else 'Online — Paid'

    # ── Header ──────────────────────────────────────────────────
    left  = _p('<b><font color="#111827" size="18">Univerin</font></b>', size=18)
    right = _p(
        f'<b>TAX INVOICE / ORDER RECEIPT</b><br/>'
        f'<font size="8" color="#6b7280">Invoice: {inv}</font><br/>'
        f'<font size="8" color="#6b7280">Order: #{order.order_number or str(order.id)[:12].upper()}</font><br/>'
        f'<font size="8" color="#6b7280">Invoice date: {dt} &nbsp; Order date: {dt}</font><br/>'
        f'<font size="8" color="#6b7280">Payment: {pm} &nbsp; Status: Delivered</font>',
        size=9, align='RIGHT'
    )
    ht = Table([[left, right]], colWidths=[90*mm, 90*mm])
    ht.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),0.5,colors.HexColor('#e5e7eb'))]))
    s.append(ht)
    s.append(Spacer(1,5*mm))

    # ── Buyer + Seller ──────────────────────────────────────────
    pd = [
        [_p('<b>Buyer details</b>', bold=True, size=8, color=GRAY),
         _p('<b>Seller (supplier of goods)</b>', bold=True, size=8, color=GRAY)],
        [_p(f'{bn}<br/>Ph: {buyer.phone_number}<br/>{order.delivery_address or "N/A"}'),
         _p(f'{vendor.shop_name}<br/>{vendor.address or vendor.town or "N/A"}<br/>GSTIN: {sg}<br/><br/>Goods listed below are supplied by the respective seller.', color=GRAY)]
    ]
    pt = Table(pd, colWidths=[90*mm, 90*mm])
    pt.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),LIGHT),
        ('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),
        ('INNERGRID',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('PADDING',(0,0),(-1,-1),6)
    ]))
    s.append(pt)
    s.append(Spacer(1,4*mm))

    # ── Billed by ───────────────────────────────────────────────
    s.append(_p('<b>Billed / facilitated by</b>', bold=True, size=8, color=GRAY))
    s.append(Spacer(1,2*mm))
    bd = [[
        _p(f'<b>{UNIVERIN["name"]}</b><br/>{UNIVERIN["address"]}<br/>GSTIN: {UNIVERIN["gstin"]}'),
        _p(f'{UNIVERIN["email"]}<br/>Ph: {UNIVERIN["phone"]}', align='RIGHT')
    ]]
    bt = Table(bd, colWidths=[120*mm, 60*mm])
    bt.setStyle(TableStyle([('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),('PADDING',(0,0),(-1,-1),6),('VALIGN',(0,0),(-1,-1),'TOP')]))
    s.append(bt)
    s.append(Spacer(1,4*mm))

    # ── Goods table ─────────────────────────────────────────────
    s.append(_p('<b>Goods supplied by seller</b>', bold=True, size=8, color=GRAY))
    s.append(Spacer(1,2*mm))
    rows = [[
        _p('<b>Item</b>', bold=True),
        _p('<b>Qty</b>', bold=True, align='CENTER'),
        _p('<b>Unit price</b>', bold=True, align='RIGHT'),
        _p('<b>GST</b>', bold=True, align='CENTER'),
        _p('<b>Amount</b>', bold=True, align='RIGHT'),
    ]]
    seller_total = Decimal('0')
    for item in order.items.all():
        pr = Decimal(str(item.price))
        lt = pr * item.quantity
        seller_total += lt
        rows.append([
            _p(item.product.name),
            _p(str(item.quantity), align='CENTER'),
            _p(f'Rs.{pr:.2f}', align='RIGHT'),
            _p('Included', color=GRAY, align='CENTER'),
            _p(f'Rs.{lt:.2f}', align='RIGHT'),
        ])
    it = Table(rows, colWidths=[70*mm, 18*mm, 30*mm, 25*mm, 30*mm])
    it.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),LIGHT),
        ('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),
        ('INNERGRID',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),
        ('PADDING',(0,0),(-1,-1),5)
    ]))
    s.append(it)
    st = Table([[_p('Seller goods total (incl. GST)', bold=True), _p(f'Rs.{seller_total:.2f}', bold=True, align='RIGHT')]], colWidths=[130*mm, 40*mm])
    st.setStyle(TableStyle([('PADDING',(0,0),(-1,-1),5),('LINEABOVE',(0,0),(-1,0),0.5,colors.HexColor('#e5e7eb'))]))
    s.append(st)
    s.append(Spacer(1,4*mm))

    # ── Univerin charges ────────────────────────────────────────
    s.append(_p('<b>Charges by Univerin</b>', bold=True, size=8, color=GRAY))
    s.append(Spacer(1,2*mm))
    df  = Decimal(str(order.delivery_fee or 0))
    pf  = Decimal(str(order.platform_fee or 10))
    pfg = round(float(pf) * 1.18)
    univerin_total = df + pfg
    ch = Table([
        [_p('Delivery fee (incl. GST 18%)<br/>Logistics service by Univerin'), _p(f'Rs.{df:.2f}', align='RIGHT')],
        [_p(f'Platform fee (incl. GST 18%)<br/>Marketplace facilitation by Univerin'), _p(f'Rs.{pfg}', align='RIGHT')],
    ], colWidths=[140*mm, 30*mm])
    ch.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),
        ('INNERGRID',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),
        ('PADDING',(0,0),(-1,-1),6),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
    ]))
    s.append(ch)
    ct = Table([[_p('Univerin charges total (incl. GST)', bold=True), _p(f'Rs.{univerin_total:.2f}', bold=True, align='RIGHT')]], colWidths=[130*mm, 40*mm])
    ct.setStyle(TableStyle([('PADDING',(0,0),(-1,-1),5),('LINEABOVE',(0,0),(-1,0),0.5,colors.HexColor('#e5e7eb'))]))
    s.append(ct)
    s.append(Spacer(1,4*mm))

    # ── Payment summary ─────────────────────────────────────────
    s.append(_p('<b>Payment summary</b>', bold=True, size=8, color=GRAY))
    s.append(Spacer(1,2*mm))
    gt = Decimal(str(order.total_amount))
    td = [
        [_p('Seller goods total'), _p(f'Rs.{seller_total:.2f}', align='RIGHT')],
        [_p('Univerin charges'), _p(f'Rs.{univerin_total:.2f}', align='RIGHT')],
        [_p('<b>Grand total paid</b>', bold=True, size=10), _p(f'<b>Rs.{gt:.2f}</b>', bold=True, size=10, align='RIGHT')],
    ]
    tt = Table(td, colWidths=[130*mm, 40*mm], hAlign='RIGHT')
    tt.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),
        ('LINEABOVE',(0,-1),(-1,-1),1,DARK),
        ('BACKGROUND',(0,-1),(-1,-1),LIGHT),
        ('PADDING',(0,0),(-1,-1),5)
    ]))
    s.append(tt)
    s.append(Spacer(1,5*mm))

    # ── Footer ──────────────────────────────────────────────────
    s.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#e5e7eb')))
    s.append(Spacer(1,2*mm))
    for n in [
        'This is a computer-generated invoice and does not require a physical signature.',
        'Goods are supplied by the respective seller listed above. Univerin is a marketplace facilitator only.',
        'Delivery and platform services are provided by Univerin Private Limited (GSTIN: 37AADCU8846J1ZP).',
        'GST on platform and delivery services is charged by Univerin Private Limited. GST on goods, wherever applicable, belongs to the seller.',
        f'For support: {UNIVERIN["email"]} | Ph: {UNIVERIN["phone"]}',
    ]:
        s.append(_p('• ' + n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#e5e7eb')))
    s.append(_p(f'{UNIVERIN["name"]} | GSTIN: {UNIVERIN["gstin"]} | {UNIVERIN["email"]} | {UNIVERIN["phone"]}', color=GRAY, align='CENTER', size=7))
    s.append(_p('Thank you for shopping with Univerin!', bold=True, color=DARK, align='CENTER'))
    doc.build(s)
    buf.seek(0)
    return buf

def generate_commission_invoice(order):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)
    s = []
    s.append(header_table(order, 'COMMISSION'))
    s.append(Spacer(1,3*mm))
    s.append(_p('Hyperlocal Marketplace', color=GRAY, align='CENTER'))
    s.append(Spacer(1,4*mm))
    vendor = order.vendor
    sg = getattr(vendor,'gstin','N/A') or 'N/A'
    sub  = Decimal(str(order.subtotal or order.total_amount))
    cr   = Decimal(str(order.commission_rate or 6))
    ca   = sub * cr / 100
    cgst = ca * Decimal('0.09')
    sgst = cgst
    total = ca + cgst + sgst
    pd = [
        [_p('<b>From (Univerin)</b>',bold=True), _p('<b>To (Seller)</b>',bold=True)],
        [_p(UNIVERIN['name']+'\n'+UNIVERIN['address']+'\nGSTIN: '+UNIVERIN['gstin']),
         _p(f'{vendor.shop_name}\nGSTIN: {sg}\nCategory: {vendor.category or "N/A"}')]
    ]
    pt = Table(pd, colWidths=[90*mm,90*mm])
    pt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),LIGHT),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),('INNERGRID',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),('VALIGN',(0,0),(-1,-1),'TOP'),('PADDING',(0,0),(-1,-1),5)]))
    s.append(pt)
    s.append(Spacer(1,4*mm))
    ct = Table([
        [_p('<b>Description</b>',bold=True),_p('<b>Order value</b>',bold=True,align='RIGHT'),_p('<b>Rate</b>',bold=True,align='CENTER'),_p('<b>SAC</b>',bold=True,align='CENTER'),_p('<b>Commission</b>',bold=True,align='RIGHT')],
        [_p(f'Commission on {vendor.category or "Groceries"} sales'),_p(f'Rs.{sub:.2f}',align='RIGHT'),_p(f'{cr:.1f}%',align='CENTER'),_p('998599',align='CENTER'),_p(f'Rs.{ca:.2f}',align='RIGHT')]
    ], colWidths=[55*mm,35*mm,25*mm,20*mm,35*mm])
    ct.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),LIGHT),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),('INNERGRID',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),('PADDING',(0,0),(-1,-1),4)]))
    s.append(ct)
    s.append(Spacer(1,3*mm))
    td = [
        [_p('Commission (excl. GST)'), _p(f'Rs.{ca:.2f}',align='RIGHT')],
        [_p('CGST @ 9% on commission'), _p(f'Rs.{cgst:.2f}',align='RIGHT')],
        [_p('SGST @ 9% on commission'), _p(f'Rs.{sgst:.2f}',align='RIGHT')],
        [_p('<b>Total commission payable</b>',bold=True,size=10,color=BLUE), _p(f'<b>Rs.{total:.2f}</b>',bold=True,size=10,color=BLUE,align='RIGHT')],
    ]
    tt = Table(td, colWidths=[130*mm,40*mm], hAlign='RIGHT')
    tt.setStyle(TableStyle([('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),('LINEABOVE',(0,-1),(-1,-1),1,BLUE),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#eff6ff')),('PADDING',(0,0),(-1,-1),4)]))
    s.append(tt)
    s.append(Spacer(1,4*mm))
    s.append(HRFlowable(width='100%',thickness=0.5,color=colors.HexColor('#e5e7eb')))
    for n in ['This commission is charged by Univerin Private Limited for marketplace services rendered per order.','GST of 18% (CGST 9% + SGST 9%) is applicable on commission as per SAC 998599.','Commission will be deducted from your order settlement.',f'For disputes: {UNIVERIN["email"]} | Ph: {UNIVERIN["phone"]}']:
        s.append(_p('• '+n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width='100%',thickness=0.5,color=colors.HexColor('#e5e7eb')))
    s.append(_p(f'{UNIVERIN["name"]} | GSTIN: {UNIVERIN["gstin"]} | {UNIVERIN["email"]} | {UNIVERIN["phone"]}', color=GRAY, align='CENTER', size=7))
    s.append(_p('Powering your local business.', bold=True, color=BLUE, align='CENTER'))
    doc.build(s)
    buf.seek(0)
    return buf


def generate_settlement_statement(vendor, period_start, period_end):
    """Generate Doc 4 — Settlement Statement"""
    from orders.models import Order
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from io import BytesIO
    from datetime import datetime, timedelta
    from decimal import Decimal

    BLUE  = colors.HexColor("#2563eb")
    DARK  = colors.HexColor("#111827")
    GRAY  = colors.HexColor("#6b7280")
    LIGHT = colors.HexColor("#f3f4f6")
    GREEN = colors.HexColor("#16a34a")
    WHITE = colors.white

    def p(text, font="Helvetica", size=8, color=None, align="LEFT", bold=False):
        fn = "Helvetica-Bold" if bold else font
        al = {"LEFT":0,"CENTER":1,"RIGHT":2}.get(align,0)
        return Paragraph(text, ParagraphStyle("s", fontName=fn, fontSize=size, textColor=color or DARK, alignment=al, leading=size+3))

    orders = Order.objects.filter(
        vendor=vendor, status="delivered",
        created_at__date__gte=period_start,
        created_at__date__lte=period_end
    ).order_by("created_at")

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)
    s = []
    today = datetime.now()
    stmt_no = f"SETL/{today.year}-{str(today.year+1)[-2:]}/{str(vendor.id)[:6].upper()}"
    pay_date = (period_end + timedelta(days=3)).strftime("%d %b %Y")

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
    sg = getattr(vendor,"gstin","N/A") or "N/A"
    sp = getattr(vendor,"pan","N/A") or "N/A"
    sb = getattr(vendor,"bank_name","State Bank of India") or "State Bank of India"
    sa = getattr(vendor,"account_number","XXXX XXXX 0000") or "XXXX XXXX 0000"
    si = getattr(vendor,"ifsc_code","SBIN0000000") or "SBIN0000000"
    pd = [
        [p("<b>Settled by (Univerin)</b>",bold=True), p("<b>Settled to (Seller)</b>",bold=True)],
        [p(f"Univerin Private Limited\n4/11, Sankarapuram, Govindampalli, Obulavaripalle - 516105, AP\nGSTIN: 37AADCU8846J1ZP\ncontact@univerin.in | Ph: 9000869619"),
         p(f'{vendor.shop_name}\nGSTIN: {sg}\nPAN: {sp}\nCategory: {vendor.category or "N/A"}\nBank: {sb} | A/C: {sa}\nIFSC: {si}')]
    ]
    pt = Table(pd, colWidths=[90*mm,90*mm])
    pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)]))
    s.append(pt)
    s.append(Spacer(1,4*mm))

    # Summary
    gross = sum(Decimal(str(o.subtotal or 0)) for o in orders)
    t_comm = sum(Decimal(str(o.commission_amount or 0)) for o in orders)
    t_tcs  = sum(Decimal(str(o.tcs_amount or 0)) for o in orders)
    t_ded  = t_comm + t_tcs
    net    = gross - t_ded

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
    rows = [[p("<b>Order ID</b>",bold=True),p("<b>Date</b>",bold=True),p("<b>Order value</b>",bold=True,align="RIGHT"),p("<b>Commission</b>",bold=True,align="RIGHT"),p("<b>TCS 1%</b>",bold=True,align="RIGHT"),p("<b>Deductions</b>",bold=True,align="RIGHT"),p("<b>Net payout</b>",bold=True,align="RIGHT")]]
    t_ov=Decimal("0"); t_net=Decimal("0")
    for o in orders:
        ov   = Decimal(str(o.subtotal or 0))
        comm = Decimal(str(o.commission_amount or 0))
        tcs  = Decimal(str(o.tcs_amount or 0))
        ded  = comm + tcs
        np   = ov - ded
        t_ov += ov; t_net += np
        rows.append([
            p(str(o.id)[:12].upper()),
            p(o.created_at.strftime("%d %b %Y")),
            p(f"Rs.{ov:.2f}",align="RIGHT"),
            p(f"Rs.{comm:.2f}",align="RIGHT"),
            p(f"Rs.{tcs:.2f}",align="RIGHT"),
            p(f"Rs.{ded:.2f}",align="RIGHT"),
            p(f"Rs.{np:.2f}",align="RIGHT"),
        ])
    rows.append([
        p("<b>Total</b>",bold=True),"",
        p(f"<b>Rs.{t_ov:.2f}</b>",bold=True,align="RIGHT"),
        p(f"<b>Rs.{t_comm:.2f}</b>",bold=True,align="RIGHT"),
        p(f"<b>Rs.{t_tcs:.2f}</b>",bold=True,align="RIGHT"),
        p(f"<b>Rs.{t_ded:.2f}</b>",bold=True,align="RIGHT"),
        p(f"<b>Rs.{t_net:.2f}</b>",bold=True,align="RIGHT"),
    ])
    ot = Table(rows, colWidths=[30*mm,22*mm,25*mm,25*mm,20*mm,25*mm,25*mm])
    ot.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),4),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#f0fdf4")),("LINEABOVE",(0,-1),(-1,-1),1,GREEN)]))
    s.append(ot)
    s.append(Spacer(1,4*mm))

    # Totals summary
    td = [
        [p("Gross order value (products excl. GST)"), p(f"Rs.{gross:.2f}",align="RIGHT")],
        [p("Commission charged"), p(f"Rs.{t_comm:.2f}",align="RIGHT")],
        [p("TCS deducted (1%)"), p(f"Rs.{t_tcs:.2f}",align="RIGHT")],
        [p("Total deductions"), p(f"Rs.{t_ded:.2f}",align="RIGHT")],
        [p("<b>Net payout to seller</b>",bold=True,size=10,color=GREEN), p(f"<b>Rs.{net:.2f}</b>",bold=True,size=10,color=GREEN,align="RIGHT")],
    ]
    tt = Table(td, colWidths=[130*mm,40*mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("LINEABOVE",(0,-1),(-1,-1),1,GREEN),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#f0fdf4")),("PADDING",(0,0),(-1,-1),4)]))
    s.append(tt)
    s.append(Spacer(1,4*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(Spacer(1,2*mm))
    for n in [
        "Commission is charged per order based on seller category. Groceries: 6%, Vegetables: 3%, Restaurant/Bakery/FastFood: 20%.",
        "GST on commission is 18% (CGST 9% + SGST 9%) charged by Univerin on the commission amount.",
        "TCS @ 1% (CGST 0.5% + SGST 0.5%) is deducted as per Section 52 of CGST Act, 2017.",
        "For disputes or reconciliation queries: contact@univerin.in | Ph: 9000869619",
    ]:
        s.append(p("• "+n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(p("Univerin Private Limited | GSTIN: 37AADCU8846J1ZP | contact@univerin.in | 9000869619", color=GRAY, align="CENTER", size=7))
    s.append(p("Powering your local business.", bold=True, color=BLUE, align="CENTER"))
    doc.build(s)
    buf.seek(0)
    return buf


def generate_tcs_certificate(vendor, quarter_start, quarter_end, quarter_name):
    """Generate Doc 5 — TCS Certificate"""
    from orders.models import Order
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from io import BytesIO
    from datetime import datetime
    from decimal import Decimal

    BLUE  = colors.HexColor("#2563eb")
    DARK  = colors.HexColor("#111827")
    GRAY  = colors.HexColor("#6b7280")
    LIGHT = colors.HexColor("#f3f4f6")
    WHITE = colors.white

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
    today = datetime.now()
    cert_no = f"TCS/{today.year}-{str(today.year+1)[-2:]}/{quarter_name}/{str(vendor.id)[:6].upper()}"

    # Header
    left  = p('<b><font color="#2563eb" size="22">Univerin</font></b>', size=22)
    right = p(f'<b>TCS CERTIFICATE</b><br/><font size="8" color="#6b7280">Certificate No: {cert_no}</font><br/><font size="8" color="#6b7280">Issue Date: {today.strftime("%d %b %Y")}</font><br/><font size="8" color="#6b7280">Quarter: {quarter_name}</font><br/><font size="8" color="#6b7280">Period: {quarter_start.strftime("%d %b %Y")} to {quarter_end.strftime("%d %b %Y")}</font><br/><font size="8" color="#6b7280">u/s 52 of CGST Act, 2017</font>', size=10, align='RIGHT')
    ht = Table([[left, right]], colWidths=[90*mm, 90*mm])
    ht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),0.5,colors.HexColor("#e5e7eb"))]))
    s.append(ht)
    s.append(Spacer(1,3*mm))
    s.append(p("Tax Collected at Source — E-Commerce Operator Certificate", color=GRAY, align="CENTER"))
    s.append(Spacer(1,4*mm))

    # Parties
    sg = getattr(vendor,"gstin","N/A") or "N/A"
    sp = getattr(vendor,"pan","N/A") or "N/A"
    pd = [
        [p("<b>Collector (E-Commerce Operator)</b>",bold=True), p("<b>Collectee (Seller)</b>",bold=True)],
        [p("Univerin Private Limited\n4/11, Sankarapuram, Govindampalli, Obulavaripalle - 516105, AP\nGSTIN: 37AADCU8846J1ZP\nPAN: AADCU8846J\nTAN: HYDV12345A\ncontact@univerin.in | Ph: 9000869619"),
         p(f'{vendor.shop_name}\nGSTIN: {sg}\nPAN: {sp}\nCategory: {vendor.category or "N/A"}')]
    ]
    pt = Table(pd, colWidths=[90*mm,90*mm])
    pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)]))
    s.append(pt)
    s.append(Spacer(1,4*mm))

    # Summary boxes
    total_taxable = sum(Decimal(str(o.subtotal or 0)) for o in orders)
    total_tcs     = sum(Decimal(str(o.tcs_amount or 0)) for o in orders)
    cgst_tcs      = total_tcs / 2
    sgst_tcs      = total_tcs / 2

    sb_data = [[
        Table([[p("Total taxable value",color=GRAY,size=7,align="CENTER")],[p(f"Rs.{total_taxable:.2f}",bold=True,size=12,align="CENTER")]],colWidths=[55*mm]),
        Table([[p("TCS rate",color=GRAY,size=7,align="CENTER")],[p("1.0% (CGST 0.5% + SGST 0.5%)",bold=True,size=9,align="CENTER")]],colWidths=[55*mm]),
        Table([[p("Total TCS collected",color=GRAY,size=7,align="CENTER")],[p(f"Rs.{total_tcs:.2f}",bold=True,size=12,color=BLUE,align="CENTER")]],colWidths=[55*mm]),
    ]]
    sbt = Table(sb_data, colWidths=[60*mm,60*mm,60*mm])
    sbt.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    s.append(sbt)
    s.append(Spacer(1,4*mm))

    # Order wise TCS breakdown
    s.append(p("<b>Order-wise TCS breakdown</b>",bold=True,size=9))
    s.append(Spacer(1,2*mm))
    rows = [[p("<b>Order ID</b>",bold=True),p("<b>Order date</b>",bold=True),p("<b>Taxable value</b>",bold=True,align="RIGHT"),p("<b>TCS rate</b>",bold=True,align="CENTER"),p("<b>CGST TCS</b>",bold=True,align="RIGHT"),p("<b>SGST TCS</b>",bold=True,align="RIGHT"),p("<b>TCS amount</b>",bold=True,align="RIGHT")]]
    for o in orders:
        ov  = Decimal(str(o.subtotal or 0))
        tcs = Decimal(str(o.tcs_amount or 0))
        rows.append([
            p(str(o.id)[:12].upper()),
            p(o.created_at.strftime("%d %b %Y")),
            p(f"Rs.{ov:.2f}",align="RIGHT"),
            p("1.0%",align="CENTER"),
            p(f"Rs.{tcs/2:.2f}",align="RIGHT"),
            p(f"Rs.{tcs/2:.2f}",align="RIGHT"),
            p(f"Rs.{tcs:.2f}",align="RIGHT"),
        ])
    rows.append([
        p("<b>Total</b>",bold=True),"",
        p(f"<b>Rs.{total_taxable:.2f}</b>",bold=True,align="RIGHT"),"",
        p(f"<b>Rs.{cgst_tcs:.2f}</b>",bold=True,align="RIGHT"),
        p(f"<b>Rs.{sgst_tcs:.2f}</b>",bold=True,align="RIGHT"),
        p(f"<b>Rs.{total_tcs:.2f}</b>",bold=True,align="RIGHT"),
    ])
    ot = Table(rows, colWidths=[30*mm,24*mm,28*mm,18*mm,24*mm,24*mm,24*mm])
    ot.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),4),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#eff6ff")),("LINEABOVE",(0,-1),(-1,-1),1,BLUE)]))
    s.append(ot)
    s.append(Spacer(1,4*mm))

    # Summary totals
    td = [
        [p("Total taxable value (quarter)"), p(f"Rs.{total_taxable:.2f}",align="RIGHT")],
        [p("CGST TCS @ 0.5%"), p(f"Rs.{cgst_tcs:.2f}",align="RIGHT")],
        [p("SGST TCS @ 0.5%"), p(f"Rs.{sgst_tcs:.2f}",align="RIGHT")],
        [p("<b>Total TCS collected & remitted</b>",bold=True,size=10,color=BLUE), p(f"<b>Rs.{total_tcs:.2f}</b>",bold=True,size=10,color=BLUE,align="RIGHT")],
    ]
    tt = Table(td, colWidths=[130*mm,40*mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("LINEABOVE",(0,-1),(-1,-1),1,BLUE),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#eff6ff")),("PADDING",(0,0),(-1,-1),4)]))
    s.append(tt)
    s.append(Spacer(1,4*mm))
    s.append(p("<b>How to claim this TCS credit</b>",bold=True,size=9))
    s.append(Spacer(1,2*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(Spacer(1,2*mm))
    for n in [
        f"The TCS amount shown above has been deposited with the Government by Univerin Private Limited.",
        f"This amount will reflect in your GSTR-2A / GSTR-2B for {quarter_name} after GSTR-8 is filed.",
        "You can claim this TCS as a credit against your GST liability while filing your GSTR-3B.",
        f"Reference this certificate number ({cert_no}) for any disputes or reconciliation.",
        "This certificate is issued under Section 52 of the CGST Act, 2017 read with Rule 67.",
        "This is a computer-generated certificate and does not require a physical signature.",
        "For queries: contact@univerin.in | Ph: 9000869619",
    ]:
        s.append(p("• "+n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(p("Univerin Private Limited | GSTIN: 37AADCU8846J1ZP | PAN: AADCU8846J | TAN: HYDV12345A", color=GRAY, align="CENTER", size=7))
    s.append(p("Powering your local business.", bold=True, color=BLUE, align="CENTER"))
    doc.build(s)
    buf.seek(0)
    return buf


def generate_seller_dashboard_invoice(order):
    """Generate Doc 6 — Seller Dashboard Invoice"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from io import BytesIO
    from datetime import datetime
    from decimal import Decimal

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
    today = datetime.now()
    inv_no = f"SINV/{today.year}-{str(today.year+1)[-2:]}/{str(order.id)[:6].upper()}"
    order_date = order.created_at.strftime("%d %b %Y")
    vendor = order.vendor
    sg = getattr(vendor,"gstin","N/A") or "N/A"

    # Header
    left  = p('<b><font color="#2563eb" size="22">Univerin</font></b>', size=22)
    right = p(f'<b>SELLER DASHBOARD INVOICE</b><br/><font size="8" color="#6b7280">Invoice No: {inv_no}</font><br/><font size="8" color="#6b7280">Date: {order_date}</font><br/><font size="8" color="#6b7280">Order ID: {str(order.id)[:12].upper()}</font>', size=10, align='RIGHT')
    ht = Table([[left, right]], colWidths=[90*mm, 90*mm])
    ht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),0.5,colors.HexColor("#e5e7eb"))]))
    s.append(ht)
    s.append(Spacer(1,3*mm))
    s.append(p("Hyperlocal Marketplace — Seller Order Summary", color=GRAY, align="CENTER"))
    s.append(Spacer(1,4*mm))

    # Seller info
    pd = [
        [p("<b>Platform</b>",bold=True), p("<b>Seller</b>",bold=True)],
        [p("Univerin Private Limited\nGSTIN: 37AADCU8846J1ZP\ncontact@univerin.in | Ph: 9000869619"),
         p(f'{vendor.shop_name}\nGSTIN: {sg}\nCategory: {vendor.category or "N/A"}')]
    ]
    pt = Table(pd, colWidths=[90*mm,90*mm])
    pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),5)]))
    s.append(pt)
    s.append(Spacer(1,4*mm))

    # Items sold
    s.append(p("<b>Items Sold</b>",bold=True,size=9))
    s.append(Spacer(1,2*mm))
    rows = [[p("<b>Item</b>",bold=True),p("<b>Qty</b>",bold=True,align="CENTER"),p("<b>Rate</b>",bold=True,align="RIGHT"),p("<b>Amount</b>",bold=True,align="RIGHT")]]
    subtotal = Decimal("0")
    for item in order.items.all():
        pr = Decimal(str(item.price))
        lt = pr * item.quantity
        subtotal += lt
        rows.append([p(item.product.name),p(str(item.quantity),align="CENTER"),p(f"Rs.{pr:.2f}",align="RIGHT"),p(f"Rs.{lt:.2f}",align="RIGHT")])
    it = Table(rows, colWidths=[80*mm,25*mm,35*mm,32*mm])
    it.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("PADDING",(0,0),(-1,-1),4)]))
    s.append(it)
    s.append(Spacer(1,4*mm))

    # Earnings breakdown
    comm  = Decimal(str(order.commission_amount or 0))
    tcs   = Decimal(str(order.tcs_amount or 0))
    ded   = comm + tcs
    net   = subtotal - ded

    td = [
        [p("Order value (excl. GST)"), p(f"Rs.{subtotal:.2f}",align="RIGHT")],
        [p(f"Commission ({order.commission_rate or 0}%)"), p(f"- Rs.{comm:.2f}",color=RED,align="RIGHT")],
        [p("TCS deducted (1%)"), p(f"- Rs.{tcs:.2f}",color=RED,align="RIGHT")],
        [p("Total deductions"), p(f"- Rs.{ded:.2f}",color=RED,align="RIGHT")],
        [p("<b>Net earnings</b>",bold=True,size=10,color=GREEN), p(f"<b>Rs.{net:.2f}</b>",bold=True,size=10,color=GREEN,align="RIGHT")],
    ]
    tt = Table(td, colWidths=[130*mm,40*mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#e5e7eb")),("LINEABOVE",(0,-1),(-1,-1),1,GREEN),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#f0fdf4")),("PADDING",(0,0),(-1,-1),4)]))
    s.append(tt)
    s.append(Spacer(1,4*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(Spacer(1,2*mm))
    for n in [
        "This is a summary of your earnings for this order.",
        "Net earnings will be settled weekly every Monday.",
        "For queries: contact@univerin.in | Ph: 9000869619",
    ]:
        s.append(p("• "+n, color=GRAY, size=7))
    s.append(Spacer(1,3*mm))
    s.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#e5e7eb")))
    s.append(p("Univerin Private Limited | GSTIN: 37AADCU8846J1ZP | contact@univerin.in | 9000869619", color=GRAY, align="CENTER", size=7))
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
