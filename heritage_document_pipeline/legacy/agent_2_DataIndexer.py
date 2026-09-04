import os
import re
from typing import List, Optional, Literal
from dotenv import load_dotenv

# 修正后的导入方式
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
import json

import sys
import os

# 将当前目录的data文件夹添加到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))

# 现在可以导入
from historical_cities import historical_cities


load_dotenv()


def extract_protection_period_from_filename(filename: str) -> Optional[str]:
    """从文件名中提取保护期限
    
    匹配格式：[[XXXX-XXXX]]
    文件名示例: Lijiang-Historical-City-Planning_[2025-2035]_full_parsed.md
    """
    base_name = os.path.splitext(os.path.basename(filename))[0]
    
    # 匹配 [[XXXX-XXXX]] 格式
    match = re.search(r'\[(\d{4}-\d{4})\]', base_name)
    if match:
        return match.group(1)
    
    return None


def extract_city_from_filename(filename: str, city_list: list) -> str:
    """
    从文件名中提取城市名
    文件名格式示例: Lijiang-Historical-City-Planning2_[丽江]_full_parsed.md
    """
    # 获取文件名（不含路径和扩展名）
    base_name = os.path.splitext(os.path.basename(filename))[0]
    
    # 匹配 [[城市名]] 格式
    match = re.search(r'\[([^\]]+)\]', base_name)
    if match:
        extracted = match.group(1)
        # 验证提取的内容是否在城市列表中
        for city in city_list:
            if city in extracted:
                return city
    
    # 兼容旧格式：直接检查城市名是否在文件名中
    for city in city_list:
        if city in base_name:
            return city
    
    return ""


# --- 1. 定义语义元数据模型 (LLM 生成) ---
class BlockSemanticAnalysis(BaseModel):
    city_name: Optional[str] = Field(default="", description="所在城市名称（外部注入）")
    chapter_title: Optional[str] = Field(default="", description="该块所属的章节标题（外部注入）")
    article_title: Optional[str] = Field(description="条文标题（如第十九条市域空间整体保护格局）或附表标题（如附表一保护对象名单），如果没有则为 None。这个字段会从block的第一行自动提取，如果第一行没有标题则为空")
    protection_period: Optional[str] = Field(default=None, description="所对应的保护期限，如2025-2035（外部注入）")
    content_type: str = Field(
        description="分类列表，允许1-2个类别：历史城区详细名单、村镇类保护对象详细名单（包括历史文化名镇/历史文化名村/传统村落等）、街区类保护对象详细名单（包括历史文化街区/历史地段等）、文物保护单位详细名单、建筑类保护对象详细名单（包括历史建筑/传统风貌建筑等）、环境要素详细名单、其他历史文化遗产详细名单（包括非物质文化遗产、其他历史文化遗产等）、保护要求（对城区、村落、街区、建筑、文物、环境等各类保护对象的保护要求）、其他背景。如果有2个类别，其中一个必须是'保护要求'。"
    )
    summary: str = Field(description="50字以内的核心摘要")


# --- 1.1 Article Title 分类模型 (快速判断) ---
class ArticleTitleClassification(BaseModel):
    """用LLM快速判断article_title是否可能包含保护对象列表"""
    likely_has_list: bool = Field(description="article_title是否可能包含具体的保护对象名称列表")
    content_type: Optional[str] = Field(default=None, description="如果likely_has_list为false，直接分类为'保护要求'或'其他背景'；如果likely_has_list为true，则为None")

# --- 2. 最终结构化数据 (外部注入 + 语义信息) ---
class IndexedBlock(BaseModel):
    block_id: int
    source_file: str
    raw_content: str  # 外部注入的原文
    analysis: BlockSemanticAnalysis # 嵌套语义分析结果

