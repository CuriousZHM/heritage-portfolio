"""
统一协调脚本 - 历史文化名城保护规划处理流水线
===============================================
串接 Agent 1 (Scanner) → Agent 2 (DataIndexer) → Agent 3 (EntityExtractor)

功能：
1. 扫描 PDF 并解析为 Markdown（Agent 1）
2. 对 Markdown 进行语义索引（Agent 2）  
3. 提取保护对象实体（Agent 3）

输出文件命名规范（统一输出到 data/ 文件夹）：
- Agent 1: data/agent1_{原文件名}_full_parsed.md
- Agent 2: data/agent2_{原文件名}_indexed.jsonl
- Agent 3: data/agent3_{原文件名}_protected_objects.jsonl
"""

import os
import sys
import argparse
from pathlib import Path

# 确保当前目录在 Python 路径中
sys.path.insert(0, os.path.dirname(__file__))

# 导入各 Agent 的核心函数
import agent_1_Scanner as Scanner
import agent_2_DataIndexer as DataIndexer
import agent_3_entity_extractor as EntityExtractor


def get_output_paths(input_pdf_path: str, data_folder: str = "data") -> dict:
    """
    生成各阶段的输出文件路径
    
    Args:
        input_pdf_path: 输入的 PDF 文件路径
        data_folder: 输出文件夹（默认 data/）
    
    Returns:
        dict: 包含各阶段输出路径的字典
    """
    # 获取不含路径和扩展名的文件名
    pdf_basename = os.path.splitext(os.path.basename(input_pdf_path))[0]
    
    return {
        "agent1_md": os.path.join(data_folder, f"agent1_{pdf_basename}_full_parsed.md"),
        "agent2_indexed": os.path.join(data_folder, f"agent2_{pdf_basename}_indexed.jsonl"),
        "agent3_objects": os.path.join(data_folder, f"agent3_{pdf_basename}_protected_objects.jsonl"),
    }


def run_agent1(pdf_path: str, output_md_path: str) -> tuple:
    """
    运行 Agent 1: 扫描 PDF 并解析为 Markdown
    
    直接调用 Scanner.process_heavy_pdf()，传递输出路径参数
    
    Args:
        pdf_path: 输入的 PDF 文件路径
        output_md_path: 输出的 Markdown 文件路径
    
    Returns:
        tuple: (城市名, 保护期限, 实际输出文件路径)
    """
    print("\n" + "="*60)
    print("【第一阶段】Agent 1 - PDF 扫描与解析")
    print("="*60)
    
    # 直接调用 Agent 1 的核心函数，传入输出路径
    detected_city, detected_period, actual_output = Scanner.process_heavy_pdf(
        pdf_path, 
        output_path=output_md_path
    )
    
    return detected_city, detected_period, actual_output


def run_agent2(md_path: str, output_jsonl_path: str) -> str:
    """
    运行 Agent 2: 对 Markdown 进行语义索引
    
    直接调用 DataIndexer.run_indexer()
    
    Args:
        md_path: 输入的 Markdown 文件路径
        output_jsonl_path: 输出的索引 JSONL 文件路径
    
    Returns:
        str: 实际输出文件路径
    """
    print("\n" + "="*60)
    print("【第二阶段】Agent 2 - 语义索引")
    print("="*60)
    
    # 直接调用 Agent 2 的核心函数
    indexed_path = DataIndexer.run_indexer(md_path, output_jsonl_path)
    
    return indexed_path


def run_agent3(indexed_jsonl_path: str, output_objects_path: str) -> str:
    """
    运行 Agent 3: 提取保护对象实体
    
    直接调用 EntityExtractor.run_extractor()
    
    Args:
        indexed_jsonl_path: Agent 2 的索引结果文件路径
        output_objects_path: 输出的保护对象 JSONL 文件路径
    
    Returns:
        str: 实际输出文件路径
    """
    print("\n" + "="*60)
    print("【第三阶段】Agent 3 - 保护对象提取")
    print("="*60)
    
    # 直接调用 Agent 3 的核心函数
    objects_path = EntityExtractor.run_extractor(indexed_jsonl_path, output_objects_path)
    
    return objects_path


