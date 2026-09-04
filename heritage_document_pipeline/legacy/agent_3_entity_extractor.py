"""
Agent 3: 保护对象提取 Agent (Entity Extractor)
功能：从每个文本块中扫描可能有的保护对象名称和对应的类型
利用 Agent 2 的粗分类（content_type）进行更精确的细分
"""

import os
import json
import re
from enum import Enum
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
import sys
import os

# 将当前目录的data文件夹添加到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))
from historical_cities import historical_cities


load_dotenv()

# --- Agent 2 定义的粗分类到细分类的映射 ---
CONTENT_TYPE_MAPPING = {
    # 建筑类保护对象详细名单 → 细分
    "建筑类保护对象详细名单": [
        "历史建筑",
        "传统风貌建筑",
        "传统民居",
        "近现代建筑",
    ],
    # 街区类保护对象详细名单 → 细分
    "街区类保护对象详细名单": [
        "历史文化街区",
        "历史地段",
    ],
    # 文物保护单位详细名单 → 细分
    "文物保护单位详细名单": [
        "全国重点文物保护单位",
        "省级文物保护单位",
        "市级文物保护单位",
        "县区级文物保护单位",
        "未定级不可移动文物",
    ],
    # 村镇类保护对象详细名单 → 细分
    "村镇类保护对象详细名单": [
        "历史文化名镇",
        "历史文化名村",
        "传统村落",
    ],
    # 环境要素详细名单 → 细分
    "环境要素详细名单": [
        "古井",
        "古桥",
        "古树名木",
        "石刻",
        "遗址",
        "水系",
    ],
    # 其他历史文化遗产详细名单 → 细分
    "其他历史文化遗产详细名单": [
        "非物质文化遗产",
        "工业文化遗产",
        "农业文化遗产",
        "水利文化遗产",
        "世界文化遗产",
        "世界自然遗产",
    ],
    # 历史城区详细名单 → 细分
    "历史城区详细名单": [
        "历史城区",
        "古城格局",
        "历史风貌区",
    ],
}

# 获取所有细分类别
ALL_DETAILED_TYPES = []
for types in CONTENT_TYPE_MAPPING.values():
    ALL_DETAILED_TYPES.extend(types)

ALL_DETAILED_TYPES.extend([
    "历史文化名城",
    "历史城区",
    "历史文化街区",
    "历史地段",
    "历史文化名镇",
    "历史文化名村",
    "传统村落",
    "文物保护单位",
    "未定级不可移动文物",
    "历史建筑",
    "传统风貌建筑",
    "历史环境要素",
    "古井",
    "古桥",
    "古树名木",
    "水文化遗产",
    "工业文化遗产",
    "农业文化遗产",
    "灌溉工程遗产",
    "非物质文化遗产",
    "地名文化遗产",
    "革命老区",
    "革命遗址",
    "历史遗址",
    "世界文化遗产",
    "世界自然遗产",
    "国家级风景名胜区",
    "省级风景名胜区",
    "自然保护地",
    "历史街巷",
    "老字号",
    "名人文化",
])

# --- 保护对象模型 ---
class ProtectionObject(BaseModel):
    """单个保护对象"""
    name: Optional[str] = Field(default=None, description="保护对象名称，如果没有则填null")
    object_type: Optional[str] = Field(default=None, description="保护对象类型，如果没有则填null")
    city_name: Optional[str] = Field(default=None, description="所属城市名称（从block元数据注入）")
    protection_period: Optional[str] = Field(default=None, description="保护期限，如2025-2035（从block元数据注入）")

class LineExtractionResult(BaseModel):
    """单行提取结果（LLM输出用，不需要block_id）"""
    objects: List[ProtectionObject] = Field(description="从该行提取到的保护对象列表，可能为空")

class ExtractionResult(BaseModel):
    """最终提取结果（包含block_id）"""
    block_id: int = Field(description="对应的文本块ID")
    objects: List[ProtectionObject] = Field(description="提取到的保护对象列表")

class TableHeaderCheck(BaseModel):
    """检查文本行的类型：表名、表头、表行或正文行"""
    line_type: str = Field(description="该行的类型：'A'表示表名（如'附表一：XXX清单'、'表1 XXX名单'），'B'表示表头/列标题（如'序号|名称|类型'），'C'表示表行/数据行（包含具体保护对象信息），'D'表示正文/描述性段落（非表格内容）")