# --- 3. Agent 2 类实现 ---
class MetadataIndexerAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("MY_CUSTOM_MODEL_NAME"),
            openai_api_key=os.getenv("MY_CUSTOM_API_KEY"),
            base_url=os.getenv("MY_CUSTOM_BASE_URL"),
            temperature=0
        )
        self.parser = PydanticOutputParser(pydantic_object=BlockSemanticAnalysis)
        self.title_classification_parser = PydanticOutputParser(pydantic_object=ArticleTitleClassification)

    def _check_article_title(self, article_title: str) -> ArticleTitleClassification:
        """用LLM快速判断article_title是否可能包含保护对象列表
        
        Args:
            article_title: 条文标题
            
        Returns:
            ArticleTitleClassification: 分类结果
        """
        check_prompt = ChatPromptTemplate.from_template(
            """你是一个历史文化保护规划专家。请根据以下article_title（条文标题），判断该条文是否可能包含具体的保护对象名称列表。

## 判断标准
- 如果条文标题仅包含保护对象类型（如"历史建筑"、"水文化遗产"、"历史城区"），或者包含暗示名单的关键词（如"清单"、"一览表"、"名录"等），则表明这个条文可能会列出具体的保护对象名称名单（如"第十二条 历史建筑"、"第十条 文物保护单位"、"附表三历史文化街区一览表"、"古树名木保护清单"等），则 `likely_has_list` = true，`content_type` 为None，进入下一步分类
- 如果条文标题表明该条文是关于保护要求的内容，则 `likely_has_list` = false，`content_type` 为"保护要求"
- 如果条文标题表明该条文可能是一般性的描述或背景说明，则 `likely_has_list` = false，`content_type` 为"其他背景"

## Article Title（条文标题）：
{article_title}

{format_instructions}""",
            partial_variables={"format_instructions": self.title_classification_parser.get_format_instructions()}
        )
        
        chain = check_prompt | self.llm | self.title_classification_parser
        
        try:
            result = chain.invoke({"article_title": article_title})
            return result
        except Exception as e:
            # 如果解析失败，保守处理：认为可能包含保护对象列表，进行完整语义分析
            # 这样可以避免漏掉真正有保护对象的block
            print(f"    [!] article_title分类失败: {e}，保守起见进行完整语义分析")
            return ArticleTitleClassification(likely_has_list=True, content_type="保护要求")

    def _split_markdown(self, md_text: str) -> List[dict]:
        """
        物理切分逻辑：将 Agent 1 的长输出按"第*条"或"附表"开头的行进行物理分割，
        并追踪当前所在的章节，将章节信息附加到每个分块中。
        
        返回: List[dict], 每个元素包含 {'chunk': str, 'chapter_title': str}
        """
        # 用于存储分块结果和对应的章节信息
        result = []
        
        # 追踪当前章节
        current_chapter = ""
        
        lines = md_text.split('\n')
        
        for line in lines:
            # 检测章节标题（如 "## 第六章市域历史文化遗产保护" 或 "## 附表"）
            cleaned = line.lstrip('# ').strip()
            
            # 检测"第X章"形式的章节标题
            chapter_match = re.match(r'^第[一二三四五六七八九十百千○〇\d]+章', cleaned)
            
            # 检测"附表"作为章节标题（无数字的附表）
            if not chapter_match:
                chapter_match = re.match(r'^附表$', cleaned)
            
            if chapter_match:
                # 更新当前章节
                current_chapter = cleaned
                continue  # 跳过章节标题行，不作为内容
                
            # 检测条号开头的新块（如 "## 第十九条市域空间整体保护格局"）
            # 同时检测"附表一"、"附表1"等作为条号的备选
            article_match = re.match(r'^第[一二三四五六七八九十百千○〇\d]+条', cleaned)
            
            # 检测"附表一"、"附表1"等形式作为条号备选
            if not article_match:
                article_match = re.match(r'^附表[一二三四五六七八九十百千○〇\d]+', cleaned)
            
            if article_match:
                # 如果有之前的块，先保存
                if result and result[-1]['chunk']:
                    result[-1]['chunk'] = result[-1]['chunk'].strip()
                
                # 创建新块
                result.append({
                    'chunk': line + '\n',  # 从这一行开始新块
                    'chapter_title': current_chapter
                })
            else:
                # 继续添加到当前块
                if result:
                    result[-1]['chunk'] += line + '\n'
                else:
                    # 如果还没有块，创建一个（处理文件开头没有条号的情况）
                    result.append({
                        'chunk': line + '\n',
                        'chapter_title': current_chapter
                    })
        
        # 清理每个块
        cleaned_result = []
        for item in result:
            chunk_text = item['chunk'].strip()
            if chunk_text:
                cleaned_result.append({
                    'chunk': chunk_text,
                    'chapter_title': item['chapter_title']
                })
        
        return cleaned_result

    def run(self, full_md_content: str, file_name: str) -> List[IndexedBlock]:
        raw_chunks_with_chapter = self._split_markdown(full_md_content)
        indexed_blocks = []
        
        # 从文件名中提取城市名
        city_name_from_file = extract_city_from_filename(file_name, historical_cities)
        print(f"[*] 从文件名提取到城市名: {city_name_from_file if city_name_from_file else '未识别到'}")
        
        # 从文件名中提取保护期限
        period_from_file = extract_protection_period_from_filename(file_name)
        if period_from_file:
            print(f"[*] 从文件名提取到保护期限: {period_from_file}")
        
        prompt = ChatPromptTemplate.from_template(
            """你是一个历史文化名城保护规划专家。请分析以下文本块并提取元数据。注意：city_name 、protection_period、 chapter_title 不需要你生成，会被外部覆盖。

            如果这个文本块的主要目的是为了列出具体的保护对象名称名单（如"光孝寺"、"六榕塔"、"北京路历史文化街区"、"八达岭长城"等），则可以分类为具体的保护对象详细名单类型，如历史城区详细名单、村镇类保护对象详细名单、街区类保护对象详细名单、文物保护单位详细名单、建筑类保护对象详细名单、环境要素详细名单、其他历史文化遗产详细名单等。

            如果文本块只是描述性/概括性的提到保护对象（如"保护历史建筑"、"维护传统格局"、"加强文物保护"等），或者列出部分具体名称只是为了举例说明保护的重点、特色、框架、体系等等，则应该分类为"保护要求"或者"其他背景"。

            请根据文本内容判断并分类。

{raw_content}

{format_instructions}""",
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
        chain = prompt | self.llm | self.parser

        for i, chunk_info in enumerate(raw_chunks_with_chapter):
            chunk_text = chunk_info['chunk']
            chapter_title = chunk_info['chapter_title']
            
            # 1. 外部注入 block_id 和 raw_content
            current_id = i + 1
            
            # 1.5 从block第一行提取article_title
            first_line = chunk_text.strip().split('\n')[0] if chunk_text.strip() else ""
            # 清理第一行的标题（去掉 ## 等markdown标记）
            article_title = first_line.lstrip('# ').strip()
            
            # 2. 先用LLM快速判断article_title是否可能包含保护对象列表
            title_classification = self._check_article_title(article_title)
            
            # 3. 根据判断结果决定如何处理
            if not title_classification.likely_has_list:
                # article_title表明不太可能包含保护对象列表，直接分类为"保护要求"或"其他背景"
                semantic_data = BlockSemanticAnalysis(
                    city_name=city_name_from_file,
                    chapter_title=chapter_title,
                    article_title=article_title,
                    protection_period=period_from_file,
                    content_type=title_classification.content_type,
                    summary="（基于article_title快速分类）"
                )
                print(f"[*] Block {current_id} article_title判定不包含保护对象列表，直接分类为: {title_classification.content_type}")
            else:
                # article_title表明可能有保护对象列表，进行完整的语义分析
                try:
                    semantic_data = chain.invoke({"raw_content": chunk_text})
                    
                    # 始终使用我们物理分割时追踪到的章节标题
                    semantic_data.chapter_title = chapter_title
                    
                    # 使用从文件名提取的城市名
                    semantic_data.city_name = city_name_from_file
                    
                    # 使用从文件名提取的保护期限
                    if period_from_file:
                        semantic_data.protection_period = period_from_file
                    
                    # 使用从第一行提取的article_title
                    if article_title:
                        semantic_data.article_title = article_title
                        
                except Exception as e:
                    print(f"Block {current_id} 解析失败: {e}，默认分类为保护要求")
                    # 解析失败时使用默认分类
                    semantic_data = BlockSemanticAnalysis(
                        city_name=city_name_from_file,
                        chapter_title=chapter_title,
                        article_title=article_title,
                        protection_period=period_from_file,
                        content_type="保护要求",
                        summary="（解析失败，使用默认分类）"
                    )
            
            # 4. 组装最终对象
            full_block = IndexedBlock(
                block_id=current_id,
                source_file=file_name,
                raw_content=chunk_text,
                analysis=semantic_data
            )
            indexed_blocks.append(full_block)
            
            # 输出信息
            period_info = f", 保护期限: {semantic_data.protection_period}" if semantic_data.protection_period else ""
            print(f"成功索引 Block {current_id}: {semantic_data.article_title} [{semantic_data.content_type}]{period_info}")
                
        return indexed_blocks
    
def load_test_data(file_path: str) -> List[IndexedBlock]:
    blocks = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip(): # 确保不是空行
                item = json.loads(line)
                blocks.append(IndexedBlock(**item))
    return blocks

def output_test_data(result, output_path=None):  
    """保存索引结果到 JSONL 文件
    
    Args:
        result: IndexedBlock 列表
        output_path: 输出路径，默认输出到 data/agent2_{原md文件名}_indexed.jsonl
    """
    if output_path is None:
        # 默认输出到 data 文件夹
        output_path = "data/agent2_indexed_results.jsonl"
        os.makedirs("data", exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for block in result:
            f.write(json.dumps(block.model_dump(), ensure_ascii=False) + "\n")
    print(f"\n数据已成功保存至: {output_path}")
    return output_path


def run_indexer(md_file_path: str, output_path: str = None) -> str:
    """
    运行 Agent 2 索引器
    
    Args:
        md_file_path: 输入的 Markdown 文件路径
        output_path: 输出路径，默认输出到 data/agent2_{原md文件名}_indexed.jsonl
    
    Returns:
        str: 输出的 JSONL 文件路径
    """
    with open(md_file_path, "r", encoding="utf-8") as f:
        md_data = f.read()
    
    # 获取文件名用于提取城市名等信息
    file_name = os.path.basename(md_file_path)
    
    # 如果没有指定输出路径，自动生成
    if output_path is None:
        # 提取 md 文件名（不含路径和扩展名）
        md_basename = os.path.splitext(file_name)[0]
        # 替换 agent1_ 前缀为 agent2_（如果存在）
        md_basename = md_basename.replace("agent1_", "")
        output_path = f"data/agent2_{md_basename}_indexed.jsonl"
        os.makedirs("data", exist_ok=True)
    
    # 运行 Agent
    agent = MetadataIndexerAgent()
    indexed_blocks = agent.run(md_data, file_name)
    
    return output_test_data(indexed_blocks, output_path)


def test_agent():
    # 使用包含城市名的文件名格式
    md_file = r"D:\2026_projects\agent_for_heritage\data\Lijiang-Historical-City-Planning2_[丽江]_[2025-2035]_full_parsed.md"
    return run_indexer(md_file)


def test_content(file_path):
    blocks = load_test_data(file_path)
    for block in blocks[3:8]:                  
        print(f"--- [Block ID: {block.block_id}] ---")
        # pretty_json = json.dumps(block_dict, indent=4, ensure_ascii=False)
        # print(pretty_json)

        print(f"条文标题: {block.analysis.article_title}")


# --- 4. 运行示例 ---
if __name__ == "__main__":
    file_path = test_agent()
    # file_path = "indexed_results.jsonl"
    test_content(file_path)