def run_pipeline(pdf_path: str, data_folder: str = "data", skip_agent1: bool = False, skip_agent2: bool = False):
    """
    完整流水线执行
    
    Args:
        pdf_path: 输入的 PDF 文件路径
        data_folder: 输出文件夹（默认 data/）
        skip_agent1: 是否跳过 Agent 1（已有解析好的 MD 文件）
        skip_agent2: 是否跳过 Agent 2（已有索引好的 JSONL 文件）
    
    Returns:
        dict: 包含各阶段输出文件路径的字典
    """
    # 确保 data 文件夹存在
    os.makedirs(data_folder, exist_ok=True)
    
    # 获取输出路径
    output_paths = get_output_paths(pdf_path, data_folder)
    
    print(f"\n{'='*60}")
    print("历史文化名城保护规划处理流水线")
    print(f"{'='*60}")
    print(f"输入 PDF: {pdf_path}")
    print(f"输出目录: {data_folder}")
    print(f"{'='*60}")
    
    # 阶段 1: Agent 1 - PDF 扫描解析
    if skip_agent1:
        print("\n[*] 跳过 Agent 1（用户指定）")
        if os.path.exists(output_paths["agent1_md"]):
            print(f"[*] 使用现有文件: {output_paths['agent1_md']}")
            md_path = output_paths["agent1_md"]
        else:
            raise FileNotFoundError(f"指定的 Agent 1 输出文件不存在: {output_paths['agent1_md']}")
    else:
        detected_city, detected_period, md_path = run_agent1(pdf_path, output_paths["agent1_md"])
        print(f"\n[Agent 1 完成] 城市: {detected_city}, 保护期限: {detected_period}")
    
    # 阶段 2: Agent 2 - 语义索引
    if skip_agent2:
        print("\n[*] 跳过 Agent 2（用户指定）")
        if os.path.exists(output_paths["agent2_indexed"]):
            print(f"[*] 使用现有文件: {output_paths['agent2_indexed']}")
            indexed_path = output_paths["agent2_indexed"]
        else:
            raise FileNotFoundError(f"指定的 Agent 2 输出文件不存在: {output_paths['agent2_indexed']}")
    else:
        indexed_path = run_agent2(md_path, output_paths["agent2_indexed"])
        print(f"\n[Agent 2 完成] 索引文件: {indexed_path}")
    
    # 阶段 3: Agent 3 - 保护对象提取
    objects_path = run_agent3(indexed_path, output_paths["agent3_objects"])
    print(f"\n[Agent 3 完成] 保护对象文件: {objects_path}")
    
    # 总结
    print("\n" + "="*60)
    print("流水线执行完成！")
    print("="*60)
    print(f"生成的中间文件:")
    print(f"  - Agent 1 (Markdown): {md_path}")
    print(f"  - Agent 2 (索引):     {indexed_path}")
    print(f"  - Agent 3 (对象):     {objects_path}")
    print("="*60)
    
    return {
        "agent1_md": md_path,
        "agent2_indexed": indexed_path,
        "agent3_objects": objects_path
    }


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="历史文化名城保护规划处理流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python run_pipeline.py data/Lijiang-Historical-City-Planning2.pdf
  python run_pipeline.py data/Lijiang-Historical-City-Planning2.pdf --skip-agent1
  python run_pipeline.py data/Lijiang-Historical-City-Planning2.pdf -o output_folder
        """
    )
    
    parser.add_argument("input_pdf", help="输入的 PDF 文件路径")
    parser.add_argument("-o", "--output", default="data", help="输出文件夹路径（默认: data）")
    parser.add_argument("--skip-agent1", action="store_true", help="跳过 Agent 1，直接使用现有的 MD 文件")
    parser.add_argument("--skip-agent2", action="store_true", help="跳过 Agent 2，直接使用现有的索引文件")
    parser.add_argument("--list-files", action="store_true", help="列出 data 文件夹中的现有文件")
    
    args = parser.parse_args()
    
    # 如果指定了 --list-files，列出现有文件
    if args.list_files:
        print("\ndata/ 文件夹中的现有文件:")
        print("-" * 40)
        for f in sorted(os.listdir(args.output)):
            filepath = os.path.join(args.output, f)
            if os.path.isfile(filepath):
                size = os.path.getsize(filepath)
                print(f"  {f} ({size/1024:.1f} KB)")
        print("-" * 40)
        return
    
    # 验证输入文件
    if not os.path.exists(args.input_pdf):
        print(f"错误: 输入文件不存在: {args.input_pdf}")
        sys.exit(1)
    
    # 执行流水线
    try:
        run_pipeline(
            args.input_pdf, 
            data_folder=args.output,
            skip_agent1=args.skip_agent1,
            skip_agent2=args.skip_agent2
        )
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