# --- Agent 3: 保护对象提取 Agent ---
class EntityExtractorAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("MY_CUSTOM_MODEL_NAME"),
            openai_api_key=os.getenv("MY_CUSTOM_API_KEY"),
            base_url=os.getenv("MY_CUSTOM_BASE_URL"),
            temperature=0
        )
        self.parser = PydanticOutputParser(pydantic_object=ExtractionResult)
        self.line_parser = PydanticOutputParser(pydantic_object=LineExtractionResult)  # 单行提取用
        self.header_check_parser = PydanticOutputParser(pydantic_object=TableHeaderCheck)
        self.content_type_mapping = CONTENT_TYPE_MAPPING
        self.all_types = ALL_DETAILED_TYPES

        # 需要提取的content_type列表（保护对象详细名单类型）
        self.extractable_types = [
            "历史城区详细名单",
            "村镇类保护对象详细名单",
            "街区类保护对象详细名单",
            "文物保护单位详细名单",
            "建筑类保护对象详细名单",
            "环境要素详细名单",
            "其他历史文化遗产详细名单",
        ]

    def _check_is_table_header(self, line: str) -> TableHeaderCheck:
        """检查一行是表名、表头、表行还是正文行，并识别位置关系
        
        Args:
            line: 文本行
            
        Returns:
            TableHeaderCheck: 检查结果，包含line_type和位置关系信息
        """

        
        # 是表格格式，分析是表头还是表行
        # 用LLM判断
        check_prompt = ChatPromptTemplate.from_template(
            """请分析以下表格行的类型。只能输出一个字母来表示类型。
            
判断标准：
- 'A'（表名）：如"附表一：历史建筑清单"、"表1 文物保护单位名单"、"XX名录"等
- 'B'（表头/列标题）：如"序号|名称|类型"、"编号|名称|保护级别|所在位置"等
- 'C'（表行/数据行）：包含具体保护对象名称的行，如"1|故宫博物院|全国重点文物保护单位|北京"
- 'D'（正文）：非表格内容的描述性段落

## 文本行：
{line}

{format_instructions}""",
            partial_variables={"format_instructions": self.header_check_parser.get_format_instructions()}
        )
        
        chain = check_prompt | self.llm | self.header_check_parser
        
        try:
            result = chain.invoke({"line": line})
            return result
        except Exception as e:
            print(f"    [警告] 表头检测失败: {e}, 正在重试...")
            # 重试一次
            try:
                result = chain.invoke({"line": line})
                return result
            except Exception as e2:
                print(f"    [警告] 表头检测重试失败: {e2}, 默认返回 D")
                # 重试也失败，直接返回 D
                return TableHeaderCheck(line_type="D")
    
    
    def _is_extractable_type(self, content_type: str) -> bool:
        """检查 content_type 是否属于可提取的保护对象详细名单类型
        
        检查 content_type 字符串中是否包含 extractable_types 中的任意一个类型名称。
        
        Args:
            content_type: content_type 字符串
            
        Returns:
            bool: 是否属于可提取类型
        """
        if not content_type:
            return False
        
        # 直接检查 content_type 中是否包含任意一个 extractable_types
        for extractable in self.extractable_types:
            if extractable in content_type:
                return True
        
        return False
    
    def _get_types_for_content_type(self, content_type: str) -> List[str]:
        """根据 content_type 获取对应的类型列表（支持部分匹配）
        
        Args:
            content_type: content_type 字符串，可能包含某个 key 的部分内容
            
        Returns:
            对应的类型列表，如果没有匹配的 key 则返回空列表
        """
        if not content_type:
            return []
        
        for key, types in self.content_type_mapping.items():
            if key in content_type:
                return types
        
        return []
    
    def _infer_type_from_context(self, content_type: Optional[str], chapter_title: str, article_title: str, header_parts: str) -> Optional[str]:
        """根据 content_type、chapter_title、article_title 和表头用 LLM 推断保护对象类型
        
        Args:
            content_type: 内容类型
            chapter_title: 章节标题
            article_title: 条文标题
            header_parts: 表名
            
        Returns:
            推断的类型，如果没有则返回 None
        """
        # 构建推断类型的提示
        infer_prompt = ChatPromptTemplate.from_template(
            """请根据以下信息推断保护对象的类型。

## 可能的内容类型
{content_type}

## 章节标题
{chapter_title}

## 条文标题
{article_title}

## 表名
{header_parts}


请直接输出推断的类型名称，不要有其他解释。如果无法推断，请输出"未知"。""",
            partial_variables={}
        )
        
        chain = infer_prompt | self.llm
        
        try:
            result = chain.invoke({
                "content_type": ", ".join(self._get_types_for_content_type(content_type)) or "（无）",
                "chapter_title": chapter_title or "（无）",
                "article_title": article_title or "（无）",
                "header_parts": header_parts
            })
            inferred = result.content.strip()
            # 如果返回"未知"或空值，返回 None
            if inferred == "未知" or not inferred:
                return None
            return inferred
        except Exception as e:
            print(f"    [警告] 类型推断失败: {e}")
            return None

    def _split_by_lines(self, text: str) -> List[str]:
        """将文本按行分割，过滤空行和纯标题行
        
        识别并保留带编号的列表项（如 "1. xxx"、"（1）xxx"、"一、xxx" 等）
        """
        lines = text.split('\n')
        result = []
        
        for line in lines:
            stripped = line.strip()
            # 跳过空行
            if not stripped:
                continue
            # 跳过纯标题行（以 # 开头且后面没有实际内容）
            if re.match(r'^#+.*$', stripped):
                continue
            # 跳过纯数字或纯序号行（如纯序号、纯点等）
            if re.match(r'^[\d\.\、\）\]]+$', stripped):
                continue
            # 跳过纯符号行（如分隔线 -----------------------）
            if re.match(r'^[-=_*]{3,}$', stripped):
                continue
            result.append(stripped)
        
        return result
    
    def _should_skip_line(self, line: str) -> bool:
        """预判断该行是否可能包含保护对象，如果是描述性文字则跳过
        
        快速过滤明显不是保护对象列表的行，避免不必要的 LLM 调用。
        
        Returns:
            True: 跳过该行（可能不是保护对象）
            False: 保留该行（需要 LLM 判断）
        """
        line = line.strip()
        
        # 太短的行不太可能是保护对象列表
        if len(line) < 4:
            return True
        
        # 跳过纯数字或纯符号行（如序号）
        if re.match(r'^[\d\.\、\）\]\[\-\"\'\”\_\’\（\“\‘\(\)\s]+$', line):
            return True
        
        # 跳过以 "以下" 开头的描述性段落
        if line.startswith("以下") or line.startswith("包括") or line.startswith("包含"):
            return True
        
        # 跳过没有具体名称的政策性描述
        # 如 "加强历史建筑保护"、"做好文物保护工作" 等
        skip_patterns = [
            r'^加强.*保护',
            r'^做好.*工作',
            r'^完善.*制度',
            r'^建立.*机制',
            r'^落实.*要求',
            r'^推进.*建设',
            r'^开展.*调查',
            r'^编制.*规划',
            r'^制定.*措施',
        ]
        for pattern in skip_patterns:
            if re.match(pattern, line):
                return True
        
        return False


    def _build_prompt(self, content_type: Optional[str] = None, chapter_title: str = "", article_title: str = "", table_context: str = "") -> ChatPromptTemplate:
        """构建提示词模板
        
        Args:
            content_type: Agent 2 提供的粗分类（如"建筑类保护对象详细名单"）
            chapter_title: 章节标题（如"第六章市域历史文化遗产保护"）
            article_title: 条文标题（如"第十九条市域空间整体保护格局"）
            table_context: 表头/表名上下文信息
        """
        # 构建上下文信息
        context_parts = []
        if chapter_title:
            context_parts.append(f"所属章节：{chapter_title}")
        if article_title:
            context_parts.append(f"条文标题：{article_title}")
        context_text = "\n".join(context_parts) if context_parts else "（无明确章节/条文标题信息）"
        
        # 加入表头上下文
        table_context_hint = ""
        if table_context:
            table_context_hint = f"\n\n## 表格上下文（来自表头/表名）\n{table_context}\n\n请结合上述表格的列标题和表名信息来识别保护对象类型。"
        
        # 根据粗分类确定可能的细分类
        if content_type and self._get_types_for_content_type(content_type):
            # 使用粗分类对应的细分类
            types_hint = f"\n\n建议优先从以下类型中匹配：\n" + (", ".join(self._get_types_for_content_type(content_type)) or "（无）")
        else:
            # 使用所有类型
            types_hint = "参考类型列表：\n" + "\n".join([f"- {t}" for t in self.all_types[:30]])  # 限制数量
        
        return ChatPromptTemplate.from_template(
            """你是一个历史文化保护规划专家。你的任务是从以下文本行中提取保护对象及其类型。注意：保护对象名称必须是具体的需要保护的建筑、文物、街区等实体，比如"北京路历史文化街区"、"故宫博物院"等，不能是抽象的类型，也不能是市政设施、公共空间、风貌格局、活化利用项目等。"建议申报"的不是保护对象，不要提取。输出要简短。


            ## 上下文信息
            {context_info}
            {table_context}
            {type_hint}

            ## 提取任务
            请识别以下文本行中的保护对象。如果没有保护对象，输出空数组 []。
            - 保护对象名称
            - 对应的类型（从上述类型中选择，或根据上下文合理命名）

            ## 文本行：
            {raw_content}

            {format_instructions}""",
            partial_variables={
                "context_info": context_text,
                "table_context": table_context_hint,
                "type_hint": types_hint,
                "format_instructions": self.line_parser.get_format_instructions()
            }
        )

    def extract_from_block(self, block: Any) -> ExtractionResult:
        """从单个文本块中提取保护对象（逐行提取）
        
        将文本块按行分割，对每行单独调用 LLM 提取，最后合并结果。
        在提取前会先检测每行是否为表头/表名，如果是则将其作为后续行的上下文信息。
        
        Args:
            block: 完整的 IndexedBlock 对象
        """
        block_id = block.block_id
        content = block.raw_content
        
        # 获取 Agent 2 的语义分析结果
        content_type = None
        chapter_title = ""
        article_title = ""
        city_name = None
        protection_period = None
        
        if hasattr(block, 'analysis') and block.analysis:
            content_type = block.analysis.content_type
            chapter_title = block.analysis.chapter_title or ""
            article_title = block.analysis.article_title or ""
            city_name = block.analysis.city_name or None
            protection_period = block.analysis.protection_period or None
        
        print(f"[*] 处理 Block {block_id}, content_type={content_type}")
        
        # 如果content_type不属于可提取类型，直接跳过提取
        if not self._is_extractable_type(content_type):
            print(f"  [-] content_type [{content_type}] 不属于保护对象详细名单类型，跳过提取")
            return ExtractionResult(block_id=block_id, objects=[])
        
        # 对于extractable_types中的类型，直接进行提取
        print(f"  [✓] 该Block属于保护对象详细名单类型，直接提取")
        
        # 按行分割
        lines = self._split_by_lines(content)
        
        if not lines:
            return ExtractionResult(block_id=block_id, objects=[])
        
        # 逐行提取，追踪表格上下文
        all_objects = []
        skip_current_table = False  # 标记是否跳过当前表格（遇到"建议申报"表头时）
        
        # 表格上下文信息（供硬编码提取使用）
        current_table_header = None  # 当前表头信息（TableHeaderCheck对象）
        current_table_name = None  # 当前表格的表名（用于LLM推测类型）
        
        for i, line in enumerate(lines):
            # 首先检查行的类型（A表名/B表头/C表行/D正文）
            if not self._should_skip_line(line):
                try:
                    table_check = self._check_is_table_header(line)
                    
                    if "A" in table_check.line_type:
                        # 表名：整行作为表名
                        line_no_space = line.replace(" ", "").replace("　", "")
                        print(f"  [行 {i+1}] 检测到表名: {line_no_space}")
                        current_table_name = line_no_space  # 整行作为表名
                        
                        # 检查表名是否包含"建议申报"
                        if "建议申报" in line_no_space:
                            skip_current_table = True
                            print(f"  [行 {i+1}] 表名包含'建议申报'，跳过当前表格")
                            current_table_header = None
                            current_table_name = None
                            continue
                        elif skip_current_table:
                            # 如果之前在跳过"建议申报"表格，遇到新表名时恢复
                            skip_current_table = False
                            print(f"  [行 {i+1}] 遇到新表名（{line_no_space}），恢复提取")
                        
                        current_table_header = None  # 表名不是表头，清空表头信息
                        continue
                        
                    elif "B" in table_check.line_type:
                        # 表头：分析列标题，识别名称列和类型列的位置
                        header_parts = [p.strip() for p in line.split('|')]
                        header_parts = [p for p in header_parts if p]  # 去掉空字符串
                        print(f"  [行 {i+1}] 检测到表头: {header_parts}")
                        
                        # 检查表头是否包含"建议申报"
                        line_no_space = line.replace(" ", "").replace("　", "")
                        if "建议申报" in line_no_space:
                            skip_current_table = True
                            print(f"  [行 {i+1}] 表头包含'建议申报'，跳过当前表格")
                            current_table_header = None
                            current_table_name = None
                            continue

                        
                        # 识别列位置
                        name_keywords = ['名称', '名称（', '对象名称', '保护对象', '名称/']
                        type_keywords = ['类型', '保护级别', '级别', '类别', '等级']
                        
                        name_col_idx = None
                        type_col_idx = None
                        
                        for idx, col in enumerate(header_parts):
                            col_no_space = col.replace(" ", "").replace("　", "")
                            # 检查是否是名称列
                            if name_col_idx is None:
                                for kw in name_keywords:
                                    if kw in col_no_space:
                                        name_col_idx = idx
                                        break
                            # 检查是否是类型列
                            if type_col_idx is None:
                                for kw in type_keywords:
                                    if kw in col_no_space:
                                        type_col_idx = idx
                                        break
                        
                        # 如果没有类型列，根据 content_type、chapter_title、article_title 和表头推断类型
                        inferred_type = None
                        if type_col_idx is None:
                            inferred_type = self._infer_type_from_context(content_type, chapter_title, article_title, current_table_name)
                            print(f"  [行 {i+1}] 未检测到类型列，推断类型: {inferred_type}")
                        
                        # 记录表头信息
                        current_table_header = {
                            'has_type_col': type_col_idx is not None,
                            'name_col_idx': name_col_idx,
                            'type_col_idx': type_col_idx,
                            'inferred_type': inferred_type
                        }
                        print(f"  [行 {i+1}] name_col_idx={name_col_idx}, type_col_idx={type_col_idx}, inferred_type={inferred_type}")
                        continue
                        
                    elif "C" in table_check.line_type:
                        # 表行：使用表头识别的列位置读取
                        if skip_current_table:
                            print(f"  [行 {i+1}] 跳过（建议申报表格）: {line[:30]}...")
                            continue
                        
                        if not current_table_header or current_table_header.get('name_col_idx') is None:
                            print(f"  [行 {i+1}] 跳过（未检测到表头或名称列）: {line[:30]}...")
                            continue
                        
                        # 用 | split 处理表行
                        parts = [p.strip() for p in line.split('|')]
                        parts = [p for p in parts if p]  # 去掉空字符串
                        
                        # 使用表头识别的列索引读取
                        name_col_idx = current_table_header.get('name_col_idx')
                        type_col_idx = current_table_header.get('type_col_idx')
                        inferred_type = current_table_header.get('inferred_type')
                        
                        if len(parts) > name_col_idx:
                            name = parts[name_col_idx]
                            
                            # 确定类型
                            obj_type = None
                            if type_col_idx is not None and len(parts) > type_col_idx:
                                obj_type = parts[type_col_idx]
                            elif inferred_type:
                                # 使用表头推断的类型
                                obj_type = inferred_type
                            
                            # 只有名称有效时才创建对象
                            if name and len(name) >= 2:  # 名称至少2个字符
                                obj = ProtectionObject(
                                    name=name,
                                    object_type=obj_type,  # 如果obj_type为None，LLM会根据表名、article_title、content_type推测
                                    city_name=city_name,
                                    protection_period=protection_period
                                )
                                all_objects.append(obj)
                                print(f"  [行 {i+1}] 硬编码提取: name={name}, type={obj_type}")
                            else:
                                print(f"  [行 {i+1}] 跳过（名称无效）: {line[:30]}...")
                        else:
                            print(f"  [行 {i+1}] 跳过（列数不足）: {line[:30]}...")
                        continue
                        
                    else:
                        # 非ABC类型（D类型或检测失败等），直接用LLM提取
                        print(f"  [行 {i+1}] 用LLM提取: {line[:30]}...")
                        chain = self._build_prompt(content_type, chapter_title, article_title, "") | self.llm | self.line_parser
                        result = chain.invoke({"raw_content": line})
                        if result.objects:
                            for obj in result.objects:
                                obj.city_name = city_name
                                obj.protection_period = protection_period
                            all_objects.extend(result.objects)
                            print(f"  [行 {i+1}] LLM提取到 {len(result.objects)} 个保护对象")
                            
                except Exception as e:
                    print(f"  [行 {i+1}] 表头检测失败: {e}")
                    # 检测失败，直接用LLM提取
                    continue
        
        # 合并结果
        return ExtractionResult(
            block_id=block_id,
            objects=all_objects
        )


    def extract_from_blocks(self, blocks: List[Any]) -> List[ExtractionResult]:
        """从多个文本块中提取保护对象（逐行提取）
        
        Args:
            blocks: IndexedBlock 对象列表
        """
        results = []
        
        for block in blocks:
            result = self.extract_from_block(block)
            results.append(result)
            
            block_id = result.block_id
            
            if result.objects:
                print(f"[+] Block {block_id}: 提取到 {len(result.objects)} 个保护对象")
            else:
                print(f"[-] Block {block_id}: 未提取到保护对象")
        
        return results

    def save_results(self, results: List[ExtractionResult], output_path: str = None):
        """保存提取结果到 JSONL 文件（每行一个保护对象）
        
        Args:
            results: 提取结果列表
            output_path: 输出路径，默认输出到 data/agent3_{原md文件名}_protected_objects.jsonl
        """
        # 默认输出到 data 文件夹
        if output_path is None:
            output_path = "data/agent3_protected_objects.jsonl"
            os.makedirs("data", exist_ok=True)
        
        total_objects = 0
        
        with open(output_path, "w", encoding="utf-8") as f:
            for result in results:
                # 逐个保护对象输出为一行
                for obj in result.objects:
                    data = {
                        "name": obj.name,
                        "object_type": obj.object_type,
                        "city_name": obj.city_name,
                        "protection_period": obj.protection_period,
                        "block_id": result.block_id
                    }
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
                    total_objects += 1
        
        print(f"\n[✓] 保护对象提取结果已保存至: {output_path}")
        print(f"[总计] 共提取 {total_objects} 个保护对象")
        
        # 输出统计
        type_counts = {}
        for result in results:
            for obj in result.objects:
                obj_type = obj.object_type
                type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
        
        print("\n[统计] 各类型保护对象数量:")
        for obj_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"  - {obj_type}: {count} 个")
        
        return output_path


