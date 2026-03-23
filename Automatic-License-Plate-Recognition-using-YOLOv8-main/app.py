"""
Smart Gate Access — SGA Dashboard
Run: streamlit run app.py
"""

import streamlit as st
import sqlite3
import pandas as pd
import cv2
import tempfile
import os
import time
from datetime import datetime

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="SGA | Hampton University",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# CUSTOM CSS  — deep navy / electric blue theme
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
    background-color: #020c1b;
    color: #ccd6f6;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #0a1628;
    border-right: 1px solid #1e3a5f;
}

/* Metric cards */
[data-testid="metric-container"] {
    background: #0d2137;
    border: 1px solid #1e3a5f;
    border-radius: 8px;
    padding: 16px;
}

/* Headings */
h1, h2, h3 { font-family: 'IBM Plex Mono', monospace; color: #64ffda; }
h1 { font-size: 1.4rem; letter-spacing: 2px; text-transform: uppercase; }
h2 { font-size: 1rem; color: #8892b0; letter-spacing: 1px; }

/* Buttons */
.stButton > button {
    background: transparent;
    border: 1px solid #64ffda;
    color: #64ffda;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    letter-spacing: 1px;
    border-radius: 4px;
    padding: 8px 20px;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: #64ffda22;
}

/* Danger button */
.danger-btn > button {
    border-color: #ff6b6b !important;
    color: #ff6b6b !important;
}
.danger-btn > button:hover { background: #ff6b6b22 !important; }

/* Table */
.stDataFrame { background: #0d2137; border: 1px solid #1e3a5f; }

/* Input */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div {
    background: #0d2137;
    border: 1px solid #1e3a5f;
    color: #ccd6f6;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
}

/* Risk badge helpers (rendered via markdown) */
.badge-clear  { background:#0d4f3c; color:#64ffda; padding:3px 10px; border-radius:4px; font-size:0.75rem; font-family:monospace; }
.badge-warn   { background:#4f3c0d; color:#ffd166; padding:3px 10px; border-radius:4px; font-size:0.75rem; font-family:monospace; }
.badge-danger { background:#4f0d0d; color:#ff6b6b; padding:3px 10px; border-radius:4px; font-size:0.75rem; font-family:monospace; }

/* Divider */
hr { border-color: #1e3a5f; }

/* Hide default streamlit chrome */
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# DATABASE  — single file, zero config
# WHY SQLite: no server needed, lives in your folder,
# fast enough for gate-level access logging.
# ─────────────────────────────────────────────
DB = "hampton_gate.db"   # lives in the same folder as app.py and main.py

def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # authorized: the "whitelist" — plates the gate knows about
    c.execute("""CREATE TABLE IF NOT EXISTS authorized (
        plate_text  TEXT PRIMARY KEY,
        owner_name  TEXT,
        role        TEXT
    )""")

    # access_logs: every scan event goes here permanently
    c.execute("""CREATE TABLE IF NOT EXISTS access_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_text  TEXT,
        timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
        risk_score  INTEGER,
        status      TEXT,
        gate_action TEXT
    )""")

    # Seed a few demo plates so the UI isn't empty on first run
    demo = [
        ("HU-1001", "Aaliyah Johnson",  "Student"),
        ("HU-2045", "Dr. Marcus Webb",  "Faculty"),
        ("HU-3312", "Facilities Dept.", "Maintenance"),
        ("ABC1234", "John Doe",         "Student"),
    ]
    c.executemany("INSERT OR IGNORE INTO authorized VALUES (?,?,?)", demo)
    conn.commit()
    conn.close()

init_db()


# ─────────────────────────────────────────────
# RISK SCORING ENGINE
#
# EQUATION (user-configurable via sidebar):
#
#   score = base_unknown_penalty
#         + (night_penalty   if late_night)
#         + (freq_penalty    if seen_today >= freq_threshold)
#
# Score bands:
#   0–30   → CLEAR
#   31–60  → WARNING
#   61+    → DANGER
#
# WHY equation-based: gives security a transparent,
# auditable number instead of a black-box verdict.
# ─────────────────────────────────────────────
def calculate_risk(plate: str, is_authorized: bool,
                   base_penalty: int,
                   night_penalty: int,
                   freq_penalty: int,
                   freq_threshold: int) -> int:
    if is_authorized:
        return 0   # known vehicle = zero risk

    score = base_penalty  # unknown vehicle starts here

    # TIME component — late-night access is riskier
    hour = datetime.now().hour
    if hour >= 23 or hour <= 5:
        score += night_penalty

    # FREQUENCY component — how many times seen today?
    conn = get_conn()
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("""SELECT COUNT(*) FROM access_logs
                 WHERE plate_text=? AND DATE(timestamp)=?""",
              (plate, today))
    seen_today = c.fetchone()[0]
    conn.close()

    if seen_today >= freq_threshold:
        score += freq_penalty

    return min(score, 100)   # cap at 100


def risk_label(score: int) -> str:
    if score <= 30:  return "CLEAR"
    if score <= 60:  return "WARNING"
    return "DANGER"

def risk_color(score: int) -> str:
    if score <= 30:  return "#64ffda"
    if score <= 60:  return "#ffd166"
    return "#ff6b6b"


# ─────────────────────────────────────────────
# PLATE LOOKUP
# WHY: single function keeps DB logic out of the UI layer
# ─────────────────────────────────────────────
def lookup_plate(plate: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT owner_name, role FROM authorized WHERE plate_text=?", (plate,))
    row = c.fetchone()
    conn.close()
    return row   # None = not authorized


def log_event(plate, risk, status, action):
    conn = get_conn()
    conn.execute("""INSERT INTO access_logs (plate_text, risk_score, status, gate_action)
                    VALUES (?,?,?,?)""", (plate, risk, status, action))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# SIDEBAR — equation controls + manual enrollment
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔒 SGA CONTROL")
    st.markdown("---")

    st.markdown("**Risk Equation Parameters**")
    st.caption("Tune the scoring formula in real time.")

    base_pen   = st.slider("Base unknown penalty",  0, 80, 50,
                           help="Points added just for being an unregistered plate.")
    night_pen  = st.slider("Late-night bonus (11pm–5am)", 0, 40, 30,
                           help="Extra risk for off-hours access.")
    freq_pen   = st.slider("Repeat-visit bonus",    0, 40, 20,
                           help="Extra risk if seen N+ times today.")
    freq_thresh = st.slider("Repeat threshold (visits/day)", 1, 10, 3,
                            help="How many scans before frequency penalty kicks in.")

    st.markdown("---")
    st.markdown("**Manual Plate Enrollment**")
    new_plate = st.text_input("Plate", placeholder="e.g. XYZ9999")
    new_owner = st.text_input("Owner name")
    new_role  = st.selectbox("Role", ["Student","Faculty","Maintenance","Visitor","Contractor"])
    if st.button("➕  Enroll Plate"):
        if new_plate and new_owner:
            conn = get_conn()
            conn.execute("INSERT OR REPLACE INTO authorized VALUES (?,?,?)",
                         (new_plate.upper(), new_owner, new_role))
            conn.commit()
            conn.close()
            st.success(f"{new_plate.upper()} enrolled.")
        else:
            st.warning("Fill in both plate and owner.")

    st.markdown("---")
    st.markdown("**Authorized Vehicles**")
    conn = get_conn()
    df_auth = pd.read_sql("SELECT plate_text, owner_name, role FROM authorized", conn)
    conn.close()
    st.dataframe(df_auth, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# MAIN PANEL
# ─────────────────────────────────────────────
st.markdown("# SMART GATE ACCESS")
st.markdown("## Hampton University — Security Operations Dashboard")
st.markdown("---")

tab_scan, tab_video, tab_logs = st.tabs(["⚡  SCAN PLATE", "📹  VIDEO FEED", "📋  ACCESS LOG"])


# ── TAB 1: Manual plate scan ──────────────────
with tab_scan:
    st.markdown("### Manual Plate Scan")
    st.caption("Simulate a gate-level plate read. Enter any plate to run it through the matching algorithm and get a live risk score.")

    col_input, col_result = st.columns([1, 1], gap="large")

    with col_input:
        scan_plate = st.text_input("Plate number", placeholder="e.g. HU-1001", key="scan_input")
        scan_time  = st.time_input("Scan time (for time-of-day scoring)", value=datetime.now().time())
        do_scan    = st.button("▶  RUN SCAN")

    with col_result:
        if do_scan and scan_plate:
            plate_up = scan_plate.strip().upper()
            match    = lookup_plate(plate_up)
            auth     = match is not None

            # Override hour for custom time input
            import datetime as dt
            fake_hour = scan_time.hour
            score = base_pen if not auth else 0
            if not auth:
                if fake_hour >= 23 or fake_hour <= 5:
                    score += night_pen
                conn = get_conn()
                c = conn.cursor()
                today = datetime.now().strftime("%Y-%m-%d")
                c.execute("""SELECT COUNT(*) FROM access_logs
                             WHERE plate_text=? AND DATE(timestamp)=?""",
                          (plate_up, today))
                seen = c.fetchone()[0]
                conn.close()
                if seen >= freq_thresh:
                    score += freq_pen
                score = min(score, 100)

            label  = risk_label(score)
            color  = risk_color(score)
            action = "GATE OPEN" if auth else "GATE HOLD"
            status = f"VERIFIED – {match[1]} ({match[0]})" if auth else f"UNKNOWN – {label}"

            # Log it
            log_event(plate_up, score, status, action)

            # Display result card
            st.markdown(f"""
            <div style="background:#0d2137;border:1px solid {color};border-radius:8px;padding:24px;">
                <div style="font-family:'IBM Plex Mono',monospace;font-size:1.6rem;color:{color};font-weight:600;letter-spacing:3px;">
                    {plate_up}
                </div>
                <div style="margin:12px 0;font-size:0.85rem;color:#8892b0;">{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}</div>
                <hr style="border-color:#1e3a5f;">
                <table style="width:100%;font-size:0.85rem;font-family:'IBM Plex Mono',monospace;">
                  <tr><td style="color:#8892b0;padding:4px 0;">STATUS</td>
                      <td style="color:{color};text-align:right;">{status}</td></tr>
                  <tr><td style="color:#8892b0;padding:4px 0;">RISK SCORE</td>
                      <td style="color:{color};text-align:right;font-size:1.4rem;font-weight:600;">{score}<span style="font-size:0.7rem;"> /100</span></td></tr>
                  <tr><td style="color:#8892b0;padding:4px 0;">GATE ACTION</td>
                      <td style="color:{color};text-align:right;">{action}</td></tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

            # Risk score bar
            st.markdown(f"""
            <div style="margin-top:16px;">
              <div style="height:8px;background:#1e3a5f;border-radius:4px;overflow:hidden;">
                <div style="width:{score}%;height:100%;background:{color};border-radius:4px;transition:width 0.5s;"></div>
              </div>
              <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:#4a5568;margin-top:4px;font-family:monospace;">
                <span>0 — CLEAR</span><span>50 — WARNING</span><span>100 — DANGER</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            if not auth:
                st.markdown("---")
                st.markdown("**Security Intervention**")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅  Override: Open Gate"):
                        log_event(plate_up, score, status, "MANUAL OVERRIDE – OPEN")
                        st.success("Gate opened. Event logged.")
                with c2:
                    if st.button("🚨  Flag & Detain"):
                        log_event(plate_up, score, status, "FLAGGED – SECURITY DISPATCHED")
                        st.error("Security dispatched. Event logged.")


# ── TAB 2: Video feed ─────────────────────────
with tab_video:
    st.markdown("### Video Feed Processor")
    st.caption("Upload your `out.mp4` output. If you've already run `main.py`, the Access Log tab shows which frame each plate was detected on — use the frame number to jump directly to that moment in the video.")

    VIDEO_PATH = "./out.mp4"

    if os.path.exists(VIDEO_PATH):
        cap = cv2.VideoCapture(VIDEO_PATH)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps          = cap.get(cv2.CAP_PROP_FPS) or 25

        st.markdown(f"**{total_frames} frames · {fps:.0f} fps · {total_frames/fps:.1f}s**")

        frame_slider = st.slider("Jump to frame", 0, max(total_frames-1,1), 0, key="frame_seek")
        col_play, col_plates = st.columns([2, 1], gap="large")

        with col_play:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_slider)
            ret, frame = cap.read()
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                st.image(frame_rgb, use_column_width=True,
                         caption=f"Frame {frame_slider} / {total_frames}")

        with col_plates:
            st.markdown("**Plates detected at this frame**")
            st.caption("Manually enter any plate visible in the frame to run it through the risk algorithm.")
            v_plate = st.text_input("Detected plate", key="video_plate")
            if st.button("▶  Score this plate", key="video_scan"):
                if v_plate:
                    p     = v_plate.strip().upper()
                    m     = lookup_plate(p)
                    a     = m is not None
                    sc    = calculate_risk(p, a, base_pen, night_pen, freq_pen, freq_thresh)
                    lbl   = risk_label(sc)
                    col   = risk_color(sc)
                    act   = "GATE OPEN" if a else "GATE HOLD"
                    stat  = f"VERIFIED – {m[1]}" if a else f"UNKNOWN – {lbl}"
                    log_event(p, sc, stat, act)
                    st.markdown(f"""
                    <div style="background:#0d2137;border-left:4px solid {col};padding:16px;border-radius:4px;font-family:'IBM Plex Mono',monospace;">
                        <div style="color:{col};font-size:1.2rem;font-weight:600;">{p}</div>
                        <div style="color:#8892b0;font-size:0.75rem;margin-top:4px;">{stat}</div>
                        <div style="color:{col};font-size:2rem;font-weight:700;margin-top:8px;">{sc}<span style="font-size:0.75rem;color:#8892b0;"> risk</span></div>
                        <div style="color:#8892b0;font-size:0.75rem;">{act}</div>
                    </div>
                    """, unsafe_allow_html=True)

        cap.release()

    else:
        st.warning("out.mp4 not found. Make sure it is in the same folder as app.py.")


# ── TAB 3: Access log ─────────────────────────
with tab_logs:
    st.markdown("### Access Log")
    st.caption("Every scan — automated or manual — is written here permanently with a timestamp.")

    conn = get_conn()
    df_logs = pd.read_sql("""
        SELECT id, plate_text, timestamp, risk_score, status, gate_action,
               frame_nmr, car_id, ROUND(ocr_confidence,3) as ocr_confidence
        FROM access_logs ORDER BY id DESC LIMIT 200
    """, conn)
    conn.close()

    if not df_logs.empty:
        # Summary metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Scans",    len(df_logs))
        m2.metric("Alerts (HOLD)",  len(df_logs[df_logs["gate_action"].str.contains("HOLD", na=False)]))
        m3.metric("Avg Risk Score", f"{df_logs['risk_score'].mean():.0f}")
        m4.metric("Manual Overrides", len(df_logs[df_logs["gate_action"].str.contains("OVERRIDE", na=False)]))

        st.markdown("---")

        # Color-code risk column
        def style_risk(val):
            if val <= 30: return "color: #64ffda"
            if val <= 60: return "color: #ffd166"
            return "color: #ff6b6b"

        styled = df_logs.style.applymap(style_risk, subset=["risk_score"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

        if st.button("🗑  Clear Log"):
            conn = get_conn()
            conn.execute("DELETE FROM access_logs")
            conn.commit()
            conn.close()
            st.rerun()
    else:
        st.info("No events logged yet. Run a plate scan to populate this table.")