
#!/usr/bin/env python3
# app_qr_lab.py

import io
from datetime import datetime, date, time as dtime

import segno
from PIL import Image
import streamlit as st

APP_TITLE = "🔳 QR Code Lab — Generate, Style & Download"

st.set_page_config(page_title="QR Code Lab", page_icon="🔳", layout="centered")

# --- Light styling ---
st.markdown(
    """
    <style>
    .app-title { font-size: 2rem; font-weight: 700; }
    .subtitle { color: #667085; margin-bottom: 0.75rem; }
    .hint { font-size: .9rem; color: #667085; }
    .footnotes { font-size: .85rem; color: #6b7280; }
    .stButton > button { border-radius: 12px; padding: .6rem 1rem; }
    .stDownloadButton > button { border-radius: 12px; padding: .6rem 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(f'<div class="app-title">{APP_TITLE}</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Enter content, pick options, and download PNG / SVG / PDF.</div>', unsafe_allow_html=True)

# ---------------------------
# Helpers to build payloads
# ---------------------------
def build_wifi_payload(ssid: str, password: str, auth: str, hidden: bool) -> str:
    # WIFI:T:WPA;S:MySSID;P:MyPass;H:true;;
    auth = (auth or "nopass").upper()
    if auth not in {"WEP", "WPA", "WPA2", "NOPASS"}:
        auth = "WPA"
    hidden_flag = "true" if hidden else "false"
    # escape semicolons and commas minimally
    def esc(s: str) -> str:
        return (s or "").replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,")
    return f"WIFI:T:{'nopass' if auth=='NOPASS' else auth};S:{esc(ssid)};P:{esc(password)};H:{hidden_flag};;"

def build_mailto(email: str, subject: str, body: str) -> str:
    from urllib.parse import quote
    qs = []
    if subject: qs.append("subject=" + quote(subject))
    if body: qs.append("body=" + quote(body))
    return f"mailto:{email}" + (f"?{'&'.join(qs)}" if qs else "")

def build_sms(number: str, message: str) -> str:
    # SMSTO:number:message is widely supported
    return f"SMSTO:{number}:{message or ''}"

def build_tel(number: str) -> str:
    return f"tel:{number}"

def build_geo(lat: float, lon: float, label: str) -> str:
    # geo:lat,lon or geo:lat,lon?q=label
    from urllib.parse import quote
    payload = f"geo:{lat},{lon}"
    if label:
        payload += f"?q={quote(label)}"
    return payload

def _fmt_dt(dt: datetime) -> str:
    # Basic local time -> iCal-like
    return dt.strftime("%Y%m%dT%H%M%S")

def build_vevent(summary: str, start_dt: datetime, end_dt: datetime, location: str, desc: str) -> str:
    # Minimal iCalendar VEVENT (no tz handling for simplicity)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//QR Lab//EN",
        "BEGIN:VEVENT",
        f"SUMMARY:{summary or ''}",
        f"DTSTART:{_fmt_dt(start_dt)}",
        f"DTEND:{_fmt_dt(end_dt)}",
        f"LOCATION:{location or ''}",
        f"DESCRIPTION:{(desc or '').replace('\\n', '\\\\n')}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\n".join(lines)

def build_vcard(given: str, family: str, phone: str, email: str, org: str, title: str, url: str) -> str:
    # Simple vCard 3.0
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{family};{given};;;",
        f"FN:{given} {family}".strip(),
    ]
    if org:   lines.append(f"ORG:{org}")
    if title: lines.append(f"TITLE:{title}")
    if phone: lines.append(f"TEL;TYPE=CELL:{phone}")
    if email: lines.append(f"EMAIL;TYPE=INTERNET:{email}")
    if url:   lines.append(f"URL:{url}")
    lines.append("END:VCARD")
    return "\n".join(lines)

# ---------------------------
# UI: Content builder
# ---------------------------
data_type = st.selectbox(
    "QR content type",
    ["URL / Text", "Wi-Fi", "Email", "SMS", "Phone", "Geo", "vCard", "Calendar event"],
)

payload = None

if data_type == "URL / Text":
    payload = st.text_area("Text or URL", placeholder="https://example.com or any text", height=120)

elif data_type == "Wi-Fi":
    ssid = st.text_input("SSID (network name)")
    auth = st.selectbox("Authentication", ["WPA/WPA2", "WEP", "No password"])
    password = "" if auth == "No password" else st.text_input("Password", type="password")
    hidden = st.checkbox("Hidden network", value=False)
    payload = build_wifi_payload(ssid, password, {"WPA/WPA2":"WPA", "WEP":"WEP", "No password":"NOPASS"}[auth], hidden)

elif data_type == "Email":
    to = st.text_input("To (email)")
    subject = st.text_input("Subject")
    body = st.text_area("Body", height=100)
    payload = build_mailto(to, subject, body)

elif data_type == "SMS":
    number = st.text_input("Phone number")
    message = st.text_area("Message", height=100)
    payload = build_sms(number, message)

elif data_type == "Phone":
    number = st.text_input("Phone number")
    payload = build_tel(number)

elif data_type == "Geo":
    c1, c2 = st.columns(2)
    with c1:
        lat = st.number_input("Latitude", value=40.7128, format="%.6f")
    with c2:
        lon = st.number_input("Longitude", value=-74.0060, format="%.6f")
    label = st.text_input("Label (optional)", placeholder="Statue of Liberty")
    payload = build_geo(lat, lon, label)

elif data_type == "vCard":
    c1, c2 = st.columns(2)
    with c1:
        given = st.text_input("First name")
        phone = st.text_input("Phone")
        org = st.text_input("Organization")
    with c2:
        family = st.text_input("Last name")
        email = st.text_input("Email")
        title = st.text_input("Title")
    url = st.text_input("Website")
    payload = build_vcard(given, family, phone, email, org, title, url)

elif data_type == "Calendar event":
    summary = st.text_input("Title")
    col_dt1, col_dt2 = st.columns(2)
    with col_dt1:
        d_start = st.date_input("Start date", value=date.today())
        t_start = st.time_input("Start time", value=dtime(9, 0))
    with col_dt2:
        d_end = st.date_input("End date", value=date.today())
        t_end = st.time_input("End time", value=dtime(10, 0))
    location = st.text_input("Location")
    desc = st.text_area("Description", height=100)
    start_dt = datetime.combine(d_start, t_start)
    end_dt = datetime.combine(d_end, t_end)
    payload = build_vevent(summary, start_dt, end_dt, location, desc)

# ---------------------------
# Sidebar: style & export
# ---------------------------
with st.sidebar:
    st.header("Style & Export")
    ecc = st.selectbox("Error correction", ["L", "M", "Q", "H"], index=3,
                       help="Higher error correction (H) is safest, especially if you add a logo.")
    scale = st.slider("Module scale (pixels)", 4, 20, 10)
    border = st.slider("Quiet zone (modules)", 1, 8, 4)
    fg = st.color_picker("Foreground", "#111827")   # near-black
    bg = st.color_picker("Background", "#FFFFFF")   # white

    st.markdown("---")
    logo = st.file_uploader("Logo overlay (PNG/JPG)", type=["png", "jpg", "jpeg"])
    logo_scale = st.slider("Logo size (fraction of QR width)", 10, 40, 22, help="~20–25% works well.") / 100.0
    round_logo = st.checkbox("Round logo (mask)", value=True)

    st.markdown("---")
    want_png = st.checkbox("Export PNG", value=True)
    want_svg = st.checkbox("Export SVG", value=True)
    want_pdf = st.checkbox("Export PDF", value=False)

# ---------------------------
# Generate & preview
# ---------------------------
col_left, col_right = st.columns([1, 1], vertical_alignment="center")

with col_left:
    if st.button("Generate QR code", use_container_width=True, type="primary"):
        if not (payload and str(payload).strip()):
            st.warning("Please enter content to encode.")
        else:
            st.session_state["qr_payload"] = payload
            st.session_state["qr_opts"] = dict(ecc=ecc, scale=scale, border=border, fg=fg, bg=bg,
                                               logo=logo, logo_scale=logo_scale, round_logo=round_logo,
                                               want_png=want_png, want_svg=want_svg, want_pdf=want_pdf)
            st.success("QR generated below.")
            st.experimental_rerun()

with col_right:
    st.markdown('<div class="hint">Tip: keep high contrast and leave the center clear if you add a logo.</div>', unsafe_allow_html=True)

if "qr_payload" in st.session_state:
    payload = st.session_state["qr_payload"]
    opts = st.session_state["qr_opts"]

    qr = segno.make(payload, error=opts["ecc"])

    # Bytes for exports
    png_buf = io.BytesIO()
    qr.save(png_buf, kind="png", scale=opts["scale"], border=opts["border"], dark=opts["fg"], light=opts["bg"])
    png_buf.seek(0)

    # Logo overlay (PNG only preview)
    preview_buf = io.BytesIO(png_buf.getvalue())
    preview_img = Image.open(preview_buf).convert("RGBA")

    if opts["logo"] is not None:
        try:
            logo_img = Image.open(opts["logo"]).convert("RGBA")
            # optional round mask
            if opts["round_logo"]:
                import numpy as np
                mask = Image.new("L", logo_img.size, 0)
                mdraw = Image.new("L", logo_img.size, 0)
                # circular mask via numpy
                w, h = logo_img.size
                y, x = np.ogrid[:h, :w]
                centerx, centery = (w - 1) / 2, (h - 1) / 2
                radius = min(centerx, centery)
                circle = (x - centerx) ** 2 + (y - centery) ** 2 <= radius ** 2
                mask_np = np.zeros((h, w), dtype=np.uint8)
                mask_np[circle] = 255
                mask = Image.fromarray(mask_np, mode="L")
                logo_img.putalpha(mask)

            # resize logo to fraction of QR width
            lw = int(preview_img.width * opts["logo_scale"])
            lh = int(lw * (logo_img.height / logo_img.width))
            logo_img = logo_img.resize((lw, lh), Image.LANCZOS)

            # paste centered
            x = (preview_img.width - logo_img.width) // 2
            y = (preview_img.height - logo_img.height) // 2
            preview_img.alpha_composite(logo_img, (x, y))
        except Exception:
            st.info("Logo overlay failed; continuing without logo.")

    # Show preview
    st.image(preview_img, caption="Preview (PNG)", use_container_width=True)

    # Download buttons
    dl_cols = st.columns(3)
    if opts["want_png"]:
        with dl_cols[0]:
            out = io.BytesIO()
            preview_img.save(out, format="PNG")
            out.seek(0)
            st.download_button("⬇️ PNG", data=out, file_name="qr.png", mime="image/png", use_container_width=True)

    if opts["want_svg"]:
        with dl_cols[1]:
            svg = io.BytesIO()
            qr.save(svg, kind="svg", scale=opts["scale"], border=opts["border"], dark=opts["fg"], light=opts["bg"])
            svg.seek(0)
            st.download_button("⬇️ SVG", data=svg, file_name="qr.svg", mime="image/svg+xml", use_container_width=True)

    if opts["want_pdf"]:
        with dl_cols[2]:
            pdf = io.BytesIO()
            qr.save(pdf, kind="pdf", scale=opts["scale"], border=opts["border"], dark=opts["fg"], light=opts["bg"])
            pdf.seek(0)
            st.download_button("⬇️ PDF", data=pdf, file_name="qr.pdf", mime="application/pdf", use_container_width=True)

st.markdown(
    """
    <div class="footnotes">
    • Scannability tips: keep high contrast, avoid cluttering finder patterns, use error correction “H” when adding logos.<br/>
    • Dynamic/trackable QR requires a redirect service (Bitly, Rebrandly, or your own link shortener). This app generates static codes.
    </div>
    """,
    unsafe_allow_html=True,
)
