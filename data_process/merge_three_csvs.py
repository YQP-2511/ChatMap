import pandas as pd
import os
import datetime
import sys

def get_current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def scan_csv_files(directory):
    """扫描目录下所有CSV文件 (不包含子目录)"""
    csv_files = []
    # 仅扫描当前目录，不递归
    if not os.path.exists(directory):
        print(f"目录不存在: {directory}")
        return []
        
    for file in os.listdir(directory):
        if file.lower().endswith('.csv'):
            full_path = os.path.join(directory, file)
            if os.path.isfile(full_path):
                csv_files.append({
                    'path': full_path,
                    'display': file
                })
    return sorted(csv_files, key=lambda x: x['display'])

def select_files(file_list, prompt_text, count=3):
    """交互式文件选择，指定选择数量"""
    print("\n" + "="*50)
    print(f"可用文件列表:")
    for i, file in enumerate(file_list):
        print(f"[{i+1}] {file['display']}")
    print("="*50)
    
    while True:
        print(f"\n{prompt_text}")
        print(f"(请输入 {count} 个文件的序号，用空格分隔，顺序对应 _1, _2, _3)")
            
        choice = input("请输入: ").strip()
        
        if choice.lower() == 'q':
            sys.exit(0)
            
        try:
            indices = [int(x) - 1 for x in choice.split()]
            if len(indices) != count:
                print(f"请恰好选择 {count} 个文件")
                continue

            selected = []
            valid = True
            for idx in indices:
                if 0 <= idx < len(file_list):
                    selected.append(file_list[idx]['path'])
                else:
                    print(f"警告: 序号 {idx+1} 无效")
                    valid = False
            
            if valid:
                return selected
                
        except ValueError:
            print("输入格式错误，请输入数字序号")

def get_csv_headers(file_path):
    """读取CSV文件头"""
    try:
        try:
            df = pd.read_csv(file_path, encoding='utf-8', nrows=0)
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='gbk', nrows=0)
        return [c.strip() for c in df.columns]
    except Exception as e:
        print(f"读取文件头失败 {file_path}: {e}")
        return []

def select_key_column(headers_list, file_paths):
    """
    让用户选择 Key 字段
    逻辑：先让用户从第一个文件选择 Key，然后尝试在其他文件中自动匹配
    """
    print("\n" + "-"*30)
    print("步骤 1: 选择合并的主键字段 (Key Column)")
    print(f"基准文件 (File 1): {os.path.basename(file_paths[0])}")
    print("可用字段:")
    
    headers_1 = headers_list[0]
    for i, h in enumerate(headers_1):
        print(f"[{i+1}] {h}")
        
    while True:
        choice = input(f"请输入基准文件的 Key 字段序号 (或直接输入字段名): ").strip()
        key_1 = ""
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(headers_1):
                key_1 = headers_1[idx]
        else:
            # 允许用户输入字段名（模糊匹配）
            matches = [h for h in headers_1 if h.lower() == choice.lower()]
            if matches:
                key_1 = matches[0]
        
        if key_1:
            print(f"已选择基准 Key: {key_1}")
            break
        print("无效的选择，请重试")

    # 自动匹配其他文件
    keys = [key_1]
    print("\n正在匹配其他文件的 Key 字段...")
    
    # 定义常见 Key 别名
    aliases = {
        'query': ['question', 'input', '问题'], 
        'question': ['query', 'input', '问题'],
        '问题': ['query', 'question', 'input']
    }

    for i in range(1, len(file_paths)):
        fname = os.path.basename(file_paths[i])
        headers = headers_list[i]
        
        # 1. 精确匹配
        if key_1 in headers:
            print(f"File {i+1} ({fname}): 自动匹配到 '{key_1}'")
            keys.append(key_1)
            continue
            
        # 2. 忽略大小写匹配
        matches = [h for h in headers if h.lower() == key_1.lower()]
        if matches:
            print(f"File {i+1} ({fname}): 自动匹配到 '{matches[0]}' (忽略大小写)")
            keys.append(matches[0])
            continue
            
        # 3. 常见别名匹配
        found_alias = False
        if key_1.lower() in aliases:
            for alias in aliases[key_1.lower()]:
                matches = [h for h in headers if h.lower() == alias]
                if matches:
                    print(f"File {i+1} ({fname}): 自动匹配到别名 '{matches[0]}'")
                    keys.append(matches[0])
                    found_alias = True
                    break
        if found_alias:
            continue
            
        # 4. 手动选择
        print(f"警告: 在 File {i+1} ({fname}) 中未找到 '{key_1}' 或常见别名")
        print("可用字段:")
        for idx, h in enumerate(headers):
            print(f"[{idx+1}] {h}")
            
        while True:
            sel = input(f"请为 {fname} 选择 Key 字段序号: ").strip()
            if sel.isdigit() and 0 <= int(sel)-1 < len(headers):
                selected_key = headers[int(sel)-1]
                keys.append(selected_key)
                break
            print("无效输入")
            
    return keys

