import re
import calendar
from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="CoE Statistics", layout="wide")
st.title("CoE Statistics Report")
st.write("Upload the audit export CSV to calculate the previous month's and year-to-date Challenge on Entry rates.")

uploaded = st.file_uploader("Upload audit export CSV", type=["csv"])

CHALLENGE_COLUMN = "secondary_result"
DATE_COLUMN = "date_of_visit_local"
CLIENT_COLUMN = "client_name"
POSTCODE_COLUMN = "site_post_code"
ABORT_COLUMN = "primary_result"

def clean_text(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).casefold()

def classify_region(postcode):
    pc = re.sub(r"[^A-Z0-9]", "", str(postcode).upper()) if pd.notna(postcode) else ""
    if not pc:
        return "Unknown"
    if pc.startswith("BT"):
        return "NI"
    # Irish Eircodes use a three-character routing key followed by four characters.
    if re.match(r"^(?:D0[1-9]|D1[0-9]|D2[0-4]|D6W)[A-Z0-9]{4}$", pc):
        return "ROI"
    if re.match(r"^[ACDEFHKMNPRTVWXY][0-9][A-Z0-9]{4}$", pc):
        return "ROI"
    if re.match(r"^[A-Z]{1,2}[0-9]", pc):
        return "GB"
    return "Unknown"

def is_challenge_on_entry(value):
    s = re.sub(r"[^a-z0-9]+", " ", clean_text(value)).strip()
    return bool(re.search(r"\bchalleng(?:e|ed|ing)\b.*\b(?:on|upon|at)\s+entry\b", s))

def rate(subset):
    if subset.empty:
        return "—"
    return f"{subset['_challenge'].sum() / len(subset):.0%}"

if uploaded:
    try:
        df = pd.read_csv(uploaded, low_memory=False)
    except Exception as exc:
        st.error(f"Could not read the CSV: {exc}")
        st.stop()

    required = [CLIENT_COLUMN, DATE_COLUMN, POSTCODE_COLUMN, CHALLENGE_COLUMN, ABORT_COLUMN]
    missing = [col for col in required if col not in df.columns]
    if missing:
        st.error("The export is missing required column(s): " + ", ".join(missing))
        st.stop()

    df["_visit_date"] = pd.to_datetime(df[DATE_COLUMN], dayfirst=True, errors="coerce")
    df["_region"] = df[POSTCODE_COLUMN].apply(classify_region)
    df["_challenge"] = df[CHALLENGE_COLUMN].apply(is_challenge_on_entry)
    df["_client"] = df[CLIENT_COLUMN].apply(clean_text)
    df["_aborted"] = df[ABORT_COLUMN].apply(lambda x: "abort" in clean_text(x))

    today = date.today()
    first_this_month = date(today.year, today.month, 1)
    last_prev_month = first_this_month.fromordinal(first_this_month.toordinal() - 1)
    report_year, report_month = last_prev_month.year, last_prev_month.month
    month_start = pd.Timestamp(report_year, report_month, 1)
    period_end = pd.Timestamp(last_prev_month) + pd.Timedelta(days=1)
    ytd_start = pd.Timestamp(report_year, 1, 1)
    month_label = calendar.month_name[report_month]

    valid = df.loc[~df["_aborted"] & df["_visit_date"].notna()].copy()
    valid["_in_month"] = (valid["_visit_date"] >= month_start) & (valid["_visit_date"] < period_end)
    valid["_in_ytd"] = (valid["_visit_date"] >= ytd_start) & (valid["_visit_date"] < period_end)

    rows = []
    for region in ["GB", "NI", "ROI"]:
        for label in ["Ladbrokes Coral", "Betting Industry (Incl. LC)", "Betting Industry (Excl. LC)"]:
            def select(period):
                subset = valid.loc[(valid["_region"] == region) & valid[period]]
                if label == "Ladbrokes Coral":
                    subset = subset.loc[subset["_client"] == "ladbrokes coral"]
                elif label == "Betting Industry (Excl. LC)":
                    subset = subset.loc[subset["_client"] != "ladbrokes coral"]
                return subset
            m, y = select("_in_month"), select("_in_ytd")
            rows.append({
                "": f"CoE Rate {region}" if label == "Ladbrokes Coral" else "",
                "Client / Industry": label,
                f"Month ({month_label})": rate(m),
                "YTD": rate(y),
            })

    result = pd.DataFrame(rows)
    st.subheader("Results")
    st.caption(f"Month: {month_start:%d %b %Y} – {(period_end - pd.Timedelta(days=1)):%d %b %Y} · YTD: {ytd_start:%d %b %Y} – {(period_end - pd.Timedelta(days=1)):%d %b %Y}")
    st.dataframe(result, hide_index=True, use_container_width=True)

    tsv = result.to_csv(sep="\t", index=False)
    st.text_area("Copy table for your email (select all and copy)", value=tsv, height=250)

    plain_text = result.to_markdown(index=False)
    st.download_button(
        "Download plain text report",
        data=plain_text.encode("utf-8"),
        file_name="CoE Statistics.txt",
        mime="text/plain",
        type="primary",
    )

    with st.expander("Calculation checks"):
        st.write("Audits included (non-aborted with a valid date):", len(valid))
        st.dataframe(valid["_region"].value_counts().rename_axis("Region").reset_index(name="Audits"), hide_index=True)
        st.write("Unclassified postcodes:", int((valid["_region"] == "Unknown").sum()))
        st.write("Challenge-on-entry answers counted:", int(valid["_challenge"].sum()))
        st.write("Aborted audits excluded:", int(df["_aborted"].sum()))

