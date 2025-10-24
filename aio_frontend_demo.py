import streamlit as st
import pandas as pd
import subprocess
import os
from datetime import datetime

st.set_page_config(page_title="AI Overview Brand Tracker Demo", layout="wide")

st.title("🧠 AI Overview Brand Tracker Demo")
st.caption("Monitor your brand mentions inside Google’s AI Overviews in real time.")

# --- Input section
st.subheader("Keyword Input")
keywords_text = st.text_area("Enter one keyword per line:", "PriorityTire vs SimpleTire\nBest budget-friendly tire webshop")
brands_file = st.file_uploader("Upload your brands.json file", type="json")

run_btn = st.button("🚀 Run Tracker")

if run_btn:
    if not brands_file:
        st.error("Please upload a brands.json file.")
    else:
        # Save temp keywords and brands
        with open("demo_keywords.csv", "w", encoding="utf-8") as f:
            f.write("\n".join(keywords_text.strip().splitlines()))
        brands_path = "demo_brands.json"
        with open(brands_path, "wb") as f:
            f.write(brands_file.getbuffer())

        st.info("Running AI Overview tracker... This can take a few minutes.")
        with st.spinner("Collecting AI Overview data..."):
            result = subprocess.run(
                ["python", "ai_brand_tracker.py"],
                capture_output=True,
                text=True
            )
        st.success("Run completed!")

        # Display console log
        st.subheader("Console Log")
        st.code(result.stdout)

        # Display results if available
        if os.path.exists("ai_overview_brand_hits_master.csv"):
            df = pd.read_csv("ai_overview_brand_hits_master.csv")
            st.subheader("Results")
            st.dataframe(df)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            out_name = f"ai_overview_results_{timestamp}.csv"
            st.download_button(
                "💾 Download Results CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=out_name,
                mime="text/csv"
            )
        else:
            st.warning("No results file found. Please check your API key and console logs.")
