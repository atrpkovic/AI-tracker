import os
import sys
import json
import requests
import csv
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import google.generativeai as genai


# --- Load Environment Variables ---
env_path = Path(__file__).resolve().parent / "tracker.env"
load_dotenv(dotenv_path=env_path)

groq_api_key = os.getenv("GROQ_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")

# Configure Google Gemini
if google_api_key:
    try:
        genai.configure(api_key=google_api_key)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to configure Google Gemini API: {e}\n")
        google_api_key = None
else:
    sys.stderr.write("Warning: GOOGLE_API_KEY not found in .env file. Gemini queries will be skipped.\n")

# --- CSV Configuration ---
CSV_FILENAME = "ai_brand_tracker_log.csv"
CSV_HEADERS = ["timestamp", "model", "prompt", "brand_name", "mentioned", "response"]


# --- Model Query Functions ---
def get_ai_response(prompt: str, model_name: str) -> str:
    if model_name.lower() == "groq":
        if not groq_api_key:
            raise RuntimeError("Groq API key not configured.")
        return query_groq(prompt)
    elif model_name.lower() == "gemini":
        if not google_api_key:
            raise RuntimeError("Google Gemini API key not configured.")
        return query_gemini(prompt)
    else:
        raise ValueError(f"Unsupported model specified: {model_name}")


def query_groq(prompt: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {groq_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a helpful, neutral research assistant. Provide a direct, factual answer."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)
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
    try:
        model = genai.GenerativeModel("gemini-1.5-flash-latest")
        response = model.generate_content(prompt)

        if not response.parts:
            if hasattr(response, "prompt_feedback") and response.prompt_feedback.block_reason:
                return f"Gemini Error: Blocked - {response.prompt_feedback.block_reason}"
            return "Gemini Error: Empty response received."

        if hasattr(response.parts[0], "text"):
            return response.parts[0].text.strip()
        return "Gemini Error: Response format not recognized as text."
    except Exception as e:
        raise RuntimeError(f"Google Gemini API error: {e}")


# --- Helper Functions ---
def analyze_response(response_text: str, brand_name: str) -> dict:
    is_mentioned = brand_name.lower() in response_text.lower()
    return {"mentioned": is_mentioned, "response_text": response_text}


def write_results_to_csv(results: list):
    file_exists = os.path.isfile(CSV_FILENAME)
    try:
        with open(CSV_FILENAME, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_HEADERS)
            if not file_exists:
                writer.writeheader()

            timestamp = datetime.now().isoformat()
            for result in results:
                row = {
                    "timestamp": timestamp,
                    "model": result.get("model", "unknown"),
                    "prompt": result.get("prompt", ""),
                    "brand_name": result.get("brand_name", ""),
                    "mentioned": result.get("mentioned", ""),
                    "response": result.get("response", ""),
                }
                writer.writerow(row)
    except Exception as e:
        sys.stderr.write(f"Error writing to CSV file {CSV_FILENAME}: {e}\n")


# --- Main Logic ---
def main():
    final_results = []

    try:
        input_path = Path(__file__).resolve().parent / "input.json"
        with open(input_path, "r", encoding="utf-8") as f:
            input_data = json.load(f)

        brand_to_track = input_data.get("brand_name")
        prompts_to_run = input_data.get("prompts")
        models_to_query = input_data.get("models", ["groq"])

        if not brand_to_track or not prompts_to_run:
            raise ValueError("Input JSON must contain 'brand_name' and a list of 'prompts'.")

        if "groq" in [m.lower() for m in models_to_query] and not groq_api_key:
            sys.stderr.write("Warning: 'groq' requested but GROQ_API_KEY is missing. Skipping Groq queries.\n")
            models_to_query = [m for m in models_to_query if m.lower() != "groq"]
        if "gemini" in [m.lower() for m in models_to_query] and not google_api_key:
            sys.stderr.write("Warning: 'gemini' requested but GOOGLE_API_KEY is missing or invalid. Skipping Gemini queries.\n")
            models_to_query = [m for m in models_to_query if m.lower() != "gemini"]

        if not models_to_query:
            raise RuntimeError("No valid models with available API keys specified.")

        # Process prompts
        for prompt in prompts_to_run:
            for model_name in models_to_query:
                try:
                    ai_response = get_ai_response(prompt, model_name)
                    analysis = analyze_response(ai_response, brand_to_track)
                    final_results.append({
                        "model": model_name,
                        "prompt": prompt,
                        "brand_name": brand_to_track,
                        "mentioned": analysis["mentioned"],
                        "response": analysis["response_text"],
                    })
                except Exception as e:
                    sys.stderr.write(f"Error processing prompt '{prompt}' with model '{model_name}': {e}\n")
                    final_results.append({
                        "model": model_name,
                        "prompt": prompt,
                        "brand_name": brand_to_track,
                        "mentioned": False,
                        "response": f"Error: {e}",
                    })

        if final_results:
            write_results_to_csv(final_results)

        print(json.dumps(final_results, indent=2))

    except Exception as e:
        sys.stderr.write(f"A critical error occurred: {e}\n")
        if final_results:
            write_results_to_csv(final_results)
        sys.exit(1)


if __name__ == "__main__":
    main()
