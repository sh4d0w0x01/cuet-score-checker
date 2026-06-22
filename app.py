import streamlit as st
import pandas as pd
import re
from bs4 import BeautifulSoup
import io

try:
    import fitz  # PyMuPDF
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_SUPPORT = True
except ImportError:
    PLOTLY_SUPPORT = False

st.set_page_config(
    page_title="CUET Marks Checker Pro",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# ── Custom CSS for Premium Look ──────────────────────────────────────────
st.markdown("""
<style>
    /* Premium Headers */
    h1, h2, h3 { font-family: 'Inter', sans-serif; font-weight: 600; letter-spacing: -0.5px; }
    
    /* Metric Cards */
    div[data-testid="metric-container"] {
        background-color: #1E1E2E;
        border: 1px solid #333;
        padding: 15px 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        transition: transform 0.2s;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-5px);
        border-color: #6366F1;
    }
    
    /* DataFrames */
    .stDataFrame { border-radius: 10px; overflow: hidden; border: 1px solid #333; }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2D2D3F;
        border-bottom: 2px solid #6366F1;
        color: #fff;
    }
</style>
""", unsafe_allow_html=True)

# ── Sidebar Settings ───────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Scoring Rules")
    MARKS_CORRECT = st.number_input("Marks for Correct Answer", value=5, step=1)
    MARKS_WRONG   = st.number_input("Penalty for Wrong Answer",  value=-1, step=1)
    st.markdown("---")
    st.info("💡 **Tip:** Unattempted and NTA-dropped questions automatically award 0 marks.")
    if not PDF_SUPPORT:
        st.warning("⚠️ `PyMuPDF` not installed. PDF Answer Keys are disabled.")
    if not PLOTLY_SUPPORT:
        st.warning("⚠️ `plotly` not installed. Interactive charts are disabled.")

st.title("🎓 CUET Marks Checker Pro")
st.markdown("An advanced, highly precise tool to evaluate your CUET response sheets against the official NTA answer keys.")


# ── Helper Functions ───────────────────────────────────────────────────────
def html_to_text(content: str) -> str:
    soup = BeautifulSoup(content, "html.parser")
    return soup.get_text("\n")

def clean_id_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

def find_column(cols, names):
    normalized = {re.sub(r"[^a-z0-9]", "", str(c).lower()): c for c in cols}
    for name in names:
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in normalized: return normalized[key]
    return None

# ── Parsers ────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_answer_key_from_pdf(file_bytes: bytes, date_filter: str | None, shift_filter: str | None, subject_filter: str | None) -> pd.DataFrame:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    rows = []
    date_pat    = re.compile(r"Exam Date\s*[:\-]\s*(\d{2}-\d{2}-\d{4})\s*\((First|Second)\)", re.IGNORECASE)
    subject_pat = re.compile(r"Subject\s*[:\-]\s*(.+)")
    qid_pat  = re.compile(r"^\d{12,}$")
    key_pat  = re.compile(r"^\d{12,}(?:,\s*\d{12,})*$")

    for page in doc:
        text = page.get_text()
        dm = date_pat.search(text)
        if not dm: continue
        exam_date = dm.group(1)
        shift     = dm.group(2).strip()

        sm = subject_pat.search(text)
        subject = sm.group(1).strip() if sm else "Unknown"

        if date_filter and date_filter not in exam_date: continue
        if shift_filter and shift_filter.lower() not in shift.lower(): continue
        
        if subject_filter:
            tokens = [t.strip().lower() for t in subject_filter.split(",") if t.strip()]
            if not any(tok in subject.lower() for tok in tokens):
                continue

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        i = 0
        while i < len(lines):
            if qid_pat.match(lines[i]):
                if i + 1 < len(lines) and key_pat.match(lines[i + 1]):
                    rows.append({
                        "ExamDate":         exam_date,
                        "Shift":            shift,
                        "Subject":          subject,
                        "QuestionID":       lines[i],
                        "OfficialOptionID": lines[i + 1],
                    })
                    i += 2
                    continue
            i += 1
    doc.close()
    return pd.DataFrame(rows)

def load_answer_key(uploaded_file, df_filter_date, df_filter_shift, df_filter_subj) -> pd.DataFrame:
    filename = uploaded_file.name.lower()
    if filename.endswith(".pdf"):
        return load_answer_key_from_pdf(uploaded_file.read(), df_filter_date or None, df_filter_shift or None, df_filter_subj or None)
    
    if filename.endswith(".csv"):
        df = pd.read_csv(uploaded_file, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
        q_col = find_column(df.columns, ["QuestionID", "Question ID"])
        c_col = find_column(df.columns, ["CorrectOptionID", "Correct Option ID", "OfficialOptionID", "Official Option ID"])
        s_col = find_column(df.columns, ["Subject", "Test Paper", "TestPaper"])
        if not q_col or not c_col:
            st.error("CSV Answer Key must contain QuestionID and CorrectOptionID columns.")
            st.stop()
        res = pd.DataFrame()
        res["QuestionID"] = clean_id_series(df[q_col])
        res["OfficialOptionID"] = clean_id_series(df[c_col])
        res["Subject"] = df[s_col].astype(str).str.strip() if s_col else "Unknown"
        return res

    text = uploaded_file.read().decode("utf-8", errors="ignore")
    if filename.endswith((".html", ".htm")): text = html_to_text(text)
    rows = []
    pattern = re.compile(r"(\d+)\s+(.+?)\s+(\d{12,})\s+(\d{12,})", re.MULTILINE)
    for m in pattern.finditer(text):
        rows.append({"Subject": m.group(2).strip(), "QuestionID": m.group(3), "OfficialOptionID": m.group(4)})
    return pd.DataFrame(rows)

def load_response(uploaded_file) -> pd.DataFrame:
    filename = uploaded_file.name.lower()
    if filename.endswith(".csv"):
        df = pd.read_csv(uploaded_file, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
        q_col = find_column(df.columns, ["QuestionID", "Question ID"])
        chosen_col = find_column(df.columns, ["ChosenOptionID", "Chosen Option ID", "YourOptionID", "Your Option ID"])
        chosen_number_col = find_column(df.columns, ["ChosenOption", "Chosen Option"])
        
        if not q_col or not chosen_col:
            st.error("Response CSV must contain QuestionID and ChosenOptionID columns.")
            st.stop()
        res = pd.DataFrame()
        res["QuestionID"]   = clean_id_series(df[q_col])
        res["YourOptionID"] = clean_id_series(df[chosen_col])
        res["ChosenOption"] = clean_id_series(df[chosen_number_col]) if chosen_number_col else "Unattempted"
        return res

    text = uploaded_file.read().decode("utf-8", errors="ignore")
    if filename.endswith((".html", ".htm")):
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text("\n")

    blocks = text.split("Question ID :")
    rows = []
    for block in blocks[1:]:
        try:
            qid_match = re.search(r"(\d+)", block)
            if not qid_match: continue
            qid = qid_match.group(1)

            option_ids = {}
            for i in range(1, 5):
                match = re.search(rf"Option {i} ID\s*:\s*(\d+)", block)
                if match: option_ids[str(i)] = match.group(1)

            chosen_match = re.search(r"Chosen Option\s*:\s*(\d+)", block)
            chosen_option = chosen_match.group(1) if chosen_match else None
            
            if chosen_option and not chosen_option.isdigit():
                chosen_option = None

            your_option_id = option_ids.get(chosen_option) if chosen_option else None

            rows.append({
                "QuestionID":   qid,
                "ChosenOption": chosen_option if chosen_option else "Unattempted",
                "YourOptionID": your_option_id,
                "Option1ID":    option_ids.get("1"),
                "Option2ID":    option_ids.get("2"),
                "Option3ID":    option_ids.get("3"),
                "Option4ID":    option_ids.get("4"),
            })
        except Exception:
            pass
    return pd.DataFrame(rows)


# ── Step 1: Upload UI ──────────────────────────────────────────────────────
st.markdown("### 📥 Step 1: Upload Your Data")

col1, col2 = st.columns(2)
with col1:
    pdf_types = ["pdf"] if PDF_SUPPORT else []
    answer_file = st.file_uploader("1️⃣ Official Answer Key (PDF / HTML / CSV)", type=["txt", "html", "htm", "csv"] + pdf_types)
    
    pdf_exam_date_filter = None
    pdf_shift_filter = None
    pdf_subject_filter = None

    if answer_file and answer_file.name.lower().endswith(".pdf"):
        st.info("🔍 **PDF Filters** — Narrow down the 300+ page PDF to your specific slot.")
        fc1, fc2 = st.columns(2)
        with fc1: pdf_exam_date_filter = st.text_input("Exam Date (e.g. `12-05-2026`)").strip()
        with fc2: pdf_shift_filter = st.selectbox("Shift", ["All", "First", "Second"])
        if pdf_shift_filter == "All": pdf_shift_filter = None
        pdf_subject_filter = st.text_input("Subject(s) (e.g. `306, 319`)", placeholder="leave blank for all subjects in this slot").strip()

with col2:
    response_files = st.file_uploader("2️⃣ Your Response Sheet(s)", type=["txt", "html", "htm", "csv"], accept_multiple_files=True)


# ── Step 2: Processing & Dashboard ─────────────────────────────────────────
if answer_file and response_files:
    st.markdown("---")
    
    with st.spinner("Parsing Answer Key..."):
        answer_df = load_answer_key(answer_file, pdf_exam_date_filter, pdf_shift_filter, pdf_subject_filter)
        if answer_df.empty:
            st.error("❌ No answer-key rows extracted. Check your PDF filters.")
            st.stop()
        answer_df["QuestionID"] = clean_id_series(answer_df["QuestionID"])

    with st.spinner(f"Parsing {len(response_files)} Response Sheet(s)..."):
        frames = [load_response(f) for f in response_files]
        response_df = pd.concat(frames, ignore_index=True).drop_duplicates(subset="QuestionID")
        response_df["QuestionID"] = clean_id_series(response_df["QuestionID"])

    # Show PDF summary
    if answer_file.name.lower().endswith(".pdf") and "Subject" in answer_df.columns:
        unique_slots = answer_df[["ExamDate", "Shift", "Subject"]].drop_duplicates()
        with st.expander(f"📄 Answer Key Info: Loaded {len(answer_df)} keys across {len(unique_slots)} subjects", expanded=False):
            st.dataframe(unique_slots, hide_index=True, use_container_width=True)

    # ── Comparison Logic ───────────────────────────────────────────────────
    # We use a LEFT JOIN so we can see all questions in the user's response sheet
    merged = response_df.merge(answer_df, on="QuestionID", how="left", indicator=True)
    
    # Missing / Dropped questions
    missing_df = merged[merged['_merge'] == 'left_only'].copy()
    matched_df = merged[merged['_merge'] == 'both'].copy()

    if matched_df.empty:
        st.error("❌ No matching Question IDs found. Make sure your response sheet belongs to the date/shift selected in the Answer Key.")
        st.stop()

    def evaluate_status(row):
        chosen = str(row["YourOptionID"]).strip()
        if chosen == "None" or chosen == "" or pd.isna(row["YourOptionID"]):
            return "⚪ Unattempted"
        
        official = str(row["OfficialOptionID"])
        accepted = [x.strip() for x in official.split(",")]
        return "🟢 Correct" if chosen in accepted else "🔴 Wrong"

    matched_df["Status"] = matched_df.apply(evaluate_status, axis=1)

    correct     = len(matched_df[matched_df["Status"] == "🟢 Correct"])
    wrong       = len(matched_df[matched_df["Status"] == "🔴 Wrong"])
    unattempted = len(matched_df[matched_df["Status"] == "⚪ Unattempted"])
    missing     = len(missing_df)
    
    total_attempted = correct + wrong
    score = correct * MARKS_CORRECT + wrong * MARKS_WRONG

    # ── Tabs Setup ─────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["🏆 Score Dashboard", "📊 Subject Analysis", "🔍 Question Inspector", f"⚠️ Missing/Dropped ({missing})"])

    with tab1:
        st.markdown("### 🎯 Your Performance")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Score", score)
        c2.metric("🟢 Correct", correct)
        c3.metric("🔴 Wrong", wrong)
        c4.metric("⚪ Unattempted", unattempted)
        c5.metric("Attempt Accuracy", f"{(correct / total_attempted * 100) if total_attempted else 0:.1f}%")

        if PLOTLY_SUPPORT:
            col_chart1, col_chart2 = st.columns([1, 2])
            with col_chart1:
                pie_data = pd.DataFrame({
                    "Status": ["Correct", "Wrong", "Unattempted"],
                    "Count": [correct, wrong, unattempted]
                })
                fig1 = px.pie(pie_data, values='Count', names='Status', hole=0.7, 
                              color='Status', color_discrete_map={"Correct":"#10B981", "Wrong":"#EF4444", "Unattempted":"#F59E0B"})
                fig1.update_layout(margin=dict(t=40, b=0, l=0, r=0), showlegend=False, 
                                   annotations=[dict(text=f'{score} pts', x=0.5, y=0.5, font_size=24, showarrow=False)])
                st.plotly_chart(fig1, use_container_width=True)
            
            with col_chart2:
                if "Subject" in matched_df.columns:
                    subj_stats = matched_df.groupby(["Subject", "Status"]).size().reset_index(name="Count")
                    fig2 = px.bar(subj_stats, x="Subject", y="Count", color="Status", 
                                  color_discrete_map={"🟢 Correct":"#10B981", "🔴 Wrong":"#EF4444", "⚪ Unattempted":"#F59E0B"},
                                  barmode="stack", title="Questions by Subject")
                    fig2.update_layout(margin=dict(t=40, b=0, l=0, r=0), xaxis_title="", yaxis_title="Questions")
                    st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        st.markdown("### 📚 Subject-wise Breakdown")
        if "Subject" in matched_df.columns:
            def subj_agg(df):
                c = len(df[df["Status"] == "🟢 Correct"])
                w = len(df[df["Status"] == "🔴 Wrong"])
                u = len(df[df["Status"] == "⚪ Unattempted"])
                s = c * MARKS_CORRECT + w * MARKS_WRONG
                return pd.Series({"Correct": c, "Wrong": w, "Unattempted": u, "Score": s})
            
            summary = matched_df.groupby("Subject").apply(subj_agg).reset_index()
            summary.insert(1, "Total Assigned", summary["Correct"] + summary["Wrong"] + summary["Unattempted"])
            st.dataframe(summary, use_container_width=True, hide_index=True)
        else:
            st.info("Subject information not available in the Answer Key.")

    with tab3:
        st.markdown("### 🔍 Detailed Question Report")
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            status_filter = st.multiselect("Filter by Status", ["🟢 Correct", "🔴 Wrong", "⚪ Unattempted"], default=["🟢 Correct", "🔴 Wrong", "⚪ Unattempted"])
        
        display_df = matched_df[matched_df["Status"].isin(status_filter)].copy()
        
        cols_to_show = ["QuestionID", "ChosenOption", "YourOptionID", "OfficialOptionID", "Status"]
        if "Subject" in display_df.columns: cols_to_show.insert(0, "Subject")
        
        st.dataframe(display_df[cols_to_show], use_container_width=True, hide_index=True)

        st.download_button("⬇️ Download Detailed Report (CSV)", display_df.to_csv(index=False), "cuet_detailed_report.csv", "text/csv")

    with tab4:
        st.markdown("### ⚠️ Missing / Dropped Questions")
        st.markdown("""
        These questions were present in your response sheet but **not found in the Answer Key** you loaded. 
        This usually happens if:
        1. The question was officially **Dropped** by the NTA.
        2. You filtered out a subject that was present in your paper.
        """)
        
        if missing > 0:
            st.warning(f"Found {missing} missing questions.")
            st.dataframe(missing_df[["QuestionID", "ChosenOption", "YourOptionID"]], use_container_width=True, hide_index=True)
        else:
            st.success("🎉 All questions in your response sheet successfully matched with the answer key!")
