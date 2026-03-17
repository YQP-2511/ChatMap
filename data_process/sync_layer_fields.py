import pandas as pd
import os
import datetime
import sys

def get_current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_source_data(source_path):
    """
    加载源文件，返回 layer 到 (是否成功, 备注) 的映射字典
    """
    print(f"[{get_current_time()}] 正在加载源文件: {source_path}")
    try:
        # 尝试使用 utf-8 读取，如果失败尝试 gbk
        try:
            df = pd.read_csv(source_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(source_path, encoding='gbk')
        
        # 统一列名处理（去除空格，处理大小写）
        df.columns = [c.strip() for c in df.columns]
        
        # 查找 layer 列 (支持 LAYER, Layer, layer)
        layer_col = next((c for c in df.columns if c.lower() == 'layer'), None)
        success_col = next((c for c in df.columns if c == '是否成功'), None)
        remark_col = next((c for c in df.columns if c == '备注'), None)
        
        if not layer_col:
            print(f"[{get_current_time()}] 错误: 源文件中未找到 layer 字段")
            return None
        
        if not success_col or not remark_col:
            print(f"[{get_current_time()}] 警告: 源文件中缺少 '是否成功' 或 '备注' 字段")
        
        # 构建映射字典 {layer_value: {'是否成功': val, '备注': val}}
        # 过滤掉 layer 为空的行
        mapping = {}
        count = 0
        for index, row in df.iterrows():
            layer_val = row[layer_col]
            if pd.isna(layer_val) or str(layer_val).strip() == '':
                continue
            
            # 清理 layer 值，去除前后空格
            layer_val = str(layer_val).strip()
            
            data = {}
            if success_col:
                data['是否成功'] = row[success_col]
            if remark_col:
                data['备注'] = row[remark_col]
            
            mapping[layer_val] = data
            count += 1
            
        print(f"[{get_current_time()}] 已加载 {count} 条映射规则")
        return mapping
        
    except Exception as e:
        print(f"[{get_current_time()}] 读取源文件失败: {e}")
        return None

def process_target_file(file_path, mapping):
    """
    处理目标文件，根据 mapping 更新字段
    """
    print(f"[{get_current_time()}] 正在处理文件: {file_path}")
    try:
        # 尝试读取
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            encoding = 'utf-8'
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='gbk')
            encoding = 'gbk'
            
        original_columns = list(df.columns)
        clean_columns = [c.strip() for c in df.columns]
        df.columns = clean_columns
        
        # 查找 layer 列
        layer_col = next((c for c in df.columns if c.lower() == 'layer'), None)
        if not layer_col:
            print(f"[{get_current_time()}] 跳过: 文件中无 layer 字段")
            return
            
        # 确保目标列存在
        if '是否成功' not in df.columns:
            df['是否成功'] = None
        if '备注' not in df.columns:
            df['备注'] = None
            
        updated_count = 0
        
        # 更新数据
        for index, row in df.iterrows():
            layer_val = row[layer_col]
            if pd.isna(layer_val) or str(layer_val).strip() == '':
                continue
                
            layer_val = str(layer_val).strip()
            
            if layer_val in mapping:
                source_data = mapping[layer_val]
                
                # 更新 是否成功
                if '是否成功' in source_data and pd.notna(source_data['是否成功']):
                    df.at[index, '是否成功'] = source_data['是否成功']
                    
                # 更新 备注
                if '备注' in source_data and pd.notna(source_data['备注']):
                    df.at[index, '备注'] = source_data['备注']
                    
                updated_count += 1
                
        if updated_count > 0:
            print(f"[{get_current_time()}] 更新了 {updated_count} 条记录")
            # 保存文件，保持原编码
            df.to_csv(file_path, index=False, encoding=encoding)
            print(f"[{get_current_time()}] 文件已保存")
        else:
            print(f"[{get_current_time()}] 无需更新")
            
    except Exception as e:
        print(f"[{get_current_time()}] 处理文件失败: {e}")

def scan_csv_files(directory):
    """扫描目录下所有CSV文件"""
    csv_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.csv'):
                full_path = os.path.join(root, file)
                # 使用相对路径显示，更友好
                rel_path = os.path.relpath(full_path, directory)
                csv_files.append({
                    'path': full_path,
                    'display': rel_path
                })
    return sorted(csv_files, key=lambda x: x['display'])

