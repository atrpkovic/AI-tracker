import os
import sys
import json
import requests
import csv
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import google.generativeai as genai # Import Google library

# --- Load Environment Variables ---
env_path = Path(__file__).resolve().parent / "tracker.env" # Make sure this matches your .env filename
load_dotenv(dotenv_path=env_path)

# Load API Keys
groq_api_key = os.getenv("GROQ_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY") # Load Google API key

# Configure Google Gemini
if google_api_key:
    try:
        genai.configure(api_key=google_api_key)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to configure Google Gemini API: {e}\n")
        google_api_key = None # Disable Gemini if configuration fails
else:
    sys.stderr.write("Warning: GOOGLE_API_KEY not found in .env file. Gemini queries will be skipped.\n")

# --- CSV Configuration ---
CSV_FILENAME = "ai_brand_tracker_log.csv"
# Add 'model' column
CSV_HEADERS = ["timestamp", "model", "prompt", "brand_name", "mentioned", "response"]

# --- Function to Query AI Models ---
def get_ai_response(prompt: str, model_name: str) -> str:
    """
    Queries the specified AI model (Groq or Gemini) and returns the text response.
    """
    if model_name.lower() == 'groq':
        if not groq_api_key:
            raise RuntimeError("Groq API key not configured.")
        return query_groq(prompt)
    elif model_name.lower() == 'gemini':
        if not google_api_key:
            raise RuntimeError("Google Gemini API key not configured.")
        return query_gemini(prompt)
    else:
        raise ValueError(f"Unsupported model specified: {model_name}")

def query_groq(prompt: str) -> str:
    """Queries the Groq API."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile", # Or whichever Groq model you prefer
        "messages": [
            {"role": "system", "content": "You are a helpful, neutral research assistant. Provide a direct, factual answer."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45) # Increased timeout
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"]
        return reply.strip().strip('"').strip("'")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Groq API request failed: {e}")
    except (KeyError, IndexError):
        raise RuntimeError("Failed to parse API response from Groq.")
    except Exception as e:
        raise RuntimeError(f"An unexpected Groq error occurred: {e}")

def query_gemini(prompt: str) -> str:
    """Queries the Google Gemini API."""
    try:
        # Using a recent, generally available model
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        # Handle potential safety blocks or empty responses
        if not response.parts:
             if response.prompt_feedback.block_reason:
                 return f"Gemini Error: Blocked - {response.prompt_feedback.block_reason}"
             else:
                 return "Gemini Error: Empty response received."
        # Accessing text safely
        if hasattr(response.parts[0], 'text'):
             return response.parts[0].text.strip()
        else:
             # Handle cases where the first part might not be text (e.g., function call)
             return "Gemini Error: Response format not recognized as text."

    except Exception as e:
        raise RuntimeError(f"Google Gemini API error: {e}")


# --- Analysis Function (Unchanged) ---
def analyze_response(response_text: str, brand_name: str) -> dict:
    """Analyzes the AI's response for a brand mention."""
    is_mentioned = brand_name.lower() in response_text.lower()
    return {
        "mentioned": is_mentioned,
        "response_text": response_text
    }

# --- CSV Writing Function (Updated) ---
def write_results_to_csv(results: list):
    """Appends results to CSV, includes 'model' column."""
    file_exists = os.path.isfile(CSV_FILENAME)
    try:
        with open(CSV_FILENAME, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_HEADERS)
            if not file_exists:
                writer.writeheader()

            timestamp = datetime.now().isoformat()
            for result in results:
                # Add timestamp and ensure all keys exist
                row_data = {
                    "timestamp": timestamp,
                    "model": result.get("model", "unknown"), # Add model
                    "prompt": result.get("prompt", ""),
                    "brand_name": result.get("brand_name", ""),
                    "mentioned": result.get("mentioned", ""),
                    "response": result.get("response", "")
                 }
                writer.writerow(row_data)
    except Exception as e:
        sys.stderr.write(f"Error writing to CSV file {CSV_FILENAME}: {e}\n")


# --- Main Logic (Updated) ---
def main():
    """Reads config, queries specified AI models, analyzes, writes to CSV, and prints JSON."""
    final_results = []
    try:
        input_data = json.load(sys.stdin)
        brand_to_track = input_data.get("brand_name")
        prompts_to_run = input_data.get("prompts")
        # Get list of models to query, default to Groq if not specified
        models_to_query = input_data.get("models", ["groq"])

        if not brand_to_track or not prompts_to_run:
            raise ValueError("Input JSON must contain 'brand_name' and a list of 'prompts'.")

        # Check for API key availability based on requested models
        if "groq" in [m.lower() for m in models_to_query] and not groq_api_key:
             sys.stderr.write("Warning: 'groq' requested but GROQ_API_KEY is missing. Skipping Groq queries.\n")
             models_to_query = [m for m in models_to_query if m.lower() != 'groq']
        if "gemini" in [m.lower() for m in models_to_query] and not google_api_key:
             sys.stderr.write("Warning: 'gemini' requested but GOOGLE_API_KEY is missing or invalid. Skipping Gemini queries.\n")
             models_to_query = [m for m in models_to_query if m.lower() != 'gemini']

        if not models_to_query:
            raise RuntimeError("No valid models with available API keys specified.")


        # Process each prompt for each specified model
        for prompt in prompts_to_run:
            for model_name in models_to_query:
                try:
                    ai_response = get_ai_response(prompt, model_name)
                    analysis = analyze_response(ai_response, brand_to_track)

                    final_results.append({
                        "model": model_name, # Record which model gave the answer
                        "prompt": prompt,
                        "brand_name": brand_to_track,
                        "mentioned": analysis["mentioned"],
                        "response": analysis["response_text"]
                    })

                except Exception as e:
                    sys.stderr.write(f"Error processing prompt '{prompt}' with model '{model_name}': {e}\n")
                    final_results.append({
                        "model": model_name, # Still record the model
                        "prompt": prompt,
                        "brand_name": brand_to_track,
                        "mentioned": False,
                        "response": f"Error: {e}"
                    })

        # Write results to CSV
        if final_results:
             write_results_to_csv(final_results)

        # Print results to stdout for n8n
        print(json.dumps(final_results, indent=2))

    except json.JSONDecodeError:
        sys.stderr.write("Error: Invalid JSON received on stdin.\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"A critical error occurred: {e}\n")
        if final_results:
             write_results_to_csv(final_results) # Attempt to save partial results
        sys.exit(1)

if __name__ == "__main__":
    main()