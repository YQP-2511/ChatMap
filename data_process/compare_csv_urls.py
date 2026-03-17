import os
import csv
import sys

def get_csv_files(directory):
    """获取指定目录下的所有 CSV 文件"""
    try:
        files = [f for f in os.listdir(directory) if f.lower().endswith('.csv')]
        return files
    except FileNotFoundError:
        print(f"Error: Directory not found: {directory}")
        return []

def read_csv_to_dict(file_path):
    """读取 CSV 文件，返回 {query: url} 字典"""
    data = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'QUERY' in row and 'URL' in row:
                    query = row['QUERY'].strip()
                    url = row['URL'].strip()
                    # 假设 Query 是唯一的，如果有重复，后面的会覆盖前面的
                    data[query] = url
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None
    return data

def select_folder():
    """选择文件夹"""
    folders = [
        r"f:\geroserverFabu\csv\CSDS60",
        r"f:\geroserverFabu\csv\DIFYDS180",
        r"f:\geroserverFabu\csv\DIFYqw"
    ]
    
    print("\n请选择 CSV 文件夹:")
    for i, folder in enumerate(folders):
        print(f"{i + 1}. {folder}")
    
    while True:
        try:
            choice = input("\n请输入序号选择 (或输入 'q' 退出): ").strip()
            if choice.lower() == 'q':
                sys.exit()
            
            idx = int(choice) - 1
            if 0 <= idx < len(folders):
                selected_folder = folders[idx]
                if not os.path.exists(selected_folder):
                    print(f"警告: 文件夹不存在: {selected_folder}")
                    continue
                return selected_folder
            else:
                print("无效的选择，请重试。")
        except ValueError:
            print("请输入有效的数字。")

def select_files(folder):
    """在文件夹中选择至少两个文件"""
    files = get_csv_files(folder)
    if len(files) < 2:
        print("该文件夹下 CSV 文件不足两个，无法比较。")
        return []
        
    print(f"\n文件夹 '{folder}' 下的文件:")
    for i, f in enumerate(files):
        print(f"{i + 1}. {f}")
        
    while True:
        try:
            choice = input("\n请输入文件的序号 (用空格分隔，例如 '1 2' 或 '1 2 3')，至少选择两个，或 'q' 退出: ").strip()
            if choice.lower() == 'q':
                sys.exit()
                
            parts = choice.split()
            if len(parts) < 2:
                print("请至少输入两个序号。")
                continue
            
            selected_files = []
            valid_selection = True
            seen_indices = set()
            
            for part in parts:
                idx = int(part) - 1
                if 0 <= idx < len(files):
                    if idx in seen_indices:
                        print(f"警告: 序号 {part} 重复，已忽略。")
                    else:
                        selected_files.append(os.path.join(folder, files[idx]))
                        seen_indices.add(idx)
                else:
                    print(f"序号 {part} 超出范围。")
                    valid_selection = False
                    break
            
            if valid_selection and len(selected_files) >= 2:
                return selected_files
            elif valid_selection:
                print("有效文件选择不足两个，请重试。")
            else:
                print("请重新选择。")

        except ValueError:
            print("请输入有效的数字。")

def compare_multiple_csvs(file_paths):
    """比较多个 CSV 文件"""
    if not file_paths:
        return

    print(f"\n正在比较以下 {len(file_paths)} 个文件:")
    for i, fp in enumerate(file_paths):
        print(f"{i + 1}. {os.path.basename(fp)}")
    print("-" * 30)

    datasets = []
    for fp in file_paths:
        data = read_csv_to_dict(fp)
        if data is None:
            print(f"无法读取文件: {fp}，停止比较。")
            return
        datasets.append(data)

    # 找到所有文件共有的 Query
    if not datasets:
        return

    # 初始化为第一个数据集的 keys
    common_queries = set(datasets[0].keys())
    for data in datasets[1:]:
        common_queries &= set(data.keys())
    
    print(f"所有文件共有的 Query 数: {len(common_queries)}")
    
    match_count = 0
    mismatch_count = 0
    matching_queries = []
    
    for query in common_queries:
        # 以此 query 在第一个文件的 url 为基准
        base_url = datasets[0][query]
        is_match = True
        
        for data in datasets[1:]:
            if data[query] != base_url:
                is_match = False
                break
        
        if is_match:
            match_count += 1
            matching_queries.append(query)
        else:
            mismatch_count += 1
            
    if matching_queries:
        print(f"\n[URL 在所有文件中都相同的问题清单] (共 {len(matching_queries)} 个):")
        for q in matching_queries:
            print(f"  - {q}")
    else:
        print("\n没有 URL 在所有文件中都相同的问题。")
            
    print("-" * 30)
    print(f"\n比较结果总结:")
    print(f"参与比较文件数: {len(file_paths)}")
    print(f"URL 完全一致的 Query 数: {match_count}")
    print(f"URL 存在差异的 Query 数: {mismatch_count}")

def main():
    while True:
        folder = select_folder()
        files = select_files(folder)
        
        if files:
            compare_multiple_csvs(files)
        
        cont = input("\n是否继续比较其他文件? (y/n): ").strip().lower()
        if cont != 'y':
            break

if __name__ == "__main__":
    main()
