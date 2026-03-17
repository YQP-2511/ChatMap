from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pandas as pd
import os
import glob
import subprocess
import sys
import shutil
import time
import re
from typing import List, Optional

app = FastAPI()

# Mount workspace for static access to generated files
app.mount("/workspace", StaticFiles(directory="f:/geroserverFabu"), name="workspace")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount templates
templates = Jinja2Templates(directory="templates")

# Configuration
CSV_ROOT = r"f:\geroserverFabu\csv"
CODE_ROOT = r"f:\geroserverFabu\code"
TARGET_SUBDIRS = ["CSDS60", "DIFYDS180", "DIFYqw"]

class UpdateRowRequest(BaseModel):
    index: int
    success: Optional[str] = ""
    remark: Optional[str] = ""

class BulkUpdateItem(BaseModel):
    index: int
    success: Optional[str] = ""
    remark: Optional[str] = ""

class BulkUpdateRequest(BaseModel):
    path: str
    updates: List[BulkUpdateItem]

class RunCodeRequest(BaseModel):
    script_path: str
    question: Optional[str] = None
    csv_path: Optional[str] = None
    row_index: Optional[int] = None

class BatchRunItem(BaseModel):
    script_path: str
    question: Optional[str] = None
    row_index: Optional[int] = None

class BatchRunRequest(BaseModel):
    items: List[BatchRunItem]
    csv_path: Optional[str] = None

class BatchVerifyRequest(BaseModel):
    csv_path: str
    txt_path: str

SERVER_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = r"f:\geroserverFabu"
RESULTS_ROOT = os.path.join(PROJECT_ROOT, "results")

def sanitize_filename(name: str) -> str:
    # Replace invalid characters with underscore
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def get_result_subdir(script_path: str) -> str:
    abs_script = os.path.abspath(script_path)
    abs_code = os.path.abspath(CODE_ROOT)
    
    if abs_script.startswith(abs_code):
        # It's in code/...
        rel = os.path.relpath(os.path.dirname(abs_script), abs_code)
        # rel could be "1", "2", "1/sub", "."
        if rel == ".":
            return "root"
        # Return the first component? "1"
        parts = rel.split(os.sep)
        return parts[0]
    
    # Check other locations
    if "data_process" in abs_script and "server" in abs_script:
        return "server"
        
    # Fallback: use parent dir name
    return os.path.basename(os.path.dirname(abs_script))

def extract_log_content(script_path: str, question: str) -> str:
    if not script_path or not question:
        return ""
        
    subdir = get_result_subdir(script_path)
    sanitized_question = sanitize_filename(question)
    info_path = os.path.join(RESULTS_ROOT, subdir, sanitized_question, "info.txt")
    
    if not os.path.exists(info_path):
         return ""
         
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Parse STDOUT
        stdout_marker = "STDOUT:\n"
        
        start_idx = content.find(stdout_marker)
        if start_idx != -1:
            start_idx += len(stdout_marker)
            # Find the end of STDOUT section
            # It usually ends with a separator line
            separator = "-" * 40
            end_idx = content.find(separator, start_idx)
            
            if end_idx != -1:
                stdout_content = content[start_idx:end_idx].strip()
            else:
                # Fallback: try to find STDERR
                stderr_idx = content.find("STDERR:\n", start_idx)
                if stderr_idx != -1:
                    stdout_content = content[start_idx:stderr_idx].strip()
                else:
                    stdout_content = content[start_idx:].strip()
            
            return stdout_content
        
        return ""
        
    except Exception:
        return ""

async def update_csv_cell(csv_path: str, row_index: int, col_name: str, value: str):
    if not os.path.exists(csv_path):
        return
    try:
        try:
            df = pd.read_csv(csv_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding='gbk')
        
        if col_name not in df.columns:
            df[col_name] = ""
        
        if 0 <= row_index < len(df):
            df.at[row_index, col_name] = value
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    except Exception as e:
        print(f"Error updating CSV: {e}")

