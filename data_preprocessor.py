"""Data preprocessing utility for activity clustering analysis.

This module processes activity CSV files to extract running-specific data
suitable for clustering algorithms.
"""

import pandas as pd
from pathlib import Path
from typing import Optional, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ActivityDataProcessor:
    """Process activity CSV data for clustering analysis."""
    
    # Required columns for clustering analysis
    REQUIRED_COLUMNS = [
        'Activity ID',
        'Activity Date', 
        'Activity Type',
        'Activity Gear',
        'Distance',
        'Moving Time',
        'Average Speed',
        'Average Grade Adjusted Pace',
        'Elevation Gain',
        'Average Cadence',
        'Average Heart Rate',
        'Training Load',
        'Relative Effort',
        'Perceived Exertion',
        'Weather Temperature'
    ]
    
    def __init__(self):
        self.data: Optional[pd.DataFrame] = None
        self.processed_data: Optional[pd.DataFrame] = None
    
    def load_csv(self, csv_path: Path) -> pd.DataFrame:
        """Load activity data from CSV file."""
        try:
            self.data = pd.read_csv(csv_path)
            logger.info(f"Loaded {len(self.data)} activities from {csv_path}")
            return self.data
        except Exception as e:
            logger.error(f"Failed to load CSV: {e}")
            raise
    
    def filter_running_activities(self) -> pd.DataFrame:
        """Filter activities to only include runs."""
        if self.data is None:
            raise ValueError("No data loaded. Call load_csv() first.")
        
        original_count = len(self.data)
        
        # Filter for running activities only
        running_data = self.data[self.data['Activity Type'] == 'Run'].copy()
        
        logger.info(f"Filtered {original_count} activities to {len(running_data)} running activities")
        
        self.processed_data = running_data
        return running_data
    
    def extract_required_columns(self) -> pd.DataFrame:
        """Extract only the columns needed for clustering analysis."""
        if self.processed_data is None:
            raise ValueError("No processed data. Call filter_running_activities() first.")
        
        # Check which required columns are available
        available_columns = []
        missing_columns = []
        
        for col in self.REQUIRED_COLUMNS:
            if col in self.processed_data.columns:
                available_columns.append(col)
            else:
                missing_columns.append(col)
        
        if missing_columns:
            logger.warning(f"Missing columns in data: {missing_columns}")
        
        # Extract available columns
        extracted_data = self.processed_data[available_columns].copy()
        
        logger.info(f"Extracted {len(available_columns)} columns for analysis")
        return extracted_data
    
    def clean_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Clean and preprocess the data for clustering."""
        logger.info("Cleaning data...")
        
        # Make a copy to avoid SettingWithCopyWarning
        cleaned_data = data.copy()
        
        # Convert Activity Date to datetime if it exists
        if 'Activity Date' in cleaned_data.columns:
            cleaned_data['Activity Date'] = pd.to_datetime(cleaned_data['Activity Date'], errors='coerce')
        
        # Convert numeric columns, handling errors
        numeric_columns = [
            'Distance', 'Moving Time', 'Average Speed', 'Average Grade Adjusted Pace',
            'Elevation Gain', 'Average Cadence', 'Average Heart Rate', 'Training Load',
            'Relative Effort', 'Perceived Exertion', 'Weather Temperature'
        ]
        
        for col in numeric_columns:
            if col in cleaned_data.columns:
                cleaned_data[col] = pd.to_numeric(cleaned_data[col], errors='coerce')
        
        # Log data quality
        total_activities = len(cleaned_data)
        
        # Count missing values per column
        missing_counts = cleaned_data.isnull().sum()
        logger.info("Missing values per column:")
        for col, count in missing_counts.items():
            if count > 0:
                percentage = (count / total_activities) * 100
                logger.info(f"  {col}: {count} ({percentage:.1f}%)")
        
        return cleaned_data
    
    def process(self, csv_path: Path) -> pd.DataFrame:
        """Complete processing pipeline: load, filter, extract, clean."""
        logger.info(f"Processing activity data from {csv_path}")
        
        # Load data
        self.load_csv(csv_path)
        
        # Filter to running activities
        self.filter_running_activities()
        
        # Extract required columns
        extracted_data = self.extract_required_columns()
        
        # Clean data
        cleaned_data = self.clean_data(extracted_data)
        
        logger.info(f"Final dataset: {len(cleaned_data)} running activities with {len(cleaned_data.columns)} features")
        
        return cleaned_data
    
    def save_processed_data(self, data: pd.DataFrame, output_path: Path) -> None:
        """Save processed data to CSV."""
        try:
            data.to_csv(output_path, index=False)
            logger.info(f"Saved processed data to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save data: {e}")
            raise
    
    def get_data_summary(self, data: pd.DataFrame) -> dict:
        """Get summary statistics of the processed data."""
        summary = {
            'total_activities': len(data),
            'columns': list(data.columns),
            'date_range': None,
            'numeric_summary': {}
        }
        
        # Date range if Activity Date exists
        if 'Activity Date' in data.columns:
            dates = pd.to_datetime(data['Activity Date'], errors='coerce')
            valid_dates = dates.dropna()
            if len(valid_dates) > 0:
                summary['date_range'] = {
                    'start': valid_dates.min().strftime('%Y-%m-%d'),
                    'end': valid_dates.max().strftime('%Y-%m-%d')
                }
        
        # Numeric summary
        numeric_cols = data.select_dtypes(include=['number']).columns
        for col in numeric_cols:
            series = data[col].dropna()
            if len(series) > 0:
                summary['numeric_summary'][col] = {
                    'mean': float(series.mean()),
                    'std': float(series.std()),
                    'min': float(series.min()),
                    'max': float(series.max()),
                    'count': int(series.count())
                }
        
        return summary


def main():
    """Example usage of the ActivityDataProcessor."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Process activity data for clustering")
    parser.add_argument("input_csv", type=Path, help="Input CSV file with activity data")
    parser.add_argument("output_csv", type=Path, help="Output CSV file for processed data")
    parser.add_argument("--summary", action="store_true", help="Print data summary")
    
    args = parser.parse_args()
    
    # Initialize processor
    processor = ActivityDataProcessor()
    
    try:
        # Process data
        processed_data = processor.process(args.input_csv)
        
        # Save processed data
        processor.save_processed_data(processed_data, args.output_csv)
        
        # Print summary if requested
        if args.summary:
            summary = processor.get_data_summary(processed_data)
            print("\n=== Data Summary ===")
            print(f"Total activities: {summary['total_activities']}")
            print(f"Columns: {', '.join(summary['columns'])}")
            
            if summary['date_range']:
                print(f"Date range: {summary['date_range']['start']} to {summary['date_range']['end']}")
            
            print("\nNumeric Features:")
            for col, stats in summary['numeric_summary'].items():
                print(f"  {col}: mean={stats['mean']:.2f}, std={stats['std']:.2f}, "
                      f"range=[{stats['min']:.2f}, {stats['max']:.2f}] (n={stats['count']})")
        
        print(f"\n✅ Processing complete! Output saved to {args.output_csv}")
        
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise


if __name__ == "__main__":
    main()
