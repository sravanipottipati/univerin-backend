"""
Univerin Tax Utilities
- CGST/SGST vs IGST logic
- TCS rate (0.5% as per Notification 15/2024 w.e.f. 10-Jul-2024)
- TDS 194-O rate (1%)
- State codes mapping
"""
from decimal import Decimal, ROUND_HALF_UP

# TCS rate reduced from 1% to 0.5% w.e.f. 10-Jul-2024
GST_TCS_RATE    = Decimal("0.005")   # 0.5%
TDS_194O_RATE   = Decimal("0.01")    # 1%

# Indian state codes
STATE_CODES = {
    "Jammu and Kashmir": "01", "Himachal Pradesh": "02",
    "Punjab": "03", "Chandigarh": "04", "Uttarakhand": "05",
    "Haryana": "06", "Delhi": "07", "Rajasthan": "08",
    "Uttar Pradesh": "09", "Bihar": "10", "Sikkim": "11",
    "Arunachal Pradesh": "12", "Nagaland": "13", "Manipur": "14",
    "Mizoram": "15", "Tripura": "16", "Meghalaya": "17",
    "Assam": "18", "West Bengal": "19", "Jharkhand": "20",
    "Odisha": "21", "Chhattisgarh": "22", "Madhya Pradesh": "23",
    "Gujarat": "24", "Dadra and Nagar Haveli": "26",
    "Maharashtra": "27", "Karnataka": "29", "Goa": "30",
    "Lakshadweep": "31", "Kerala": "32", "Tamil Nadu": "33",
    "Puducherry": "34", "Andaman and Nicobar Islands": "35",
    "Telangana": "36", "Andhra Pradesh": "37",
    "Ladakh": "38",
}

PLATFORM_STATE  = "Andhra Pradesh"
PLATFORM_GSTIN  = "37AADCU8846J1ZP"
PLATFORM_STATE_CODE = "37"

def get_state_code(state_name):
    """Get 2-digit state code from state name."""
    return STATE_CODES.get(state_name, "37")

def is_interstate(supplier_state, place_of_supply_state):
    """Check if transaction is inter-state."""
    return supplier_state.strip().lower() != place_of_supply_state.strip().lower()

def calc_gst(taxable_value, gst_rate_pct, supplier_state, place_of_supply_state):
    """
    Calculate GST split based on interstate/intrastate.
    Returns: (cgst, sgst, igst)
    """
    taxable = Decimal(str(taxable_value))
    rate    = Decimal(str(gst_rate_pct)) / 100

    if is_interstate(supplier_state, place_of_supply_state):
        igst = (taxable * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Decimal("0"), Decimal("0"), igst
    else:
        half_rate = rate / 2
        cgst = (taxable * half_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sgst = (taxable * half_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return cgst, sgst, Decimal("0")

def calc_tcs(taxable_value, supplier_state, place_of_supply_state):
    """Calculate GST TCS at 0.5%."""
    taxable = Decimal(str(taxable_value))
    total_tcs = (taxable * GST_TCS_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if is_interstate(supplier_state, place_of_supply_state):
        return Decimal("0"), Decimal("0"), total_tcs  # igst_tcs
    else:
        half = (total_tcs / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return half, half, Decimal("0")  # cgst_tcs, sgst_tcs

def calc_tds_194o(taxable_value):
    """Calculate TDS u/s 194-O at 1%."""
    return (Decimal(str(taxable_value)) * TDS_194O_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def amount_in_words(amount):
    """Convert amount to words (simplified)."""
    try:
        amt = float(amount)
        rupees = int(amt)
        paise  = round((amt - rupees) * 100)
        ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven',
                'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen',
                'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
        tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty',
                'Sixty', 'Seventy', 'Eighty', 'Ninety']

        def words(n):
            if n == 0: return ''
            elif n < 20: return ones[n]
            elif n < 100: return tens[n//10] + (' ' + ones[n%10] if n%10 else '')
            elif n < 1000: return ones[n//100] + ' Hundred' + (' ' + words(n%100) if n%100 else '')
            elif n < 100000: return words(n//1000) + ' Thousand' + (' ' + words(n%1000) if n%1000 else '')
            elif n < 10000000: return words(n//100000) + ' Lakh' + (' ' + words(n%100000) if n%100000 else '')
            else: return words(n//10000000) + ' Crore' + (' ' + words(n%10000000) if n%10000000 else '')

        result = 'Rupees ' + (words(rupees) if rupees else 'Zero')
        if paise:
            result += f' and {words(paise)} Paise'
        return result + ' Only'
    except:
        return ''