async def execute_script_internal(script_path: str, question: str = None, csv_path: str = None, row_index: int = None):
    # Special handling for HTML files - do not execute, just link
    if script_path.lower().endswith('.html'):
        if not os.path.exists(script_path):
             return {"error": "HTML file not found", "script": script_path}
        
        # Calculate relative path for link
        # script_path is absolute, e.g. f:\geroserverFabu\code\1\foo.html
        # We need relative to f:\geroserverFabu, e.g. code/1/foo.html
        try:
            rel_path = os.path.relpath(script_path, PROJECT_ROOT).replace('\\', '/')
        except ValueError:
            # Fallback if not on same drive (unlikely)
            rel_path = os.path.basename(script_path)
            
        # Update CSV
        if csv_path and row_index is not None:
             await update_csv_cell(csv_path, row_index, "HTML Result", rel_path)
             await update_csv_cell(csv_path, row_index, "是否成功", "是")
             await update_csv_cell(csv_path, row_index, "备注", "已关联现有文件")

        return {
            "stdout": "",
            "stderr": "",
            "returncode": 0,
            "script": script_path,
            "html_link": rel_path
        }

    if not os.path.exists(script_path):
        return {"error": "Script file not found", "script": script_path}
    
    if "geroserverFabu" not in os.path.abspath(script_path):
         return {"error": "Access denied", "script": script_path}

    try:
        script_dir = os.path.dirname(script_path)
        start_time = time.time()
        
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=script_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )
        
        try:
            stdout_bytes, stderr_bytes = process.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout_bytes, stderr_bytes = process.communicate()
            
            if csv_path and row_index is not None:
                await update_csv_cell(csv_path, row_index, "是否成功", "否")
                await update_csv_cell(csv_path, row_index, "备注", "Execution timed out")

            return {
                "error": "Execution timed out (600s limit)", 
                "stdout": stdout_bytes.decode('gbk', errors='ignore'), 
                "stderr": stderr_bytes.decode('gbk', errors='ignore'),
                "script": script_path
            }

        def decode_output(b):
            try:
                return b.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    return b.decode('gbk')
                except UnicodeDecodeError:
                    return b.decode('utf-8', errors='replace')

        stdout_str = decode_output(stdout_bytes)
        stderr_str = decode_output(stderr_bytes)
        
        # Post-processing: Move HTML files
        html_link = None
        found_html = False
        found_geojson = False

        if question:
            sanitized_question = sanitize_filename(question)
            
            # Determine result subdir (e.g. "1", "2", "server")
            subdir = get_result_subdir(script_path)
            
            target_dir = os.path.join(RESULTS_ROOT, subdir, sanitized_question)
            os.makedirs(target_dir, exist_ok=True)

            # Generate info.txt with execution details
            info_path = os.path.join(target_dir, "info.txt")
            try:
                with open(info_path, "w", encoding="utf-8") as f:
                    f.write(f"Script: {script_path}\n")
                    f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}\n")
                    f.write(f"Return Code: {process.returncode}\n")
                    if csv_path:
                        f.write(f"CSV Path: {csv_path}\n")
                    if row_index is not None:
                        f.write(f"Row Index: {row_index}\n")
                    f.write("-" * 40 + "\n")
                    f.write("STDOUT:\n")
                    f.write(stdout_str + "\n")
                    f.write("-" * 40 + "\n")
                    f.write("STDERR:\n")
                    f.write(stderr_str + "\n")
            except Exception as e:
                print(f"Error writing info.txt: {e}")
            
            # Find generated HTML and GeoJSON files in script_dir modified after start_time
            # found_html already initialized to False
            html_link = None
            geojson_link = None
            
            for file in os.listdir(script_dir):
                if file.lower().endswith(('.html', '.geojson')):
                    full_path = os.path.join(script_dir, file)
                    if os.path.getmtime(full_path) >= start_time:
                        # Move file
                        target_path = os.path.join(target_dir, file)
                        shutil.move(full_path, target_path)
                        
                        # Use relative path for link
                        rel_path = f"results/{subdir}/{sanitized_question}/{file}"
                        
                        if file.lower().endswith('.html'):
                            found_html = True
                            html_link = rel_path # Store the last one found
                        elif file.lower().endswith('.geojson'):
                            found_geojson = True
                            geojson_link = rel_path
            
            # Collect all available links
            links = []
            if found_html and html_link:
                links.append(html_link)
            if found_geojson and geojson_link:
                links.append(geojson_link)
            
            final_link = "|".join(links)
            
            if links and csv_path and row_index is not None:
                # Check target column
                target_col = "HTML Result"
                try:
                    try:
                        header_df = pd.read_csv(csv_path, encoding='utf-8', nrows=0)
                    except UnicodeDecodeError:
                        header_df = pd.read_csv(csv_path, encoding='gbk', nrows=0)
                    
                    if "URL" in header_df.columns:
                        target_col = "URL"
                except:
                    pass
                
                await update_csv_cell(csv_path, row_index, target_col, final_link)

        # Update success status based on return code
        if csv_path and row_index is not None:
            if process.returncode != 0:
                await update_csv_cell(csv_path, row_index, "是否成功", "否")
            elif question and not (found_html or found_geojson):
                await update_csv_cell(csv_path, row_index, "是否成功", "否")
                await update_csv_cell(csv_path, row_index, "备注", "运行成功但未生成HTML或GeoJSON文件")


        return {
            "stdout": stdout_str,
            "stderr": stderr_str,
            "returncode": process.returncode,
            "script": script_path,
            "html_link": html_link
        }
    except Exception as e:
        if csv_path and row_index is not None:
            await update_csv_cell(csv_path, row_index, "是否成功", "否")
            await update_csv_cell(csv_path, row_index, "备注", f"Internal Error: {str(e)}")
        return {"error": str(e), "script": script_path}