def run_extractor(indexed_jsonl_path: str, output_path: str = None) -> str:
    """
    运行 Agent 3 提取器
    
    Args:
        indexed_jsonl_path: Agent 2 的索引结果文件路径
        output_path: 输出路径，默认输出到 data/agent3_{原md文件名}_protected_objects.jsonl
    
    Returns:
        str: 输出的保护对象文件路径
    """
    from agent_2_DataIndexer import load_test_data
    
    # 加载索引数据
    blocks = load_test_data(indexed_jsonl_path)
    print(f"[*] 已加载 {len(blocks)} 个文本块")
    
    # 运行提取（逐行模式）
    agent = EntityExtractorAgent()
    print(f"[*] 提取模式: 逐行")
    
    # 如果没有指定输出路径，自动生成
    if output_path is None:
        # 提取索引文件名（不含路径和扩展名）
        indexed_basename = os.path.splitext(os.path.basename(indexed_jsonl_path))[0]
        # 替换 agent2_ 前缀为 agent3_
        indexed_basename = indexed_basename.replace("agent2_", "")
        output_path = f"data/agent3_{indexed_basename}_protected_objects.jsonl"
        os.makedirs("data", exist_ok=True)
    
    # 提取保护对象
    results = agent.extract_from_blocks(blocks)
    
    # 保存结果
    return agent.save_results(results, output_path)


def test_agent_3():
    """测试 Agent 3（逐行提取）"""
    # 默认使用 Agent 2 的索引文件
    indexed_file = "data/agent2_Lijiang-Historical-City-Planning2_[丽江]_[2025-2035]_indexed.jsonl"
    
    # 如果默认文件不存在，尝试其他可能的文件
    if not os.path.exists(indexed_file):
        import glob
        possible_files = glob.glob("data/agent2_*_indexed.jsonl")
        if possible_files:
            indexed_file = possible_files[0]
        else:
            indexed_file = "indexed_results copy.jsonl"
    
    return run_extractor(indexed_file)


# --- 运行示例 ---
if __name__ == "__main__":
    output = test_agent_3()
    print(f"\n[结果] 输出文件: {output}")