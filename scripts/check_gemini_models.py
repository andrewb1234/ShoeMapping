"""Check available Gemini models on the current API key."""

import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Initialize API
api_key = os.getenv('GOOGLE_GEMINI_API_KEY')
if not api_key:
    print("Error: GOOGLE_GEMINI_API_KEY not found in environment variables")
    exit(1)

genai.configure(api_key=api_key)

# List all available models
print("Available models:")
for model in genai.list_models():
    # Filter for generative models
    if 'generateContent' in model.supported_generation_methods:
        print(f"- {model.name}")
        print(f"  Display name: {model.display_name}")
        print(f"  Description: {model.description}")
        print(f"  Generation methods: {model.supported_generation_methods}")
        print()