def select_value_columns(headers_list, file_paths, keys):
    """
    让用户选择要合并的 Value 字段
    """
    print("\n" + "-"*30)
    print("步骤 2: 选择需要合并的数据字段 (Value Columns)")
    print(f"基准文件 (File 1): {os.path.basename(file_paths[0])}")
    
    # 排除 Key 字段
    headers_1 = headers_list[0]
    available_cols = [h for h in headers_1 if h != keys[0]]
    
    print("可用字段:")
    for i, h in enumerate(available_cols):
        print(f"[{i+1}] {h}")
        
    selected_cols_1 = []
    while True:
        choice = input("请输入要合并的字段序号 (多选空格分隔, all全选): ").strip()
        if choice.lower() == 'all':
            selected_cols_1 = available_cols
            break
            
        try:
            indices = [int(x)-1 for x in choice.split()]
            valid = True
            temp_list = []
            for idx in indices:
                if 0 <= idx < len(available_cols):
                    temp_list.append(available_cols[idx])
                else:
                    valid = False
            if valid and temp_list:
                selected_cols_1 = temp_list
                break
        except:
            pass
        print("输入无效，请重试")
        
    print(f"已选择基准字段: {selected_cols_1}")
    
    # 映射到所有文件
    # 结构: [[col1_file1, col2_file1], [col1_file2, col2_file2], ...]
    all_selected_cols = [selected_cols_1]
    
    # 定义字段别名映射 (normalized key -> list of aliases)
    # 注意：这里的 key 应该是 normalized 后的形式，或者我们在比较时处理
    column_aliases = {
        '耗时(s)': ['duration', 'duration_seconds', '耗时', 'time', 'latency'],
        'total tokens': ['tokens', 'token usage', 'token_usage', 'total_tokens'],
        '工具链': ['tool', 'tools', 'tool_chain', 'tool calls', 'tool_calls'],
        '图层': ['layer', 'layers'],
        'url': ['link', 'result_link'],
        '是否成功': ['success', 'is_success', 'status']
    }
    
    def normalize(s):
        return s.lower().replace(' ', '').replace('_', '').replace('(', '').replace(')', '')

    for i in range(1, len(file_paths)):
        fname = os.path.basename(file_paths[i])
        headers = headers_list[i]
        current_file_cols = []
        
        print(f"\n正在为 File {i+1} ({fname}) 映射字段...")
        
        for col_1 in selected_cols_1:
            # 1. 精确匹配
            if col_1 in headers:
                current_file_cols.append(col_1)
                continue
                
            # 2. 忽略大小写
            matches = [h for h in headers if h.lower() == col_1.lower()]
            if matches:
                print(f"  '{col_1}' -> 匹配到 '{matches[0]}'")
                current_file_cols.append(matches[0])
                continue
                
            # 3. 常见别名匹配
            norm_col_1 = normalize(col_1)
            found_alias = False
            
            # 3.1 检查预定义别名
            # 检查 col_1 是否匹配 alias map 中的任何 key (或其 aliases)
            for main_key, aliases in column_aliases.items():
                # 检查 col_1 是否是 main_key 或者在 aliases 中
                if col_1 == main_key or col_1 in aliases or normalize(col_1) == normalize(main_key):
                    # 如果 col_1 属于这个组，则在 headers 中寻找匹配该组任何 alias 的列
                    potential_names = [main_key] + aliases
                    for alias in potential_names:
                        matches = [h for h in headers if normalize(h) == normalize(alias)]
                        if matches:
                            print(f"  '{col_1}' -> 别名匹配到 '{matches[0]}'")
                            current_file_cols.append(matches[0])
                            found_alias = True
                            break
                    if found_alias: break
            
            if found_alias:
                continue

            # 3.2 简单模糊匹配 (如果没在预定义别名中找到)
            matches = [h for h in headers if normalize(h) == norm_col_1]
            if matches:
                print(f"  '{col_1}' -> 模糊匹配到 '{matches[0]}'")
                current_file_cols.append(matches[0])
                continue
            
            # 4. 手动选择
            print(f"  警告: 无法自动匹配 '{col_1}'")
            print("  可用字段:")
            for idx, h in enumerate(headers):
                print(f"  [{idx+1}] {h}")
            
            while True:
                sel = input(f"  请为 '{col_1}' 选择对应字段 (输入 0 跳过): ").strip()
                if sel == '0':
                    current_file_cols.append(None) # None 表示跳过该列
                    print("  已跳过")
                    break
                if sel.isdigit() and 0 <= int(sel)-1 < len(headers):
                    current_file_cols.append(headers[int(sel)-1])
                    break
                print("  无效输入")
                
        all_selected_cols.append(current_file_cols)
        
    return all_selected_cols