def select_files(file_list, prompt_text, allow_multiple=True, allow_all=False):
    """交互式文件选择"""
    print("\n" + "="*50)
    print(f"可用文件列表:")
    for i, file in enumerate(file_list):
        print(f"[{i+1}] {file['display']}")
    print("="*50)
    
    while True:
        print(f"\n{prompt_text}")
        if allow_all:
            print("(输入 'all' 选择所有文件，输入 'q' 退出)")
        else:
            print("(输入序号，多个用空格分隔，输入 'q' 退出)")
            
        choice = input("请输入: ").strip()
        
        if choice.lower() == 'q':
            sys.exit(0)
            
        if allow_all and choice.lower() == 'all':
            return [f['path'] for f in file_list]
            
        if not choice:
            continue
            
        try:
            indices = [int(x) - 1 for x in choice.split()]
            selected = []
            for idx in indices:
                if 0 <= idx < len(file_list):
                    selected.append(file_list[idx]['path'])
                else:
                    print(f"警告: 序号 {idx+1} 无效，已忽略")
            
            if not selected:
                print("未选择有效文件，请重试")
                continue
                
            if not allow_multiple and len(selected) > 1:
                print("仅允许选择一个文件")
                continue
                
            return selected
        except ValueError:
            print("输入格式错误，请输入数字序号")

def main():
    target_dir = r"f:\geroserverFabu\csv"
    
    print(f"[{get_current_time()}] 开始执行交互式同步脚本")
    
    # 1. 扫描所有CSV文件
    all_csv_files = scan_csv_files(target_dir)
    if not all_csv_files:
        print("未在目录中找到CSV文件")
        return

    # 2. 选择参照文件
    print("\n步骤 1/2: 选择参照文件 (Reference Files)")
    print("注意：请按 **优先级从高到低** 的顺序选择")
    print("例如：输入 '1 2 3' 表示文件[1]优先级最高，[2]次之，[3]最低")
    
    source_csvs = select_files(all_csv_files, "请选择参照文件序号 (优先级高 -> 低):")
    
    # 转换为加载顺序：优先级低的先加载，优先级高的后加载（覆盖）
    # 用户输入: High -> Low
    # 加载顺序: Low -> High
    load_order_sources = source_csvs[::-1]
    
    print(f"\n已选择参照文件 (按加载覆盖顺序显示):")
    for p in load_order_sources:
        print(f"- {os.path.basename(p)}")

    # 3. 选择目标文件
    print("\n步骤 2/2: 选择需要更新的目标文件 (Target Files)")
    
    # 默认过滤掉参照文件，但允许用户重新选择
    remaining_files = [f for f in all_csv_files if f['path'] not in source_csvs]
    
    target_csvs = select_files(remaining_files, "请选择目标文件序号 (默认排除参照文件):", allow_all=True)
    
    print(f"\n准备开始同步...")
    print(f"参照源数量: {len(source_csvs)}")
    print(f"目标文件数量: {len(target_csvs)}")
    
    confirm = input("\n确认开始执行? (y/n): ").strip().lower()
    if confirm != 'y':
        print("操作已取消")
        return

    # 4. 执行同步逻辑
    final_mapping = {}
    
    # 加载源数据
    for source_csv in load_order_sources:
        if not os.path.exists(source_csv):
            print(f"[{get_current_time()}] 警告: 源文件不存在: {source_csv}")
            continue
            
        mapping = load_source_data(source_csv)
        if mapping:
            final_mapping.update(mapping)
            print(f"[{get_current_time()}] 已合并 {os.path.basename(source_csv)} 的映射数据，当前总规则数: {len(final_mapping)}")
    
    if not final_mapping:
        print(f"[{get_current_time()}] 错误: 未能加载任何有效映射数据，程序退出")
        return
        
    # 处理目标文件
    for file_path in target_csvs:
        process_target_file(file_path, final_mapping)
                
    print(f"[{get_current_time()}] 所有任务完成")

if __name__ == "__main__":
    main()
