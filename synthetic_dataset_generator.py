"""Synthetic dataset generator for shoe similarity scoring using Gemini API.

This module creates a supervised dataset by sampling random shoe pairs and
getting similarity scores from the Gemini LLM based on their lab test results.
"""

import json
import logging
import os
import random
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any

import google.generativeai as genai
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/runrepeat_lab_tests.sqlite")
DEFAULT_FEATURES = [
    "Drop",
    "Heel stack", 
    "Forefoot stack",
    "Energy return heel",
    "Weight",
    "Midsole softness (old method)",
    "Torsional rigidity",
]

FEATURE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "Drop": ("Drop",),
    "Heel stack": ("Heel stack",),
    "Forefoot stack": ("Forefoot stack",),
    "Energy return heel": ("Energy return heel", "Energy return (heel)", "Energy return"),
    "Weight": ("Weight",),
    "Midsole softness (old method)": ("Midsole softness (old method)", "Midsole softness"),
    "Torsional rigidity": ("Torsional rigidity",),
}


def load_shoes_from_db(db_path: Path = DEFAULT_DB_PATH) -> pd.DataFrame:
    """Load all shoes from the database and flatten lab test results."""
    conn = sqlite3.connect(db_path)
    
    # Load basic shoe data
    df = pd.read_sql_query("SELECT shoe_id, brand, shoe_name, lab_test_results FROM shoes", conn)
    conn.close()
    
    # Filter out shoes with no lab test results
    df = df[df['lab_test_results'].notna()].copy()
    
    # Parse JSON lab test results
    lab_results = df['lab_test_results'].apply(json.loads)
    
    # Create feature columns
    for feature in DEFAULT_FEATURES:
        df[feature] = None
        
    # Extract features using aliases
    for idx, results in enumerate(lab_results):
        for feature, aliases in FEATURE_ALIASES.items():
            for alias in aliases:
                if alias in results and results[alias] is not None:
                    # Try to convert to numeric
                    try:
                        value = float(str(results[alias]).replace('mm', '').replace('g', '').strip())
                        df.at[df.index[idx], feature] = value
                        break
                    except (ValueError, TypeError):
                        continue
    
    # Filter to shoes with at least some features
    feature_cols = [col for col in df.columns if col in DEFAULT_FEATURES]
    df = df.dropna(subset=feature_cols, thresh=3).copy()  # Require at least 3 features
    
    logger.info(f"Loaded {len(df)} shoes with lab test data")
    return df