def load_and_process_csv_v2(file_path, key_col, value_cols, suffix_index, target_key_name='query'):
    """
    根据指定的 key 和 value 列读取并处理 CSV
    """
    print(f"[{get_current_time()}] 读取文件: {file_path}")
    try:
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='gbk')
            
        df.columns = [c.strip() for c in df.columns]
        
        # 准备重命名映射
        rename_dict = {key_col: target_key_name}
        keep_cols = [key_col]
        
        for i, val_col in enumerate(value_cols):
            if val_col is not None: # 如果不是跳过的列
                keep_cols.append(val_col)

        # 检查列是否存在
        missing = [c for c in keep_cols if c not in df.columns]
        if missing:
            print(f"错误: 文件缺少字段 {missing}")
            return None
            
        df_subset = df[keep_cols].copy()
        
        # 应用重命名
        df_subset.rename(columns={key_col: target_key_name}, inplace=True)
        
        # 统一 Key 格式
        df_subset[target_key_name] = df_subset[target_key_name].astype(str).str.strip()
        
        return df_subset
        
    except Exception as e:
        print(f"处理文件失败 {file_path}: {e}")
        return None

def main():
    base_dir = r"f:\geroserverFabu\csv"
    output_dir = r"f:\geroserverFabu\csv\merged_results"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    print(f"[{get_current_time()}] 开始执行交互式 CSV 合并脚本 (优化版)")
    
    # 1. 选择文件
    all_files = scan_csv_files(base_dir)
    if len(all_files) < 3:
        print("错误: 目录下 CSV 文件少于 3 个")
        return
        
    selected_files = select_files(all_files, "请选择 3 个要合并的 CSV 文件")
    
    # 2. 读取所有表头
    headers_list = [get_csv_headers(f) for f in selected_files]
    if any(len(h) == 0 for h in headers_list):
        print("读取表头失败，程序退出")
        return

    # 3. 交互式映射
    # keys: [key_file1, key_file2, key_file3]
    keys = select_key_column(headers_list, selected_files)
    
    # value_cols_list: [[v1_f1, v2_f1], [v1_f2, v2_f2], ...]
    value_cols_list = select_value_columns(headers_list, selected_files, keys)
    
    # 获取基准 Value 列名，用于生成最终列名
    base_value_names = value_cols_list[0] 
    
    # 4. 读取数据并重命名
    dfs = []
    # 使用用户在第一个文件选择的 Key 作为最终合并 Key 的名称，而不是硬编码 'query'
    target_key = keys[0] 
    print(f"合并基准键: {target_key}")
    
    for i, file_path in enumerate(selected_files):
        current_key = keys[i]
        current_vals = value_cols_list[i]
        
        # 构造重命名逻辑: current_val -> base_name_suffix
        # 我们需要在 load 之后 rename
        
        df = load_and_process_csv_v2(file_path, current_key, current_vals, i+1, target_key)
        
        if df is not None:
            # 执行 Value 列的重命名
            rename_map = {}
            for j, val_col in enumerate(current_vals):
                if val_col is not None:
                    base_name = base_value_names[j]
                    rename_map[val_col] = f"{base_name}_{i+1}"
            
            df.rename(columns=rename_map, inplace=True)
            dfs.append(df)
        else:
            return

    # 5. 合并
    print(f"\n[{get_current_time()}] 正在合并数据...")
    merged_df = dfs[0]
    for i in range(1, len(dfs)):
        merged_df = pd.merge(merged_df, dfs[i], on=target_key, how='outer')
        
    # 6. 保存
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"merged_3files_opt_{timestamp}.csv"
    output_path = os.path.join(output_dir, output_filename)
    
    try:
        merged_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"[{get_current_time()}] 合并完成！")
        print(f"输出文件: {output_path}")
        print(f"总行数: {len(merged_df)}")
    except Exception as e:
        print(f"保存失败: {e}")

if __name__ == "__main__":
    main()
