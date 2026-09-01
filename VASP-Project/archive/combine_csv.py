import pandas as pd
import glob
import json

# Path to all CSV files
csv_files = glob.glob('data/*.csv')

# List to hold DataFrames
dfs = []

for file in csv_files:
    # Read each line as JSON
    with open(file, 'r') as f:
        data = [json.loads(line) for line in f]
    
    df = pd.DataFrame(data)
    dfs.append(df)

# Combine all DataFrames
combined_df = pd.concat(dfs, ignore_index=True)

# Save to a single CSV
combined_df.to_csv('data/combined_sensors.csv', index=False)

print("✅ Combined CSV saved as data/combined_sensors.csv")
