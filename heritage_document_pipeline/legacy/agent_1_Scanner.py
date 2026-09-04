import os
import gc
from pypdf import PdfReader, PdfWriter
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter
import sys
import os

# 将当前目录的data文件夹添加到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))

# 现在可以导入
from historical_cities import historical_cities

import re


def extract_city_name_from_cover(md_content: str, city_list: list) -> str:
    """
    从封面页内容中识别历史文化名城名称
    遍历 city_list 中的城市名，找到与"历史文化名城"在同一行的城市名
    """
    if not md_content or not md_content.strip():
        return ""
    
    lines = md_content.split('\n')
    
    for line in lines:
        # 查找包含"历史文化名城"的行
        if '历史文化名城' in line:
            # 遍历城市列表，查找该行中是否包含某个城市名
            for city in city_list:
                if city in line:
                    return city
    
    return ""


def extract_protection_period_from_cover(md_content: str) -> str:
    """
    从封面页内容中识别保护期限
    匹配格式（先去空白字符）：
    - XXXX-XXXX (如 2025-2035)
    - XXXX年-XXXX年 (如 2010年-2025年)
    - XXXX年至XXXX年 (如 2025年至2035年)
    返回格式：XXXX-XXXX（不带"年"字）
    """
    if not md_content or not md_content.strip():
        return ""
    
    # 去掉所有空白字符（空格、换行、制表符等）
    full_text = re.sub(r'\s+', '', md_content)
    
    # 匹配保护期限格式，提取年份数字
    patterns = [
        r'(\d{4})-(\d{4})',      # 2025-2035
        r'(\d{4})年-(\d{4})年',   # 2010年-2025年
        r'(\d{4})年至(\d{4})年', # 2025年至2035年
    ]
    
    for pattern in patterns:
        match = re.search(pattern, full_text)
        if match:
            # 返回 XXXX-XXXX 格式
            return f"{match.group(1)}-{match.group(2)}"
    
    return ""

def fix_single_page_markdown(md_content):
    if not md_content or not md_content.strip():
        return md_content

    # 将内容按行切分
    lines = md_content.split('\n')
    
    # 过滤掉纯空行，方便定位真正的“最后一行”
    content_lines = [i for i, line in enumerate(lines) if line.strip()]
    if not content_lines:
        return md_content

    last_content_idx = content_lines[-1]
    last_line = lines[last_content_idx].strip()

    # --- 你的核心逻辑实现 ---
    # 1. 匹配开头：忽略 # 和空格，紧跟“第x章”
    # 2. 匹配末尾：不能是数字（排除页码干扰，如“第一章 1”）
    # 正则解释：
    # ^[#\s]* : 开头任意数量的 # 或 空格
    # 第[一二三四五六七八九十百\d]+[章节] : 核心章号
    # (?!.*\d$) : 负向先行断言，确保行尾不是数字
    title_pattern = r'^[#\s]*第[一二三四五六七八九十百\d]+[章节].*?(?<!\d)$'

    if re.match(title_pattern, last_line):
        # 提取这一行
        target_line = lines.pop(last_content_idx)
        
        # 强制格式化为二级标题（去掉多余空格，加上 ##）
        clean_title = "## " + re.sub(r'^[#\s]*', '', target_line).strip()
        
        # 插入到最前面
        lines.insert(0, clean_title)
    
    # 删除末尾的空行
    while lines and not lines[-1].strip():
        lines.pop()
    
    # 重新组合
    return '\n'.join(lines)
            

def is_toc_page(md_content):
    """检测是否为目录页"""
    if not md_content or not md_content.strip():
        return False
    
    lines = [line.strip() for line in md_content.split('\n') if line.strip()]
    if not lines:
        return False
    
    # 检查第一行是否包含"目录"关键词
    first_line = lines[0]
    if re.search(r'^[#\s]*目[录录]|^[#\s]*Table\s*of\s*Contents', first_line, re.IGNORECASE):
        return True
    
    # 检查目录特征：第x章/条开头的行不以中文字符结尾
    # 目录行特征：以第x章/条开头，结尾不是中文字符（如 . | 数字等）
    # 也支持：附表开头的行不以中文字符结尾
    toc_pattern = r'^第[一二三四五六七八九十百\d]+[章节条].*[^\u4e00-\u9fff]$'
    toc_pattern2 = r'^附表.*[^\u4e00-\u9fff]$'
    toc_count = 0
    
    for line in lines:
        # 优先按表格分隔符 | 分割检查每列（表格格式目录）
        if '|' in line:
            cols = [col.strip() for col in line.split('|') if col.strip()]
            for col in cols:
                if re.match(toc_pattern, col) or re.match(toc_pattern2, col):
                    toc_count += 1
                    if toc_count >= 2:
                        return True
        else:
            # 非表格格式，直接检查整行
            if re.match(toc_pattern, line) or re.match(toc_pattern2, line):
                toc_count += 1
                if toc_count >= 2:
                    return True
    
    return False


def is_cover_page(md_content):
    """检测是否为封面页"""
    if not md_content or not md_content.strip():
        return False
    
    lines = [line.strip() for line in md_content.split('\n') if line.strip()]
    if not lines:
        return False
    
    # 合并所有行进行检查
    full_text = '\n'.join(lines)

    
    # 封面页特征：包含"历史文化名城"+"保护规划"，且包含日期
    has_title = '历史文化名城' in full_text and '保护规划' in full_text
    has_date = re.search(r'\d{2,4}年\d{1,2}月\d{1,2}日|\d{2,4}年\d{1,2}月|\d{2,4}年', full_text)
    
    if len(lines)<= 10 and has_title and has_date:
        return True
    
    return False