def init_gemini() -> Any:
    """Initialize Gemini API with API key from environment."""
    api_key = os.getenv('GOOGLE_GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GOOGLE_GEMINI_API_KEY not found in environment variables")
    
    genai.configure(api_key=api_key)
    # Use gemini-2.5-flash which is available on free tier
    model = genai.GenerativeModel('gemini-2.5-flash')
    return model


def create_similarity_prompt(shoe_a: Dict[str, Any], shoe_b: Dict[str, Any]) -> str:
    """Create a prompt for Gemini to rate shoe similarity."""
    
    # Format shoe specs for the prompt
    def format_shoe_specs(shoe: Dict[str, Any]) -> str:
        specs = []
        for feature in DEFAULT_FEATURES:
            if feature in shoe and shoe[feature] is not None:
                specs.append(f"{feature}: {shoe[feature]}")
        return "\n".join(specs) if specs else "No specifications available"
    
    prompt = f"""You are an expert running shoe fitter. I am going to give you the lab specifications for Shoe A and Shoe B.

Shoe A ({shoe_a['brand']} {shoe_a['shoe_name']}):
{format_shoe_specs(shoe_a)}

Shoe B ({shoe_b['brand']} {shoe_b['shoe_name']}):
{format_shoe_specs(shoe_b)}

Rate how good of an alternative Shoe B is for a runner who loves Shoe A on a scale of 0 to 100. Consider:
- Drop (heel-to-toe offset) differences
- Stack height and cushioning similarity  
- Weight differences
- Energy return characteristics
- Overall ride feel based on the lab measurements

Output ONLY a JSON object like {{"similarity_score": 85}} where 100 means a perfect alternative and 0 means completely unsuitable."""
    
    return prompt


def get_gemini_similarity_score(model: Any, shoe_a: Dict[str, Any], shoe_b: Dict[str, Any]) -> float:
    """Get similarity score from Gemini API for a shoe pair."""
    
    prompt = create_similarity_prompt(shoe_a, shoe_b)
    
    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Extract JSON from response
        if '{' in response_text and '}' in response_text:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_str = response_text[json_start:json_end]
            
            result = json.loads(json_str)
            score = float(result.get('similarity_score', 0))
            return max(0, min(100, score))  # Clamp to 0-100 range
        
    except Exception as e:
        logger.warning(f"Error getting Gemini score for {shoe_a['shoe_name']} vs {shoe_b['shoe_name']}: {e}")
    
    return 0.0


def generate_synthetic_dataset(
    db_path: Path = DEFAULT_DB_PATH,
    output_path: Path = Path("data/synthetic_similarity_dataset.csv"),
    num_pairs: int = 10000,
    batch_size: int = 100,
    max_retries: int = 3
) -> None:
    """Generate synthetic dataset of shoe similarity scores."""
    
    logger.info(f"Generating synthetic dataset with {num_pairs} shoe pairs")
    
    # Load shoes from database
    shoes_df = load_shoes_from_db(db_path)
    if len(shoes_df) < 2:
        raise ValueError("Need at least 2 shoes with lab data to generate pairs")
    
    # Initialize Gemini
    model = init_gemini()
    
    # Prepare output data
    dataset = []
    
    # Generate random pairs
    for batch_start in range(0, num_pairs, batch_size):
        batch_end = min(batch_start + batch_size, num_pairs)
        batch_pairs = batch_end - batch_start
        
        logger.info(f"Processing batch {batch_start//batch_size + 1}: pairs {batch_start+1}-{batch_end}")
        
        for i in range(batch_pairs):
            # Sample two random shoes
            shoe_a_idx, shoe_b_idx = random.sample(range(len(shoes_df)), 2)
            shoe_a = shoes_df.iloc[shoe_a_idx]
            shoe_b = shoes_df.iloc[shoe_b_idx]
            
            # Prepare shoe data for prompt
            shoe_a_data = {
                'brand': shoe_a['brand'],
                'shoe_name': shoe_a['shoe_name'],
                **{feature: shoe_a[feature] for feature in DEFAULT_FEATURES if pd.notna(shoe_a[feature])}
            }
            shoe_b_data = {
                'brand': shoe_b['brand'],
                'shoe_name': shoe_b['shoe_name'],
                **{feature: shoe_b[feature] for feature in DEFAULT_FEATURES if pd.notna(shoe_b[feature])}
            }
            
            # Get similarity score with retries
            similarity_score = 0.0
            for attempt in range(max_retries):
                similarity_score = get_gemini_similarity_score(model, shoe_a_data, shoe_b_data)
                if similarity_score > 0:
                    break
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
            
            # Calculate feature differences
            feature_diffs = {}
            for feature in DEFAULT_FEATURES:
                val_a = shoe_a[feature] if pd.notna(shoe_a[feature]) else None
                val_b = shoe_b[feature] if pd.notna(shoe_b[feature]) else None
                
                if val_a is not None and val_b is not None:
                    feature_diffs[f'delta_{feature.lower().replace(" ", "_")}'] = abs(val_a - val_b)
                else:
                    feature_diffs[f'delta_{feature.lower().replace(" ", "_")}'] = None
            
            # Store dataset entry
            entry = {
                'shoe_a_id': shoe_a['shoe_id'],
                'shoe_a_name': f"{shoe_a['brand']} {shoe_a['shoe_name']}",
                'shoe_b_id': shoe_b['shoe_id'],
                'shoe_b_name': f"{shoe_b['brand']} {shoe_b['shoe_name']}",
                'similarity_score': similarity_score,
                **feature_diffs
            }
            dataset.append(entry)
            
            if (batch_start + i + 1) % 10 == 0:
                logger.info(f"Generated {batch_start + i + 1}/{num_pairs} pairs")
        
        # Save batch progress
        if dataset:
            pd.DataFrame(dataset).to_csv(output_path, index=False)
            logger.info(f"Saved intermediate progress to {output_path}")
        
        # Rate limiting - sleep between batches
        if batch_end < num_pairs:
            sleep_time = 1 + (batch_start // batch_size) * 0.5  # Gradually increase delay
            logger.info(f"Sleeping {sleep_time:.1f}s before next batch...")
            time.sleep(sleep_time)
    
    # Final save
    if dataset:
        final_df = pd.DataFrame(dataset)
        final_df.to_csv(output_path, index=False)
        logger.info(f"Generated complete dataset with {len(dataset)} pairs saved to {output_path}")
        
        # Print summary statistics
        logger.info(f"Similarity score stats:")
        logger.info(f"  Mean: {final_df['similarity_score'].mean():.2f}")
        logger.info(f"  Std: {final_df['similarity_score'].std():.2f}")
        logger.info(f"  Min: {final_df['similarity_score'].min():.2f}")
        logger.info(f"  Max: {final_df['similarity_score'].max():.2f}")


if __name__ == "__main__":
    # Generate dataset
    generate_synthetic_dataset(
        num_pairs=100,  # Medium size for better training
        batch_size=25   # Larger batches for faster processing
    )
