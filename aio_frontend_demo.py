import streamlit as st
import pandas as pd
import os
# Import SERPAPI_KEY directly from the backend logic file
from tracker_logic import process_keyword, check_serpapi_account, BRANDS_FILE, SERPAPI_KEY
import time

# --- Page Configuration ---
st.set_page_config(
    page_title="AI Overview Brand Tracker",
    page_icon="🤖",
    layout="wide"
)

# --- Main UI ---
st.title("🤖 AI Overview Brand Tracker")
st.markdown("This tool scans Google's AI Overviews for brand mentions based on a list of keywords.")

# --- Inputs on Main Page (Moved from Sidebar) ---
st.header("Configuration")

# --- API Key input is REMOVED ---
# The app will now use the SERPAPI_KEY from tracker_logic.py

default_keywords = "best running shoes\nbest coffee maker\nwhat is generative ai"
keywords_input = st.text_area(
    "Enter keywords (one per line)", 
    default_keywords,
    height=250
)

# Run Button
run_button = st.button("Run Tracker", type="primary")


# --- Main Content Area for Results ---
if run_button:
    # --- UPDATED CHECK ---
    # Check if the hardcoded key in the backend file is valid
    if not SERPAPI_KEY or SERPAPI_KEY == "5d3f50d427ec0c756bc4c02d12d8d6461e4b31dd1d0190d310bc447993ceb27b": # Or whatever your placeholder is
        st.error("Error: SERPAPI_KEY is not set in tracker_logic.py.")
        st.markdown("Please edit the `tracker_logic.py` file and add your valid SerpApi key to the `SERPAPI_KEY` variable.")
        st.stop()
        
    if not keywords_input:
        st.error("Please enter at least one keyword.")
        st.stop()
        
    # Check for brands.json
    if not os.path.exists(BRANDS_FILE):
        st.error(f"Error: '{BRANDS_FILE}' not found.")
        st.markdown(f"Please create or upload a `{BRANDS_FILE}` file to your app's repository. It should look like this:")
        st.code("""
{
    "nike.com": ["nike", "air jordan"],
    "adidas.com": ["adidas", "adipure"],
    "example.com": ["example brand"]
}
        """, language="json")
        st.stop()

    # Process keywords
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    total_keywords = len(keywords)
    
    st.info(f"Processing {total_keywords} keywords... This may take a moment.")

    # Check SerpApi Account
    with st.spinner("Checking SerpApi account..."):
        # --- UPDATED CALL (no api_key argument) ---
        account_info = check_serpapi_account()
        if account_info:
            searches_left = account_info.get('searches_left', 'N/A')
            st.success(f"SerpApi account check OK. Searches left: {searches_left}")
        else:
            st.warning("Could not verify SerpApi account, but will proceed. Check your API key in tracker_logic.py if errors occur.")

    # Placeholders for results
    progress_bar = st.progress(0)
    summary_placeholder = st.empty()
    
    all_brand_hits = []
    summary_log = []
    
    start_time = time.time()

    for i, keyword in enumerate(keywords, 1):
        status_text = f"Processing: '{keyword}' ({i}/{total_keywords})"
        # This is a small update to make the log cleaner in Streamlit
        log_message_placeholder = st.empty()
        log_message_placeholder.text(status_text)
        
        try:
            # --- UPDATED CALL (no api_key argument) ---
            rows, status = process_keyword(keyword, BRANDS_FILE)
            
            # Update summary log
            if status == "SUCCESS":
                if rows:
                    log_entry = f"✅ Found {len(rows)} brand(s) for: '{keyword}'"
                    all_brand_hits.extend(rows)
                else:
                    log_entry = f"ℹ️ AIO found, but no matching brands for: '{keyword}'"
            elif status == "NO_AIO":
                log_entry = f"⚠️ No AI Overview found for: '{keyword}'"
            elif status == "INVALID_AIO":
                log_entry = f"❌ Invalid AIO structure for: '{keyword}'"
            else: # API_ERROR
                log_entry = f"❌ API Error processing: '{keyword}'"
            
            summary_log.append(log_entry)
            log_message_placeholder.empty() # Clear the "Processing..." line

        except Exception as e:
            st.error(f"An unexpected error occurred processing '{keyword}': {e}")
            summary_log.append(f"🔥 UNEXPECTED ERROR for: '{keyword}'")
            log_message_placeholder.empty() # Clear the "Processing..." line

        # Update UI
        progress_bar.progress(i / total_keywords)
        # Display log in reverse so newest is at top
        summary_placeholder.markdown("### Processing Log\n" + "\n".join(f"- {s}" for s in reversed(summary_log)))

    end_time = time.time()
    st.success(f"Processing complete in {end_time - start_time:.2f} seconds!")

    # --- Display Final Results ---
    if all_brand_hits:
        st.subheader("Brand Mentions Found")
        
        # Create DataFrame
        try:
            df = pd.DataFrame(
                all_brand_hits, 
                columns=["Timestamp", "Keyword", "Brand", "Matched Term", "Context", "URL", "Source"]
            )
            
            # Display the DataFrame
            st.dataframe(df)
            
            # Download Button
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Results as CSV",
                data=csv_data,
                file_name="ai_overview_brand_hits.csv",
                mime="text/csv",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Error creating DataFrame: {e}")
            st.json(all_brand_hits) # Fallback to JSON
            
    else:
        st.info("No brand mentions were found in the AI Overviews for the given keywords.")