@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Handle Chrome DevTools request to silence 404 logs
@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_config():
    return JSONResponse(content={})

@app.get("/api/files")
async def list_files():
    # Build tree structure
    # Root: f:\geroserverFabu (Virtual)
    # Children: 
    #   - csv (mapped to f:\geroserverFabu\csv)
    #   - code (mapped to f:\geroserverFabu\code)
    
    root_node = {
        "name": "项目根目录",
        "path": r"f:\geroserverFabu",
        "type": "folder",
        "children": []
    }

    # 1. Build CSV Tree
    csv_node = {
        "name": "csv",
        "path": CSV_ROOT,
        "type": "folder",
        "children": []
    }
    
    if os.path.exists(CSV_ROOT):
        # Add CSV files in CSV_ROOT
        csv_files = glob.glob(os.path.join(CSV_ROOT, "*.csv"))
        for f in csv_files:
            csv_node["children"].append({
                "name": os.path.basename(f),
                "path": f,
                "type": "file"
            })
            
        # Add TARGET_SUBDIRS
        for subdir_name in TARGET_SUBDIRS:
            subdir_path = os.path.join(CSV_ROOT, subdir_name)
            if os.path.exists(subdir_path):
                subdir_node = {
                    "name": subdir_name,
                    "path": subdir_path,
                    "type": "folder",
                    "children": []
                }
                
                # Add CSV files in subdir
                sub_csvs = glob.glob(os.path.join(subdir_path, "*.csv"))
                for f in sub_csvs:
                    subdir_node["children"].append({
                        "name": os.path.basename(f),
                        "path": f,
                        "type": "file"
                    })
                
                csv_node["children"].append(subdir_node)
    
    root_node["children"].append(csv_node)

    # 2. Build Code Tree
    code_node = {
        "name": "code",
        "path": CODE_ROOT,
        "type": "folder",
        "children": []
    }
    
    if os.path.exists(CODE_ROOT):
        # Walk through code directories (e.g. 1, 2)
        # We only want top level subdirs in code folder or files
        try:
            # List items in CODE_ROOT
            items = os.listdir(CODE_ROOT)
            for item in items:
                item_path = os.path.join(CODE_ROOT, item)
                if os.path.isdir(item_path):
                    # Subdirectory (e.g. "1")
                    sub_node = {
                        "name": item,
                        "path": item_path,
                        "type": "folder",
                        "children": []
                    }
                    # List CSVs and Pys in subdir
                    # We specifically want batch_run_stats.csv and .py files?
                    # User said "code" so maybe list all relevant files.
                    # For now, let's list all files in these subdirs to be safe.
                    sub_files = os.listdir(item_path)
                    for sub_file in sub_files:
                        sub_file_path = os.path.join(item_path, sub_file)
                        if os.path.isfile(sub_file_path):
                             # Only add if it is likely relevant (csv, py, html)
                             if sub_file.lower().endswith(('.csv', '.py', '.html')):
                                file_type = "file"
                                if sub_file.lower().endswith('.html'):
                                    file_type = "html"
                                
                                sub_node["children"].append({
                                    "name": sub_file,
                                    "path": sub_file_path,
                                    "type": file_type
                                })
                    code_node["children"].append(sub_node)
                elif os.path.isfile(item_path):
                    if item.lower().endswith(('.csv', '.py', '.html')):
                        file_type = "file"
                        if item.lower().endswith('.html'):
                            file_type = "html"
                            
                        code_node["children"].append({
                            "name": item,
                            "path": item_path,
                            "type": file_type
                        })
        except Exception as e:
            print(f"Error reading code dir: {e}")

    root_node["children"].append(code_node)

    # 3. Build Generated Reports Tree (HTML files in root)
    generated_node = {
        "name": "生成结果 (Root)",
        "path": "generated",
        "type": "folder",
        "children": []
    }
    
    root_dir = r"f:\geroserverFabu"
    try:
        if os.path.exists(root_dir):
            for item in os.listdir(root_dir):
                item_path = os.path.join(root_dir, item)
                if os.path.isfile(item_path) and item.lower().endswith('.html'):
                    generated_node["children"].append({
                        "name": item,
                        "path": item_path,
                        "type": "html"
                    })
        root_node["children"].append(generated_node)
    except Exception as e:
        print(f"Error reading root dir: {e}")

    # 4. Build TxtQuery Tree
    txt_query_root = r"f:\geroserverFabu\txtquery"
    txt_node = {
        "name": "txtquery",
        "path": txt_query_root,
        "type": "folder",
        "children": []
    }
    
    if os.path.exists(txt_query_root):
        try:
            items = os.listdir(txt_query_root)
            for item in items:
                item_path = os.path.join(txt_query_root, item)
                if os.path.isfile(item_path) and item.lower().endswith('.txt'):
                    txt_node["children"].append({
                        "name": item,
                        "path": item_path,
                        "type": "file"
                    })
        except Exception as e:
            print(f"Error reading txtquery dir: {e}")
            
    root_node["children"].append(txt_node)

    # 5. Server HTMLs
    server_node = {
        "name": "Server HTMLs",
        "path": SERVER_ROOT,
        "type": "folder",
        "children": []
    }
    
    try:
        if os.path.exists(SERVER_ROOT):
            for item in os.listdir(SERVER_ROOT):
                item_path = os.path.join(SERVER_ROOT, item)
                if os.path.isfile(item_path) and item.lower().endswith('.html'):
                    server_node["children"].append({
                        "name": item,
                        "path": item_path,
                        "type": "html"
                    })
        root_node["children"].append(server_node)
    except Exception as e:
        print(f"Error reading server dir: {e}")

    # 5. Results (Generated HTMLs)
    results_node = {
        "name": "Results",
        "path": RESULTS_ROOT,
        "type": "folder",
        "children": []
    }

    try:
        if os.path.exists(RESULTS_ROOT):
            # Level 1: Subdirs (1, 2, server, etc.)
            for subdir in os.listdir(RESULTS_ROOT):
                subdir_path = os.path.join(RESULTS_ROOT, subdir)
                if os.path.isdir(subdir_path):
                    subdir_node = {
                        "name": subdir,
                        "path": subdir_path,
                        "type": "folder",
                        "children": []
                    }
                    
                    # Level 2: Questions
                    for item in os.listdir(subdir_path):
                        item_path = os.path.join(subdir_path, item)
                        if os.path.isdir(item_path):
                            question_node = {
                                "name": item,
                                "path": item_path,
                                "type": "folder",
                                "children": []
                            }
                            # Level 3: HTML, TXT, and GeoJSON files
                            for sub_item in os.listdir(item_path):
                                sub_item_path = os.path.join(item_path, sub_item)
                                if os.path.isfile(sub_item_path):
                                    if sub_item.lower().endswith('.html'):
                                        question_node["children"].append({
                                            "name": sub_item,
                                            "path": sub_item_path,
                                            "type": "html"
                                        })
                                    elif sub_item.lower().endswith('.geojson'):
                                        question_node["children"].append({
                                            "name": sub_item,
                                            "path": sub_item_path,
                                            "type": "geojson"
                                        })
                                    elif sub_item.lower().endswith('.txt'):
                                        question_node["children"].append({
                                            "name": sub_item,
                                            "path": sub_item_path,
                                            "type": "file"
                                        })
                            subdir_node["children"].append(question_node)
                    
                    results_node["children"].append(subdir_node)
        root_node["children"].append(results_node)
    except Exception as e:
        print(f"Error reading results dir: {e}")
            
    # 6. TXT Query
    TXT_QUERY_ROOT = r"f:\geroserverFabu\txtquery"
    txt_node = {
        "name": "txtquery",
        "path": TXT_QUERY_ROOT,
        "type": "folder",
        "children": []
    }
    if os.path.exists(TXT_QUERY_ROOT):
        def build_txt_tree(dir_path):
            children = []
            try:
                for item in os.listdir(dir_path):
                    item_path = os.path.join(dir_path, item)
                    if os.path.isdir(item_path):
                        children.append({
                            "name": item,
                            "path": item_path,
                            "type": "folder",
                            "children": build_txt_tree(item_path)
                        })
                    elif item.lower().endswith('.txt'):
                        children.append({
                            "name": item,
                            "path": item_path,
                            "type": "file"
                        })
            except Exception:
                pass
            return children
            
        txt_node["children"] = build_txt_tree(TXT_QUERY_ROOT)
        root_node["children"].append(txt_node)

    return root_node

