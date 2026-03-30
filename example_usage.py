"""Example usage of the ActivityDataProcessor for clustering analysis."""

from data_preprocessor import ActivityDataProcessor
from pathlib import Path

def example_usage():
    """Example of how to use the ActivityDataProcessor."""
    
    # Initialize the processor
    processor = ActivityDataProcessor()
    
    # Process your activity data
    input_csv = Path("your_activities.csv")  # Replace with your file
    output_csv = Path("processed_running_activities.csv")
    
    try:
        # Complete processing pipeline
        processed_data = processor.process(input_csv)
        
        # Save processed data
        processor.save_processed_data(processed_data, output_csv)
        
        # Get and print summary
        summary = processor.get_data_summary(processed_data)
        print("=== Processing Summary ===")
        print(f"✅ Processed {summary['total_activities']} running activities")
        print(f"📊 Extracted {len(summary['columns'])} features for clustering")
        
        if summary['date_range']:
            print(f"📅 Date range: {summary['date_range']['start']} to {summary['date_range']['end']}")
        
        print(f"💾 Saved to: {output_csv}")
        
        # Show first few rows
        print("\n=== Sample Data ===")
        print(processed_data.head())
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure your CSV file has the required columns.")

if __name__ == "__main__":
    example_usage()