def process_heavy_pdf(input_path, chunk_size=1, output_path=None):
    """处理 PDF 文件并转换为 Markdown
    
    Args:
        input_path: 输入的 PDF 文件路径
        chunk_size: 每次处理的页数（默认1）
        output_path: 输出文件路径，默认输出到 data/agent1_{原文件名}_full_parsed.md
    
    Returns:
        tuple: (城市名, 保护期限, 实际输出文件路径)
    """
    chunk_size=1 #现在是对页面进行docling处理后修正，需要写死逐页处理。
    reader = PdfReader(input_path)
    total_pages = len(reader.pages)
    base_name = os.path.splitext(input_path)[0]
    final_markdown = []
    processed_pages = 0  # 统计非目录页数量
    toc_ended = False  # 标记目录是否已结束
    detected_city = ""  # 识别到的城市名
    detected_period = ""  # 识别到的保护期限
    
    # 确定输出路径
    if output_path is None:
        pdf_basename = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join("data", f"agent1_{pdf_basename}_full_parsed.md")
        os.makedirs("data", exist_ok=True)

    print(f"[*] 检测到 {total_pages} 页文档，采用分段解析模式（每段 {chunk_size} 页）...")
    pipeline_options = PdfPipelineOptions()

    pipeline_options.do_ocr = True 
  
    converter = DocumentConverter(
        format_options={
            "pdf": {
                "pipeline_options": pipeline_options
            }
        }
    )
    converter = DocumentConverter() 

    for i in range(0, total_pages, chunk_size):
        writer = PdfWriter()
        start = i
        end = min(i + chunk_size, total_pages)
        
        # 1. 物理切分 PDF
        for page_num in range(start, end):
            writer.add_page(reader.pages[page_num])
        
        temp_chunk = f"temp_split_{start}.pdf"
        with open(temp_chunk, "wb") as f:
            writer.write(f)

        # 2. 局部解析
        try:
            # 每一段都重新初始化 Converter 是最保险的内存释放方式
            
            result = converter.convert(temp_chunk)
            chunk_md = result.document.export_to_markdown()
            
            # 检查页面类型
            is_cover = is_cover_page(chunk_md)
            is_toc = False
            if not is_cover and not toc_ended:
                is_toc = is_toc_page(chunk_md)
            
            if is_cover:
                # 识别封面页中的城市名
                if not detected_city:
                    detected_city = extract_city_name_from_cover(chunk_md, historical_cities)
                    if detected_city:
                        print(f"[*] 识别到历史文化名城: {detected_city}")
                # 识别封面页中的保护期限
                if not detected_period:
                    detected_period = extract_protection_period_from_cover(chunk_md)
                    if detected_period:
                        print(f"[*] 识别到保护期限: {detected_period}")
                print(f"[*] 跳过封面页: 第 {start+1} - {end} 页")
            elif is_toc:
                print(f"[*] 跳过目录页: 第 {start+1} - {end} 页")
            else:
                # 只有非目录页（非封面、非目录）才标记目录已结束
                if not toc_ended:
                    toc_ended = True
                fixed_md = fix_single_page_markdown(chunk_md)
                final_markdown.append(fixed_md)
                processed_pages += 1
                print(f"[+] 已完成: 第 {start+1} - {end} 页")
            
            # 3. 强制清理内存
            
        except Exception as e:
            print(f"[-] 段落 {start}-{end} 解析失败: {e}")
        finally:
            if os.path.exists(temp_chunk):
                os.remove(temp_chunk)
    del converter
    gc.collect() 

    # 4. 合并结果
    full_content = "\n\n".join(final_markdown)
    
    # 构建文件名，包含城市名和保护期限
    pdf_name = os.path.splitext(os.path.basename(input_path))[0]
    filename_parts = []
    
    if detected_city:
        filename_parts.append(f"[{detected_city}]")
    if detected_period:
        filename_parts.append(f"[{detected_period}]")
    
    # 如果检测到城市/期限，重命名输出文件
    if filename_parts:
        dir_name = os.path.dirname(output_path)
        base_name = os.path.splitext(os.path.basename(output_path))[0]
        # 移除 agent1_ 前缀，重新添加
        base_name = base_name.replace("agent1_", "")
        new_filename = f"agent1_{base_name}_{'_'.join(filename_parts)}_full_parsed.md"
        output_file = os.path.join(dir_name, new_filename)
    else:
        output_file = output_path
    
    # 确保目录存在
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(full_content)
    
    # 返回识别到的城市名和保护期限（供 MetadataIndexer 使用）
    print(f"[✓] 全部解析完成！共处理 {processed_pages} 页非目录内容，总计 {total_pages} 页，保存至: {output_file}")
    return detected_city, detected_period, output_file


if __name__ == "__main__":
    target = r"D:\2026_projects\agent_for_heritage\data\Lijiang-Historical-City-Planning2.pdf"
    detected_city, detected_period, output_file = process_heavy_pdf(target)
    print(f"\n[结果] 识别到的城市名: {detected_city}")
    print(f"[结果] 识别到的保护期限: {detected_period}")
    print(f"[结果] 输出的Markdown文件: {output_file}")