@app.post("/api/batch_verify")
async def batch_verify(request: BatchVerifyRequest):
    if not os.path.exists(request.csv_path) or not os.path.exists(request.txt_path):
        return {"error": "File not found"}
    
    # 1. Parse TXT
    questions_map = {} 
    lines = []
    try:
        with open(request.txt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        try:
            with open(request.txt_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
        except Exception as e:
            return {"error": f"Failed to read TXT file: {str(e)}"}
            
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Find first opening parenthesis (Chinese or English)
        idx_cn = line.find('（')
        idx_en = line.find('(')
        
        if idx_cn == -1 and idx_en == -1: continue
        
        if idx_cn != -1 and idx_en != -1:
            idx_paren = min(idx_cn, idx_en)
        elif idx_cn != -1:
            idx_paren = idx_cn
        else:
            idx_paren = idx_en
        
        question_part = line[:idx_paren].strip()
        
        # Extract question text, removing numbering (1. or 1、)
        # Regex to match start of line, digits, optional dot/comma, optional space
        question_match = re.match(r'^(\d+)[.、\s]\s*(.*)', question_part)
        if question_match:
            question = question_match.group(2).strip()
        else:
            question = question_part
            
        # Find closing parenthesis corresponding to the opening one
        idx_cn_end = line.find('）', idx_paren)
        idx_en_end = line.find(')', idx_paren)
        
        if idx_cn_end == -1 and idx_en_end == -1: continue
        
        # Find the earliest closing parenthesis after the opening one
        possible_ends = []
        if idx_cn_end != -1: possible_ends.append(idx_cn_end)
        if idx_en_end != -1: possible_ends.append(idx_en_end)
        
        idx_paren_end = min(possible_ends)
        
        paren_content = line[idx_paren+1:idx_paren_end].strip()
        
        if paren_content.lower().startswith('cg'):
            continue
            
        questions_map[question] = paren_content

    print(f"Loaded {len(questions_map)} questions from TXT")

    # 2. Process CSV
    try:
        try:
            df = pd.read_csv(request.csv_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(request.csv_path, encoding='gbk')
            
        # Standardize columns to find QUERY and LAYER
        query_col = None
        layer_col = None
        success_col = '是否成功'
        
        for col in df.columns:
            if col.upper() == 'QUERY' or col == '问题':
                query_col = col
            elif col.upper() == 'LAYER' or col == '图层':
                layer_col = col
                
        if not query_col:
            return {"error": "CSV missing QUERY column (问题/QUERY)"}
        if not layer_col:
            return {"error": "CSV missing LAYER column (图层/LAYER)"}
            
        if success_col not in df.columns:
            df[success_col] = ""
            
        updated_count = 0
        match_count = 0
        
        for index, row in df.iterrows():
            query = str(row[query_col]).strip()
            # Try exact match first
            expected = questions_map.get(query)
            
            # If not found, try stripping numbering from CSV query
            if not expected:
                query_match = re.match(r'^(\d+)[.、\s]\s*(.*)', query)
                if query_match:
                    clean_query = query_match.group(2).strip()
                    expected = questions_map.get(clean_query)
            
            if expected:
                match_count += 1
                actual_layer = str(row[layer_col]) if pd.notna(row[layer_col]) else ""
                
                # Logic update:
                # 1. Split by '或' (OR logic)
                # 2. Split by ',' or '，' (AND logic, order independent)
                
                or_parts = expected.split('或')
                is_match = False
                
                for part in or_parts:
                    part = part.strip()
                    if not part: continue
                    
                    # Split by comma for AND logic
                    sub_items = re.split(r'[,，]', part)
                    
                    all_subs_found = True
                    has_items = False
                    
                    for item in sub_items:
                        item = item.strip()
                        if not item: continue
                        
                        has_items = True
                        if item not in actual_layer:
                            all_subs_found = False
                            break
                    
                    if has_items and all_subs_found:
                        is_match = True
                        break
                
                if is_match:
                    df.at[index, success_col] = '是'
                else:
                    df.at[index, success_col] = '否'
                
                updated_count += 1
            
        df.to_csv(request.csv_path, index=False, encoding='utf-8-sig')
        return {
            "message": f"Batch verification completed. Matched {match_count} questions. Marked {updated_count} as success.",
            "updated": updated_count,
            "total_questions": len(questions_map),
            "matched_questions": match_count
        }
        
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/run_code")
async def run_code(request: RunCodeRequest):
    result = await execute_script_internal(request.script_path, request.question, request.csv_path, request.row_index)
    if "error" in result and result.get("returncode") is None:
        # Check if it was a 404 or 403 based on error message, or just return as is
        # For compatibility with frontend expecting specific error structure
        pass
    return result

@app.post("/api/batch_run")
async def batch_run(request: BatchRunRequest):
    results = []
    # Run sequentially to avoid resource contention
    for item in request.items:
        # Check if result directory already exists
        if item.question:
            sanitized_question = sanitize_filename(item.question)
            
            # Determine result subdir (e.g. "1", "2", "server")
            subdir = get_result_subdir(item.script_path)
            
            target_dir = os.path.join(RESULTS_ROOT, subdir, sanitized_question)
            if os.path.exists(target_dir):
                results.append({
                    "script": item.script_path,
                    "stdout": "",
                    "stderr": f"Skipped: Result directory '{subdir}/{sanitized_question}' already exists.",
                    "returncode": 0,
                    "error": None,
                    "html_link": None
                })
                continue

        result = await execute_script_internal(item.script_path, item.question, request.csv_path, item.row_index)
        results.append(result)
    return {"results": results}

@app.get("/api/file_content")
async def get_file_content(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        # Read CSV
        # Try reading with different encodings if utf-8 fails, but user said utf-8 preferred.
        # However, existing files might be GBK. We'll try utf-8 first, then gbk.
        try:
            df = pd.read_csv(path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding='gbk')
        
        # Ensure columns exist
        save_needed = False
        if "是否成功" not in df.columns:
            df["是否成功"] = ""
            save_needed = True
        if "备注" not in df.columns:
            df["备注"] = ""
            save_needed = True
            
        # Fill NaN with empty string
        df = df.fillna("")

        # Save if we added columns
        if save_needed:
             df.to_csv(path, index=False, encoding='utf-8-sig')
        
        # Convert to records
        data = df.to_dict(orient="records")
        columns = df.columns.tolist()
        
        # Populate Log content if applicable
        # Check for Code/Script column and Question/Query column
        code_col = None
        for col in columns:
            if col.lower() in ['output file', 'script', 'code']:
                code_col = col
                break
        
        question_col = None
        for col in columns:
            if col.lower() in ['question', 'query', '问题']:
                question_col = col
                break
                
        if code_col and question_col:
            # Add 'Log' to columns if not present
            if "Log" not in columns:
                columns.append("Log")
            
            # Populate data
            csv_dir = os.path.dirname(path)
            for row in data:
                script_filename = row.get(code_col)
                question_val = row.get(question_col)
                
                if script_filename and question_val:
                    # Construct full script path
                    # Assuming script is relative to CSV dir if it's just a filename
                    if not os.path.isabs(script_filename):
                         full_script_path = os.path.join(csv_dir, script_filename)
                    else:
                         full_script_path = script_filename
                         
                    log_content = extract_log_content(full_script_path, question_val)
                    row["Log"] = log_content
                else:
                    row["Log"] = ""

        return {"columns": columns, "data": data, "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/get_log")
async def get_log(script_path: str, question: str):
    content = extract_log_content(script_path, question)
    if content:
        return {"content": content}
    return {"content": "Log not found or empty."}

@app.post("/api/update_row")
async def update_row(path: str, update: UpdateRowRequest):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        try:
            df = pd.read_csv(path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding='gbk')
            
        # Ensure columns exist (in case they were missing when file was read but not saved)
        if "是否成功" not in df.columns:
            df["是否成功"] = ""
        if "备注" not in df.columns:
            df["备注"] = ""
            
        # Update row
        if 0 <= update.index < len(df):
            df.at[update.index, "是否成功"] = update.success
            df.at[update.index, "备注"] = update.remark
            
            # Save back
            df.to_csv(path, index=False, encoding='utf-8-sig') # Use utf-8-sig for Excel compatibility
            return {"status": "success"}
        else:
            raise HTTPException(status_code=400, detail="Index out of range")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save_all")
async def save_all(request: BulkUpdateRequest):
    path = request.path
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        try:
            df = pd.read_csv(path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding='gbk')
            
        # Ensure columns exist
        if "是否成功" not in df.columns:
            df["是否成功"] = ""
        if "备注" not in df.columns:
            df["备注"] = ""
            
        # Bulk update
        for item in request.updates:
            if 0 <= item.index < len(df):
                df.at[item.index, "是否成功"] = item.success
                df.at[item.index, "备注"] = item.remark
        
        # Save back
        df.to_csv(path, index=False, encoding='utf-8-sig')
        return {"status": "success", "updated_count": len(request.updates)}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8005)
