from pathlib import Path
import base64

import streamlit as st


# ============================================================
# FUTURISTIC NCAA WVB PALETTE
# ============================================================

NAVY = "#071425"
NAVY_2 = "#0B1B31"
CARD = "#10253F"
CARD_2 = "#132B49"

NCAA_BLUE = "#0A67C8"
SKY = "#68D8FF"
MINT = "#8CF0CB"
LAVENDER = "#B9A7FF"

TEXT = "#F5F9FF"
MUTED = "#9CB0C8"
BORDER = "rgba(143, 200, 255, 0.18)"


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets"

NCAA_WVB_LOGO = ASSETS_DIR / "ncaa-wvblogo.png"


def image_to_data_uri(path):
    """
    Convert a local image into a CSS-safe data URI.
    """
    try:
        if not path.exists():
            return ""

        encoded = base64.b64encode(
            path.read_bytes()
        ).decode("ascii")

        return (
            "data:image/png;base64,"
            + encoded
        )

    except Exception:
        return ""



# ============================================================
# GLOBAL CSS
# ============================================================

def inject_global_css():
    """
    Global app styling.

    The VolleyReview brand is placed directly inside the
    Streamlit navigation container so it stays at the true
    top-left of the sidebar above all navigation groups.
    """

    logo_data_uri = image_to_data_uri(
        NCAA_WVB_LOGO
    )

    logo_background = (
        f'url("{logo_data_uri}")'
        if logo_data_uri
        else "none"
    )

    st.markdown(
        f"""
        <style>

        /* ==================================================
           APP BACKGROUND
        ================================================== */

        html,
        body,
        [class*="css"] {{
            font-family:
                Inter,
                ui-sans-serif,
                system-ui,
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;
        }}

        .stApp {{
            background:
                radial-gradient(
                    circle at 12% 0%,
                    rgba(104, 216, 255, 0.075),
                    transparent 27%
                ),
                radial-gradient(
                    circle at 92% 8%,
                    rgba(185, 167, 255, 0.075),
                    transparent 28%
                ),
                radial-gradient(
                    circle at 70% 92%,
                    rgba(140, 240, 203, 0.05),
                    transparent 28%
                ),
                linear-gradient(
                    145deg,
                    {NAVY} 0%,
                    #08182B 52%,
                    #06101E 100%
                );

            color: {TEXT};
        }}


        /* ==================================================
           REMOVE STREAMLIT TOP BAR
        ================================================== */

        header[data-testid="stHeader"],
        [data-testid="stHeader"],
        .stAppHeader {{
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            min-height: 0 !important;
            max-height: 0 !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }}

        [data-testid="stToolbar"],
        [data-testid="stStatusWidget"],
        [data-testid="stDecoration"] {{
            display: none !important;
            visibility: hidden !important;
        }}

        .block-container {{
            max-width: 1480px;
            padding-top: 1.75rem !important;
            padding-bottom: 3rem !important;
        }}


        /* ==================================================
           SIDEBAR
        ================================================== */

        [data-testid="stSidebar"] {{
            background:
                linear-gradient(
                    180deg,
                    #06111F 0%,
                    #081A2E 58%,
                    #071425 100%
                );

            border-right:
                1px solid rgba(104, 216, 255, 0.12);
        }}

        [data-testid="stSidebarContent"] {{
            padding-top: 0 !important;
            padding-bottom: 0.25rem;
        }}

        [data-testid="stSidebarNav"] {{
            padding-top: 0 !important;
            margin-top: -0.35rem !important;
        }}

        [data-testid="stSidebarNav"] {{
            padding-top: 0.15rem;
        }}

        /*
        ======================================================
        VOLLEYREVIEW — TRUE TOP-LEFT SIDEBAR BRAND
        ======================================================

        st.navigation() owns the top of the sidebar. Normal
        st.sidebar elements are placed after the navigation.
        This pseudo-element becomes the first child visually
        inside the navigation container itself.
        */

        [data-testid="stSidebarNav"]::before {{
            content:
                "NCAA WOMEN'S\\A"
                "VOLLEYBALL\\A"
                "REVIEW";

            display: flex;

            align-items: center;

            white-space: pre;

            min-height: 104px;

            margin:
                0 1rem 0.55rem;

            padding:
                0.75rem 0.35rem 0.75rem 92px;

            box-sizing: border-box;

            background-image:
                {logo_background};

            background-repeat:
                no-repeat;

            background-position:
                left 0.25rem center;

            background-size:
                74px auto;

            border-bottom:
                1px solid
                rgba(104, 216, 255, 0.16);

            color:
                {TEXT};

            font-size:
                1.08rem;

            font-weight:
                850;

            line-height:
                1.08;

            letter-spacing:
                -0.015em;
        }}

        [data-testid="stSidebarNav"] a {{
            border-radius: 10px;
            margin: 0px 6px;
            transition: all 0.16s ease;
        }}

        [data-testid="stSidebarNav"] a:hover {{
            background:
                rgba(104, 216, 255, 0.08);
        }}


        /* ==================================================
           TEXT
        ================================================== */

        h1,
        h2,
        h3 {{
            color: {TEXT} !important;
            letter-spacing: -0.03em;
        }}

        h1 {{
            font-weight: 850 !important;
        }}

        h2,
        h3 {{
            font-weight: 750 !important;
        }}

        p {{
            line-height: 1.5;
        }}


        /* ==================================================
           BORDERED CONTAINERS
        ================================================== */

        [data-testid="stVerticalBlockBorderWrapper"] {{
            border:
                1px solid
                rgba(104, 216, 255, 0.14) !important;

            border-radius:
                18px !important;

            background:
                linear-gradient(
                    115deg,
                    rgba(16, 37, 63, 0.92),
                    rgba(10, 103, 200, 0.075) 60%,
                    rgba(185, 167, 255, 0.045)
                ) !important;

            box-shadow:
                inset 0 1px 0 rgba(255,255,255,.025),
                0 14px 40px rgba(0,0,0,.08);
        }}


        /* ==================================================
           METRIC CARDS
        ================================================== */

        [data-testid="stMetric"] {{
            min-height: 120px;

            padding:
                0.95rem 1rem;

            border:
                1px solid
                rgba(104, 216, 255, 0.15);

            border-top:
                2px solid {SKY};

            border-radius:
                16px;

            background:
                linear-gradient(
                    155deg,
                    rgba(16, 37, 63, 0.96),
                    rgba(10, 25, 44, 0.96)
                );

            box-shadow:
                inset 0 1px 0 rgba(255,255,255,.025),
                0 12px 30px rgba(0,0,0,.08);
        }}

        [data-testid="stMetricLabel"] {{
            color:
                {MUTED} !important;

            font-size:
                0.72rem !important;

            font-weight:
                800 !important;

            letter-spacing:
                0.09em;

            text-transform:
                uppercase;
        }}

        [data-testid="stMetricValue"] {{
            color:
                {TEXT} !important;

            font-weight:
                850 !important;

            letter-spacing:
                -0.045em;
        }}

        [data-testid="stMetricDelta"] {{
            color:
                {MUTED} !important;

            font-size:
                0.76rem !important;
        }}


        /* ==================================================
           INPUTS
        ================================================== */

        [data-baseweb="select"] > div,
        [data-baseweb="input"] > div,
        [data-testid="stTextArea"] textarea,
        [data-testid="stTextInput"] input {{
            background:
                rgba(16, 37, 63, 0.78) !important;

            border-color:
                rgba(104, 216, 255, 0.16) !important;

            color:
                {TEXT} !important;

            border-radius:
                11px !important;
        }}

        [data-baseweb="select"] > div:focus-within,
        [data-baseweb="input"] > div:focus-within,
        [data-testid="stTextArea"] textarea:focus,
        [data-testid="stTextInput"] input:focus {{
            border-color:
                {SKY} !important;

            box-shadow:
                0 0 0 1px
                rgba(104, 216, 255, 0.25) !important;
        }}


        /* ==================================================
           BUTTONS
        ================================================== */

        .stButton > button[kind="primary"],
        [data-testid="stFormSubmitButton"]
        button[kind="primary"] {{
            background:
                linear-gradient(
                    90deg,
                    {NCAA_BLUE},
                    #1889DA 58%,
                    #37A6E5
                ) !important;

            color:
                white !important;

            border:
                1px solid
                rgba(104, 216, 255, 0.35) !important;

            border-radius:
                11px !important;

            box-shadow:
                0 8px 30px
                rgba(10, 103, 200, 0.20);

            font-weight:
                700 !important;
        }}

        .stButton > button:not([kind="primary"]),
        .stLinkButton > a {{
            border-radius:
                11px !important;

            border-color:
                rgba(104, 216, 255, 0.18) !important;

            background:
                rgba(16, 37, 63, 0.62) !important;
        }}


        /* ==================================================
           ALERTS / DATA / PROGRESS / VIDEO
        ================================================== */

        [data-testid="stAlert"] {{
            border-radius: 12px;

            border:
                1px solid
                rgba(104, 216, 255, 0.14);
        }}

        [data-testid="stDataFrame"] {{
            border:
                1px solid
                rgba(104, 216, 255, 0.12);

            border-radius: 13px;
            overflow: hidden;
        }}

        [data-testid="stProgress"]
        > div
        > div
        > div {{
            background:
                linear-gradient(
                    90deg,
                    {NCAA_BLUE},
                    {SKY},
                    {MINT}
                ) !important;
        }}

        video {{
            border-radius:
                14px !important;

            border:
                1px solid
                rgba(104, 216, 255, 0.16);

            background:
                #020812;
        }}

        hr {{
            border-color:
                rgba(104, 216, 255, 0.10) !important;
        }}

        #MainMenu {{
            visibility: hidden;
        }}

        footer {{
            visibility: hidden;
        }}

        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# SIDEBAR BRAND
# ============================================================

def render_sidebar_brand():
    """
    Branding is injected into stSidebarNav by inject_global_css()
    so it appears above the Streamlit navigation, not below it.

    This function remains for compatibility with streamlit_app.py.
    """
    return


# ============================================================
# SIDEBAR FOOTER
# ============================================================

def render_sidebar_footer():

    st.sidebar.caption(
        "Internal Review Platform • 2026"
    )


# ============================================================
# PAGE HEADER
# ============================================================

def render_page_header(
    title,
    subtitle="",
    eyebrow="NCAA WOMEN'S VOLLEYBALL",
):
    """
    Native Streamlit page header.
    No visible-content HTML is used.
    """

    with st.container(
        border=True
    ):

        st.caption(
            f"◈ {eyebrow}"
        )

        st.markdown(
            f"# {title}"
        )

        if subtitle:

            st.caption(
                subtitle
            )


# ============================================================
# KPI CARD
# ============================================================

def render_kpi(
    label,
    value,
    detail="",
    accent="blue",
):
    """
    Native Streamlit metric.
    accent is retained for compatibility with existing pages.
    """

    delta = (
        detail
        if detail
        else None
    )

    st.metric(
        label=label,
        value=value,
        delta=delta,
        delta_color="off",
        border=False,
    )


# ============================================================
# SECTION LABEL
# ============================================================

def render_section_label(
    text,
):
    """
    Native section heading.
    """

    st.caption(
        f"●  {text.upper()}"
    )


# ============================================================
# STATUS
# ============================================================

def render_status_pill(
    status,
):
    """
    Native status indicator.
    """

    status = (
        status
        or "Not Viewed"
    )

    if status == "Complete":

        st.success(
            "● Complete",
            icon="✅",
        )

    elif status == "Needs Review":

        st.warning(
            "● Needs Review",
            icon="⚠️",
        )

    else:

        st.info(
            "● Not Viewed",
            icon="👁️",
        )


# ============================================================
# EMPTY STATE
# ============================================================

def render_empty(
    message,
):
    """
    Native empty-state component.
    """

    st.info(
        message
    )
