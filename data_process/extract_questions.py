import os
import random
import re
import sys

def extract_questions(file_path, output_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    # Initialize nested dictionary to store questions by level and sublevel
    # Structure: questions[major_level][minor_level] = []
    questions = {
        '1': {'01': [], '02': [], '03': []},
        '2': {'01': [], '02': [], '03': []},
        '3': {'01': [], '02': [], '03': []}
    }
    
    # Define sampling counts for each sublevel
    # 01->6, 02->6, 03->8
    sample_counts = {'01': 6, '02': 6, '03': 8}

    current_major = None
    current_minor = None
    
    print(f"Reading from: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Match headers like L101, L202, L303
        # Regex captures major level (digit 1) and minor level (digits 2-3)
        match = re.match(r'^L(\d)(\d{2})[：:]?', line)
        if match:
            current_major = match.group(1)
            current_minor = match.group(2)
            # print(f"Switched to level: L{current_major}{current_minor}")
            continue

        # Check if line is a question (starts with digit and dot)
        if current_major and current_minor and re.match(r'^\d+\.', line):
            if current_major in questions and current_minor in questions[current_major]:
                questions[current_major][current_minor].append(line)

    # Perform sampling and writing
    total_count = 0
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for major in ['1', '2', '3']:
                f.write(f"L{major} Questions:\n")
                
                # Collect all sampled questions for this major level to write them sequentially
                # but user requirement implies structure. 
                # "每个大级别20个". Let's write them continuously 1-20.
                
                level_samples = []
                
                # Iterate through sublevels 01, 02, 03
                for minor in ['01', '02', '03']:
                    qs = questions[major][minor]
                    count = sample_counts.get(minor, 0)
                    
                    # Sample logic
                    if len(qs) <= count:
                        sampled = qs # Take all if not enough
                    else:
                        # random.sample returns random order, but we want to keep original file order
                        # Solution: Sample indices, sort them, then pick elements
                        indices = random.sample(range(len(qs)), count)
                        indices.sort()
                        sampled = [qs[i] for i in indices]
                    
                    level_samples.extend(sampled)
                    print(f"L{major}{minor}: Found {len(qs)}, Sampled {len(sampled)}")

                # Write to file
                for idx, q in enumerate(level_samples, 1):
                    # Clean the original number (e.g. "1. xxx" -> "xxx")
                    clean_q = re.sub(r'^\d+\.\s*', '', q)
                    f.write(f"{idx}. {clean_q}\n")
                    total_count += 1
                
                f.write("\n") # Empty line between major levels

        print(f"Successfully generated {output_path} with {total_count} questions.")
        
    except Exception as e:
        print(f"Error writing output file: {e}")

if __name__ == "__main__":
    # Updated default paths
    input_file = r"f:\geroserverFabu\txtquery\问题集V2.1.txt"
    output_file = r"f:\geroserverFabu\data_process\sampled_questions.txt"
    
    print("开始抽取问题...")
    print(f"输入文件: {input_file}")
    print(f"输出文件: {output_file}")
    print("规则: L1/L2/L3 各20个 (01-6个, 02-6个, 03-8个)")
    
    extract_questions(input_file, output_file)
