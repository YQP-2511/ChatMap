import os
import pandas as pd
from pathlib import Path

def compare_folders(dir1, dir2, ignore_columns=None):
    if ignore_columns is None:
        ignore_columns = []
    
    dir1_path = Path(dir1)
    dir2_path = Path(dir2)
    
    # Get all CSV files in dir1 recursively
    files1 = [f.relative_to(dir1_path) for f in dir1_path.rglob('*.csv')]
    files2 = [f.relative_to(dir2_path) for f in dir2_path.rglob('*.csv')]
    
    common_files = set(files1) & set(files2)
    only_in_1 = set(files1) - set(files2)
    only_in_2 = set(files2) - set(files1)
    
    print(f"对比文件夹: {dir1} vs {dir2}")
    print(f"忽略列: {ignore_columns}\n")
    
    if only_in_1:
        print("只在文件夹 1 中存在的文件:")
        for f in only_in_1:
            print(f"  - {f}")
    
    if only_in_2:
        print("只在文件夹 2 中存在的文件:")
        for f in only_in_2:
            print(f"  - {f}")
            
    print("\n开始对比共有文件:")
    
    for file_rel_path in sorted(list(common_files)):
        file1 = dir1_path / file_rel_path
        file2 = dir2_path / file_rel_path
        
        try:
            # Try reading with utf-8 first, then gbk if fails
            try:
                df1 = pd.read_csv(file1, encoding='utf-8')
            except UnicodeDecodeError:
                df1 = pd.read_csv(file1, encoding='gbk')
                
            try:
                df2 = pd.read_csv(file2, encoding='utf-8')
            except UnicodeDecodeError:
                df2 = pd.read_csv(file2, encoding='gbk')
            
            # Drop ignored columns if they exist
            cols_to_drop = [c for c in ignore_columns if c in df1.columns]
            if cols_to_drop:
                df1 = df1.drop(columns=cols_to_drop)
            
            cols_to_drop2 = [c for c in ignore_columns if c in df2.columns]
            if cols_to_drop2:
                df2 = df2.drop(columns=cols_to_drop2)
                
            # Compare
            # Align columns just in case order is different but content is same? 
            # Usually for row-by-row comparison, we assume schema matches.
            # But let's check columns first
            
            if list(df1.columns) != list(df2.columns):
                # If columns are just reordered, sort them
                if set(df1.columns) == set(df2.columns):
                    df1 = df1[sorted(df1.columns)]
                    df2 = df2[sorted(df2.columns)]
                else:
                    print(f"[差异] {file_rel_path}: 列名不匹配")
                    print(f"  Dir1 Columns: {list(df1.columns)}")
                    print(f"  Dir2 Columns: {list(df2.columns)}")
                    continue
            
            # Compare shape
            if df1.shape != df2.shape:
                print(f"[差异] {file_rel_path}: 行数或列数不同 ({df1.shape} vs {df2.shape})")
                continue
                
            # Compare content
            # Using pandas equals
            if df1.equals(df2):
                print(f"[相同] {file_rel_path}")
            else:
                # Find first difference for detail
                diff_mask = (df1 != df2) & ~(df1.isnull() & df2.isnull())
                # Check if any True in mask
                if diff_mask.any().any():
                    print(f"[差异] {file_rel_path}: 内容不一致")
                    # Optional: Print first few diffs
                    # diff_rows = diff_mask.any(axis=1)
                    # print(df1[diff_rows].head()) 
                else:
                    print(f"[相同] {file_rel_path} (NaN处理后相同)")

        except Exception as e:
            print(f"[错误] {file_rel_path}: {e}")

if __name__ == "__main__":
    folder1 = r"f:\geroserverFabu\csv"
    folder2 = r"f:\geroserverFabu\csvcopy"
    ignore = ["是否成功", "备注"]
    
    compare_folders(folder1, folder2, ignore)
