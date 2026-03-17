import os
import ast
import sys

def extract_imports_from_file(file_path):
    """
    使用 ast 模块从 Python 文件中提取 import 语句
    """
    imports = set()
    try:
        content = None
        # 尝试 UTF-8
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            pass

        if content is not None:
            try:
                tree = ast.parse(content, filename=file_path)
            except SyntaxError:
                content = None  # 语法错误可能是编码不对导致的乱码，尝试 GBK

        # 如果 UTF-8 失败，尝试 GBK
        if content is None:
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    content = f.read()
                tree = ast.parse(content, filename=file_path)
            except Exception:
                # 如果 GBK 也失败，尝试 errors='ignore'
                try:
                     with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                     tree = ast.parse(content, filename=file_path)
                except Exception as e:
                    print(f"无法解析文件 {file_path}: {e}")
                    return imports

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # import module
                    line = f"import {alias.name}"
                    if alias.asname:
                        line += f" as {alias.asname}"
                    imports.add(line)
            elif isinstance(node, ast.ImportFrom):
                # from module import name
                module = node.module if node.module else ''
                names = []
                for alias in node.names:
                    name_part = alias.name
                    if alias.asname:
                        name_part += f" as {alias.asname}"
                    names.append(name_part)
                
                # 处理相对导入
                level = '.' * node.level
                line = f"from {level}{module} import {', '.join(names)}"
                imports.add(line)
                
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        
    return imports

def main():
    # 默认目标文件夹
    default_target_dir = r"f:\geroserverFabu\code\1"
    
    # 优先检查命令行参数
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
    else:
        # 获取用户输入，如果为空则使用默认值
        try:
            target_dir = input(f"请输入要扫描的文件夹路径 (默认: {default_target_dir}): ").strip()
        except EOFError:
            # 处理非交互式环境或管道输入结束的情况
            target_dir = ""

    if not target_dir:
        target_dir = default_target_dir
        
    if not os.path.exists(target_dir):
        print(f"错误: 文件夹 '{target_dir}' 不存在")
        return

    all_imports = set()
    file_count = 0
    
    print(f"正在扫描文件夹: {target_dir} ...")
    
    # 遍历文件夹
    for root, dirs, files in os.walk(target_dir):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                # print(f"正在处理: {file}")
                file_imports = extract_imports_from_file(file_path)
                all_imports.update(file_imports)
                file_count += 1
    
    # 排序
    sorted_imports = sorted(list(all_imports))
    
    # 输出文件路径
    output_file = "unique_imports.txt"
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# 生成时间: {os.path.basename(sys.argv[0])}\n")
            f.write(f"# 扫描目录: {target_dir}\n")
            f.write(f"# 扫描文件数: {file_count}\n")
            f.write(f"# 总导入语句数: {len(sorted_imports)}\n\n")
            for line in sorted_imports:
                f.write(line + "\n")
                
        print(f"\n成功! 已从 {file_count} 个文件中提取 {len(sorted_imports)} 条唯一的导入语句。")
        print(f"结果已保存至: {os.path.abspath(output_file)}")
        
    except Exception as e:
        print(f"写入结果文件时出错: {e}")

if __name__ == "__main__":
    main()
