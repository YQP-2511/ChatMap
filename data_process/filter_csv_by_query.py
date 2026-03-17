import pandas as pd
import os
import argparse
import re

def load_reference_queries(file_path):
    queries = set()
    if not os.path.exists(file_path):
        print(f"Error: Reference file not found: {file_path}")
        return queries

    if file_path.lower().endswith('.csv'):
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='gbk')
        
        # Normalize columns
        df.columns = df.columns.str.strip().str.replace('﻿', '')
        
        # Find query column
        query_col = next((col for col in df.columns if col.lower() in ['query', 'question', '问题', 'input']), None)
        if query_col:
            queries = set(df[query_col].dropna().astype(str).str.strip())
        else:
            print(f"Warning: No query column found in {file_path}. Available columns: {df.columns.tolist()}")
            
    elif file_path.lower().endswith('.txt'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('L') or 'Questions:' in line:
                        continue
                    # Extract question text: remove leading "1. " and trailing "（...）"
                    # Regex: ^\d+\.\s*(.*?)(?:（|\(|$)
                    # Handle full-width '（' and half-width '('
                    match = re.match(r'^\d+\.\s*(.*?)(?:（|\(|$)', line)
                    if match:
                        query = match.group(1).strip()
                        if query:
                            queries.add(query)
        except UnicodeDecodeError:
            # Try GBK if UTF-8 fails
            with open(file_path, 'r', encoding='gbk') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('L') or 'Questions:' in line:
                        continue
                    match = re.match(r'^\d+\.\s*(.*?)(?:（|\(|$)', line)
                    if match:
                        query = match.group(1).strip()
                        if query:
                            queries.add(query)
    return queries

def filter_csv(source_file=None, reference_file=None):
    # Default paths
    base_dir = r"f:\geroserverFabu\csv"
    txt_dir = r"f:\geroserverFabu\txtquery"
    
    if not source_file:
        source_file = os.path.join(base_dir, "DIFYDS180.csv")
    
    if not reference_file:
        # Default to the txt file mentioned by user if not provided
        reference_file = os.path.join(txt_dir, "问题集60.txt")
        if not os.path.exists(reference_file):
             # Fallback to old default if txt doesn't exist
             reference_file = os.path.join(base_dir, "DIFYQW60.csv")

    output_file = source_file.replace(".csv", "_filtered.csv")

    print(f"Loading source file: {source_file}")
    if not os.path.exists(source_file):
        print(f"Error: Source file not found: {source_file}")
        return

    try:
        # Try reading with utf-8-sig to handle potential BOM
        df_source = pd.read_csv(source_file, encoding='utf-8-sig')
    except UnicodeDecodeError:
        print("UTF-8 decode failed, trying GBK...")
        df_source = pd.read_csv(source_file, encoding='gbk')

    # Normalize column names (strip whitespace and BOM)
    df_source.columns = df_source.columns.str.strip().str.replace('﻿', '')
    
    # Identify query column (supporting multiple variations)
    # Check for 'query', 'QUERY', 'question', '问题', 'input'
    target_cols = ['query', 'question', '问题', 'input']
    query_col_source = next((col for col in df_source.columns if col.lower() in target_cols), None)
    
    if not query_col_source:
        print(f"Error: Query column not found in {source_file}. Available columns: {df_source.columns.tolist()}")
        return
    
    print(f"Using column '{query_col_source}' from source.")

    print(f"Loading reference file: {reference_file}")
    queries_to_keep = load_reference_queries(reference_file)
    
    print(f"Found {len(queries_to_keep)} unique queries in reference file.")

    if not queries_to_keep:
        print("Warning: No queries found in reference file. No filtering will be applied.")
        return

    # Filter source dataframe
    # Also normalize source queries for comparison
    mask = df_source[query_col_source].astype(str).str.strip().isin(queries_to_keep)
    df_filtered = df_source[mask]

    print(f"Filtered rows: {len(df_filtered)} (Original: {len(df_source)})")

    # Save to new CSV
    print(f"Saving to {output_file}...")
    df_filtered.to_csv(output_file, index=False, encoding='utf-8-sig')
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter CSV by queries from another file.")
    parser.add_argument("source_file", nargs='?', help="Source CSV file path")
    parser.add_argument("reference_file", nargs='?', help="Reference file path (CSV or TXT)")
    args = parser.parse_args()
    
    filter_csv(args.source_file, args.reference_file)
