import os
import pandas as pd
import glob
import re
from datetime import datetime

# 配置源目录
SOURCE_DIRS = [
    r"f:\geroserverFabu\code\CSDS",
    r"f:\geroserverFabu\code\deepseek",
    r"f:\geroserverFabu\code\GLM",
    r"f:\geroserverFabu\code\QW"
]

# 输出文件路径
OUTPUT_FILE = r"f:\geroserverFabu\data_process\token_speed_summary.csv"
STATS_OUTPUT_FILE = r"f:\geroserverFabu\code\average_token_speed_stats.csv"

def get_base_name(filename):
    """
    解析文件名，去除末尾的序号或run+序号
    例如: 
    cherry_测试_run1.csv -> cherry_测试
    DS1.csv -> DS
    """
    base = os.path.splitext(filename)[0]
    # 去除末尾的数字
    base = re.sub(r'\d+$', '', base)
    # 去除末尾的 _run 或 run (如果前面还有)
    base = re.sub(r'(_?run)?$', '', base, flags=re.IGNORECASE)
    # 去除末尾可能的下划线
    base = base.rstrip('_')
    return base

def process_files():
    all_data = []
    
    print(f"开始处理 CSV 文件...")
    
    for folder in SOURCE_DIRS:
        if not os.path.exists(folder):
            print(f"警告: 目录不存在 {folder}")
            continue
            
        # 获取目录下所有 CSV 文件
        csv_files = glob.glob(os.path.join(folder, "*.csv"))
        
        for file_path in csv_files:
            try:
                # 读取 CSV
                df = pd.read_csv(file_path)
                
                # 标准化列名（处理不同文件的列名差异）
                # 主要是 Duration(s) 和 耗时(s)
                column_mapping = {
                    '耗时(s)': 'Duration(s)',
                    'Duration(s)': 'Duration(s)',
                    'Total Tokens': 'Total Tokens'
                }
                
                # 检查是否存在必要的列
                current_cols = df.columns.tolist()
                found_duration = None
                found_tokens = None
                
                for col in current_cols:
                    if col in column_mapping:
                        if column_mapping[col] == 'Duration(s)':
                            found_duration = col
                    if col == 'Total Tokens':
                        found_tokens = col
                
                if not found_duration or not found_tokens:
                    print(f"跳过文件 {os.path.basename(file_path)}: 缺少必要列 (Duration/耗时 或 Total Tokens)")
                    continue
                
                # 计算 Tokens/s
                # 确保数据是数值型
                df[found_duration] = pd.to_numeric(df[found_duration], errors='coerce')
                df[found_tokens] = pd.to_numeric(df[found_tokens], errors='coerce')
                
                # 避免除以零
                df['Tokens/s'] = df.apply(
                    lambda row: row[found_tokens] / row[found_duration] if row[found_duration] > 0 else 0, 
                    axis=1
                )
                
                # 添加来源信息
                folder_name = os.path.basename(folder)
                file_name = os.path.basename(file_path)
                df['Source Folder'] = folder_name
                df['Source File'] = file_name
                
                # 统一列名用于合并
                if found_duration != 'Duration(s)':
                    df.rename(columns={found_duration: 'Duration(s)'}, inplace=True)
                
                # 重新排列列，把重要信息放在前面
                cols = ['Source Folder', 'Source File', 'Duration(s)', 'Total Tokens', 'Tokens/s']
                # 添加其他原始列
                for c in df.columns:
                    if c not in cols:
                        cols.append(c)
                
                all_data.append(df[cols])
                print(f"已处理: {folder_name}\{file_name} - {len(df)} 行")
                
            except Exception as e:
                print(f"处理文件失败 {file_path}: {e}")

    if all_data:
        # 合并所有数据
        final_df = pd.concat(all_data, ignore_index=True)
        
        # 保存结果
        final_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"\n成功生成汇总文件: {OUTPUT_FILE}")
        print(f"总计处理行数: {len(final_df)}")
        
        # 打印简要统计
        print("\n=== 平均速度统计 (Tokens/s) ===")
        summary = final_df.groupby(['Source Folder', 'Source File'])['Tokens/s'].mean().reset_index()
        print(summary.to_string(index=False))
        
        # --- 新增逻辑：按同名不同序号文件进行分组统计 ---
        print("\n=== 分组平均统计 (合并多次运行) ===")
        
        # 提取基名 (Base Name)
        final_df['Base Name'] = final_df['Source File'].apply(get_base_name)
        
        # 按 Folder 和 Base Name 分组计算
        # 计算平均 Tokens/s (所有行速度的平均)
        grouped_stats = final_df.groupby(['Source Folder', 'Base Name']).agg({
            'Tokens/s': 'mean',
            'Source File': 'nunique',  # 统计包含的文件数量
            'Duration(s)': 'count'     # 统计总行数
        }).reset_index()
        
        grouped_stats.rename(columns={
            'Tokens/s': 'Average Tokens/s',
            'Source File': 'File Count',
            'Duration(s)': 'Total Rows'
        }, inplace=True)
        
        # 格式化保留2位小数
        grouped_stats['Average Tokens/s'] = grouped_stats['Average Tokens/s'].round(2)
        
        print(grouped_stats.to_string(index=False))
        
        # 保存统计结果
        grouped_stats.to_csv(STATS_OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"\n成功生成分组统计文件: {STATS_OUTPUT_FILE}")

        # 记录日志
        log_content = f"任务: 计算Token生成速度及分组统计\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n内容: 扫描了 {len(SOURCE_DIRS)} 个目录，生成了汇总文件 {OUTPUT_FILE} 和分组统计文件 {STATS_OUTPUT_FILE}。\n"
        log_file = r"f:\geroserverFabu\data_process\process_log.txt"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_content + "\n")
            
    else:
        print("未找到有效数据，未生成文件。")

if __name__ == "__main__":
    process_files()
