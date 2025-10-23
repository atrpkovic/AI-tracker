import os
import sys
import json
import requests
from dotenv import load_dotenv
from pathlib import Path
import csv # Import the CSV module
from datetime import datetime # Import datetime for timestamps

# --- Load Environment Variables ---
env_path = Path(__file__).resolve().parent / "tracker.env" # Assuming you renamed the file back or changed this
load_dotenv(dotenv_path=env_path)
groq_api_key = os.getenv("GROQ_API_KEY")

if not groq_api_key:
    sys.stderr.write("Error: GROQ_API_KEY not found in .env file.\n")
    sys.exit(1)

# --- CSV Configuration ---
CSV_FILENAME = "ai_brand_tracker_log.csv"
CSV_HEADERS = ["timestamp", "prompt", "brand_name", "mentioned", "response"]

# --- Replaces llama3_reply.py ---
def get_ai_response(prompt: str) -> str:
    """
    Queries the Groq API with a given prompt and returns the text response.
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a helpful, neutral research assistant. Provide a direct, factual answer to the user's question."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"]
        return reply.strip().strip('"').strip("'")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API request failed: {e}")
    except (KeyError, IndexError):
        raise RuntimeError("Failed to parse API response from Groq.")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred: {e}")

# --- New Analysis Function ---
def analyze_response(response_text: str, brand_name: str) -> dict:
    """
    Analyzes the AI's response for a brand mention.
    """
    is_mentioned = brand_name.lower() in response_text.lower()
    return {
        "mentioned": is_mentioned,
        "response_text": response_text
    }

# --- New CSV Writing Function ---
def write_results_to_csv(results: list):
    """
    Appends the results of the run to a CSV file. Creates the file if it doesn't exist.
    """
    file_exists = os.path.isfile(CSV_FILENAME)
    try:
        with open(CSV_FILENAME, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_HEADERS)

            # Write header only if the file is new
            if not file_exists:
                writer.writeheader()

            # Add timestamp to each result before writing
            timestamp = datetime.now().isoformat()
            for result in results:
                result_with_timestamp = {
                    "timestamp": timestamp,
                    "prompt": result.get("prompt", ""),
                    "brand_name": result.get("brand_name", ""),
                    "mentioned": result.get("mentioned", ""),
                    "response": result.get("response", "")
                 }
                writer.writerow(result_with_timestamp)
        # sys.stdout.write(f"Successfully wrote {len(results)} rows to {CSV_FILENAME}\n") # Optional: Confirmation message
    except Exception as e:
        sys.stderr.write(f"Error writing to CSV file {CSV_FILENAME}: {e}\n")


# --- Modified Main Logic ---
def main():
    """
    Main execution function. Reads config, queries AI, analyzes,
    writes to CSV, and prints results to stdout.
    """
    final_results = [] # Initialize here to ensure it's always defined
    try:
        input_data = json.load(sys.stdin)
        brand_to_track = input_data.get("brand_name")
        prompts_to_run = input.get("prompts")

        if not brand_to_track or not prompts_to_run:
            raise ValueError("Input JSON must contain 'brand_name' and a list of 'prompts'.")

        # Process each prompt
        for prompt in prompts_to_run:
            try:
                ai_response = get_ai_response(prompt)
                analysis = analyze_response(ai_response, brand_to_track)

                final_results.append({
                    "prompt": prompt,
                    "brand_name": brand_to_track,
                    "mentioned": analysis["mentioned"],
                    "response": analysis["response_text"]
                })

            except Exception as e:
                sys.stderr.write(f"Error processing prompt '{prompt}': {e}\n")
                final_results.append({
                    "prompt": prompt,
                    "brand_name": brand_to_track,
                    "mentioned": False,
                    "response": f"Error: {e}"
                })

        # --- Write results to CSV ---
        if final_results:
             write_results_to_csv(final_results)

        # --- Print results to stdout for n8n ---
        print(json.dumps(final_results, indent=2))

    except json.JSONDecodeError:
        sys.stderr.write("Error: Invalid JSON received on stdin.\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"A critical error occurred: {e}\n")
        # Ensure CSV is written even on critical error, if results were collected
        if final_results:
             write_results_to_csv(final_results)
        sys.exit(1)

if __name__ == "__main__":
    main()