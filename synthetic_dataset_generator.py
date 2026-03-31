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
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

# Import clustering functionality
from shoe_clustering import ShoeKMeansClusterer

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


def create_batch_similarity_prompt(shoe_pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> str:
    """Create a prompt for Gemini to rate multiple shoe pairs in a single batch."""
    
    # Format shoe specs for the prompt
    def format_shoe_specs(shoe: Dict[str, Any]) -> str:
        specs = []
        for feature in DEFAULT_FEATURES:
            if feature in shoe and shoe[feature] is not None:
                specs.append(f"{feature}: {shoe[feature]}")
        # Add terrain and support type if available
        if 'Terrain' in shoe and shoe['Terrain'] is not None:
            specs.append(f"Terrain: {shoe['Terrain']}")
        if 'Arch Support' in shoe and shoe['Arch Support'] is not None:
            specs.append(f"Arch Support: {shoe['Arch Support']}")
        return "\n".join(specs) if specs else "No specifications available"
    
    prompt = """You are an expert running shoe fitter. Evaluate the following pairs of shoes.
Rate how good of an alternative Shoe B is for a runner who loves Shoe A (0-100).

Consider:
- Drop (heel-to-toe offset) differences
- Stack height and cushioning similarity  
- Weight differences
- Energy return characteristics
- Terrain compatibility (road vs trail)
- Support type compatibility (neutral vs stability)
- Overall ride feel based on the lab measurements

Respond ONLY with a valid JSON array of objects.
Example format:
[
  {"pair_id": 0, "similarity_score": 85},
  {"pair_id": 1, "similarity_score": 42}
]

Pairs to evaluate:
"""
    
    for i, (shoe_a, shoe_b) in enumerate(shoe_pairs):
        prompt += f"\nPair {i}:\n"
        prompt += f"Shoe A ({shoe_a['brand']} {shoe_a['shoe_name']}):\n"
        prompt += f"{format_shoe_specs(shoe_a)}\n\n"
        prompt += f"Shoe B ({shoe_b['brand']} {shoe_b['shoe_name']}):\n"
        prompt += f"{format_shoe_specs(shoe_b)}\n"
    
    return prompt


def get_gemini_batch_similarity_scores(model: Any, shoe_pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> List[float]:
    """Get similarity scores from Gemini API for a batch of shoe pairs."""
    
    prompt = create_batch_similarity_prompt(shoe_pairs)
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        
        # Parse the JSON response
        results = json.loads(response.text)
        
        # Extract scores in order
        scores = []
        for i in range(len(shoe_pairs)):
            # Find the result for this pair_id
            pair_result = next((r for r in results if r.get('pair_id') == i), None)
            if pair_result and 'similarity_score' in pair_result:
                score = float(pair_result['similarity_score'])
                scores.append(max(0, min(100, score)))  # Clamp to 0-100 range
            else:
                logger.warning(f"No score found for pair {i}")
                scores.append(0.0)
        
        return scores
        
    except Exception as e:
        logger.warning(f"Error getting Gemini batch scores: {e}")
        # Return zeros for all pairs on error
        return [0.0] * len(shoe_pairs)


def generate_synthetic_dataset(
    db_path: Path = DEFAULT_DB_PATH,
    output_path: Path = Path("data/synthetic_similarity_dataset.csv"),
    num_pairs: int = 50000,  # Increased from 10,000 to 50,000
    batch_size: int = 15,  # Optimal batch size for Gemini API
    max_retries: int = 3
) -> None:
    """Generate synthetic dataset of shoe similarity scores."""
    
    logger.info(f"Generating synthetic dataset with {num_pairs} shoe pairs")
    
    # Load shoes from database
    shoes_df = load_shoes_from_db(db_path)
    if len(shoes_df) < 2:
        raise ValueError("Need at least 2 shoes with lab data to generate pairs")
    
    # Initialize and fit clusterer
    clusterer = ShoeKMeansClusterer(random_state=42)
    clusterer.fit()
    
    # Merge cluster labels back to original shoes dataframe using shoe_id
    cluster_df = pd.DataFrame({
        'shoe_id': clusterer.shoe_frame['shoe_id'],
        'cluster_label': clusterer.labels_
    })
    
    # Merge to keep only shoes that have cluster labels
    shoes_df = shoes_df.merge(cluster_df, on='shoe_id', how='inner')
    
    # Get feature matrix for distance calculations
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    feature_matrix = shoes_df[DEFAULT_FEATURES].copy()
    imputed = imputer.fit_transform(feature_matrix)
    shoe_features = scaler.fit_transform(imputed)
    
    def calculate_euclidean_distance(shoe_a_idx: int, shoe_b_idx: int) -> float:
        """Calculate Euclidean distance between two shoes in feature space."""
        return np.linalg.norm(shoe_features[shoe_a_idx] - shoe_features[shoe_b_idx])
    
    # Initialize Gemini
    model = init_gemini()
    
    # Prepare output data
    dataset = []
    
    # Generate random pairs in batches
    for batch_start in range(0, num_pairs, batch_size):
        batch_end = min(batch_start + batch_size, num_pairs)
        batch_pairs = batch_end - batch_start
        
        logger.info(f"Processing batch {batch_start//batch_size + 1}: pairs {batch_start+1}-{batch_end}")
        
        # Prepare batch of shoe pairs
        shoe_pairs = []
        batch_entries = []
        
        for i in range(batch_pairs):
            # Sample two random shoes
            shoe_a_idx, shoe_b_idx = random.sample(range(len(shoes_df)), 2)
            shoe_a = shoes_df.iloc[shoe_a_idx]
            shoe_b = shoes_df.iloc[shoe_b_idx]
            
            # Parse lab test results to get terrain and support type
            lab_a = json.loads(shoe_a['lab_test_results']) if pd.notna(shoe_a['lab_test_results']) else {}
            lab_b = json.loads(shoe_b['lab_test_results']) if pd.notna(shoe_b['lab_test_results']) else {}
            
            # Prepare shoe data for prompt
            shoe_a_data = {
                'brand': shoe_a['brand'],
                'shoe_name': shoe_a['shoe_name'],
                **{feature: shoe_a[feature] for feature in DEFAULT_FEATURES if pd.notna(shoe_a[feature])},
                'Terrain': lab_a.get('Terrain'),
                'Arch Support': lab_a.get('Arch Support')
            }
            shoe_b_data = {
                'brand': shoe_b['brand'],
                'shoe_name': shoe_b['shoe_name'],
                **{feature: shoe_b[feature] for feature in DEFAULT_FEATURES if pd.notna(shoe_b[feature])},
                'Terrain': lab_b.get('Terrain'),
                'Arch Support': lab_b.get('Arch Support')
            }
            
            shoe_pairs.append((shoe_a_data, shoe_b_data))
            
            # Pre-calculate feature differences for storage
            feature_diffs = {}
            for feature in DEFAULT_FEATURES:
                val_a = shoe_a[feature] if pd.notna(shoe_a[feature]) else None
                val_b = shoe_b[feature] if pd.notna(shoe_b[feature]) else None
                
                if val_a is not None and val_b is not None:
                    # Use directional difference instead of absolute
                    feature_diffs[f'diff_{feature.lower().replace(" ", "_")}'] = val_b - val_a
                else:
                    feature_diffs[f'diff_{feature.lower().replace(" ", "_")}'] = None
            
            # Add categorical features
            feature_diffs['is_same_terrain'] = 1 if lab_a.get('Terrain') == lab_b.get('Terrain') else 0
            feature_diffs['is_same_support'] = 1 if lab_a.get('Arch Support') == lab_b.get('Arch Support') else 0
            
            # Add K-Means clustering features
            feature_diffs['is_same_kmeans_cluster'] = 1 if shoe_a['cluster_label'] == shoe_b['cluster_label'] else 0
            feature_diffs['euclidean_distance'] = calculate_euclidean_distance(shoe_a_idx, shoe_b_idx)
            
            # Store dataset entry (without score for now)
            entry = {
                'shoe_a_id': shoe_a['shoe_id'],
                'shoe_a_name': f"{shoe_a['brand']} {shoe_a['shoe_name']}",
                'shoe_b_id': shoe_b['shoe_id'],
                'shoe_b_name': f"{shoe_b['brand']} {shoe_b['shoe_name']}",
                'similarity_score': 0.0,  # Placeholder
                **feature_diffs
            }
            batch_entries.append(entry)
        
        # Get similarity scores for the entire batch
        similarity_scores = []
        for attempt in range(max_retries):
            similarity_scores = get_gemini_batch_similarity_scores(model, shoe_pairs)
            if any(score > 0 for score in similarity_scores):
                break
            if attempt < max_retries - 1:
                logger.warning(f"Batch failed, retrying... (attempt {attempt + 2})")
                time.sleep(2 ** attempt)  # Exponential backoff
        
        # Update entries with scores
        for i, score in enumerate(similarity_scores):
            batch_entries[i]['similarity_score'] = score
        
        # Add to dataset
        dataset.extend(batch_entries)
        
        if (batch_end) % 50 == 0:
            logger.info(f"Generated {batch_end}/{num_pairs} pairs")
        
        # Save batch progress
        if dataset:
            pd.DataFrame(dataset).to_csv(output_path, index=False)
            logger.info(f"Saved intermediate progress to {output_path}")
        
        # Rate limiting - sleep between batches
        if batch_end < num_pairs:
            sleep_time = 1.5
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
        num_pairs=50000,  # Increased to 50,000 for better training
        batch_size=15   # Optimal batch size for Gemini API
    )
