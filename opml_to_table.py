from typing import List, Optional, Dict, Any
import xml.etree.ElementTree as ET
import csv

class OPMLProcessor:
    def __init__(
        self,
        category_levels: int = 2,
        content_mode: str = "both",
        content_depth: int = 1,
        column_titles: Optional[List[str]] = None
    ):
        """
        初始化OPML处理器
        
        参数:
        category_levels: int, 分类层级数量
            - 1: 第一层级为具体名称，第二层级开始为列
            - 2: 第一层级为大类，第二层级为具体名称，第三层级开始为列（默认）
            - N: N层分类，第N层为指标名称，第N+1层级开始为列
        content_mode: str, 内容获取方式
            - "both": 同时获取层级内容和下级内容（默认）
            - "sub_only": 只获取下级内容
            - "smart": 如果有下级内容则取下级内容，否则取层级内容
        content_depth: int, 获取下级内容的深度（默认为1）
            - 1: 只获取直接子级内容
            - N: 获取N层子级内容
        column_titles: list, 列标题列表（默认为None）
            - None: 不筛选列
            - ["标题1", "标题2"]: 只保留以这些标题开头的列
        """
        self._validate_inputs(category_levels, content_mode, content_depth)
        self.category_levels = category_levels
        self.content_mode = content_mode
        self.content_depth = content_depth
        self.column_titles = column_titles

    @staticmethod
    def _validate_inputs(category_levels: int, content_mode: str, content_depth: int) -> None:
        """验证输入参数"""
        if category_levels < 1:
            raise ValueError('category_levels必须为正数')
        if content_mode not in ['both', 'sub_only', 'smart']:
            raise ValueError('无效的content_mode')
        if content_depth < 1:
            raise ValueError('content_depth必须为正数')

    def _get_nested_content(self, element: ET.Element, depth: int = 1) -> List[str]:
        """获取嵌套内容"""
        if depth >= self.content_depth:
            return []
        
        contents = []
        for sub_elem in element.findall('outline'):
            text = sub_elem.attrib['text']
            deeper_contents = self._get_nested_content(sub_elem, depth + 1)
            
            if deeper_contents:
                if self.content_mode == 'sub_only':
                    contents.extend(deeper_contents)
                elif self.content_mode == 'smart':
                    contents.append(f'{text}\n{chr(10).join(deeper_contents)}')
                else:  # 'both'
                    contents.append(text)
                    contents.extend(deeper_contents)
            else:
                contents.append(text)
        return contents

    def _get_max_depth(self, element: ET.Element) -> int:
        """计算OPML文档的最大层级深度"""
        if len(element.findall('outline')) == 0:
            return 1
        return 1 + max(self._get_max_depth(child) for child in element.findall('outline'))

    def process_opml(self, file_path: str) -> List[Dict[str, Any]]:
        """处理OPML文件并返回行数据列表"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # 添加最大深度校验
            max_depth = self._get_max_depth(root.find('body'))
            if self.category_levels > max_depth:
                print(f"警告：文件 {file_path} - 请求的分类层级({self.category_levels})超过文档最大层级({max_depth})，跳过处理")
                return [], []
            
        except Exception as e:
            raise ValueError(f'无法解析OPML文件: {str(e)}')

        rows = []
        max_columns = 0

        def process_level(element: ET.Element, current_level: int = 1, categories: Optional[List[str]] = None) -> None:
            nonlocal max_columns
            categories = categories or []
            
            for outline in element.findall('outline'):
                new_categories = categories + [outline.attrib['text']]
                
                # 处理 category_levels=1 的情况
                if self.category_levels == 1:
                    # 直接将第一层作为指标名称
                    row_data = {}
                    row_data['指标名称'] = outline.attrib['text']
                    
                    # 处理第N+1层作为列
                    if self.column_titles:
                        title_contents = {title: None for title in self.column_titles}
                        for content in outline.findall('outline'):
                            matching_title = next(
                                (title for title in self.column_titles 
                                 if content.attrib['text'].startswith(title)),
                                None
                            )
                            if matching_title:
                                content_text = self._process_content(content, matching_title)
                                if content_text:
                                    title_contents[matching_title] = content_text
                        row_data.update(title_contents)
                    else:
                        # 将下级内容横向展开为列
                        contents = outline.findall('outline')
                        for i, content in enumerate(contents, 1):
                            if self.content_mode == 'sub_only':
                                sub_contents = self._get_nested_content(content)
                                row_data[i] = '\n'.join(sub_contents) if sub_contents else None
                            elif self.content_mode == 'smart':
                                sub_contents = self._get_nested_content(content)
                                row_data[i] = '\n'.join(sub_contents) if sub_contents else content.attrib['text']
                            else:  # 'both'
                                text = content.attrib['text']
                                sub_contents = self._get_nested_content(content)
                                if sub_contents:
                                    text = f"{text}\n{chr(10).join(sub_contents)}"
                                row_data[i] = text
                            max_columns = max(max_columns, i)
                        rows.append(row_data)
                    
                # 当达到N-1层时创建行
                elif current_level == self.category_levels - 1:
                    # 创建基础行数据
                    row_data = {f'分类{i}': cat for i, cat in enumerate(new_categories, 1)}
                    
                    # 获取第N层作为指标名称
                    indicators = outline.findall('outline')
                    if indicators:
                        for indicator in indicators:
                            indicator_row = row_data.copy()
                            indicator_row['指标名称'] = indicator.attrib['text']
                            
                            if self.column_titles:
                                # 处理带标题的情况
                                title_contents = {title: None for title in self.column_titles}
                                for content in indicator.findall('outline'):
                                    matching_title = next(
                                        (title for title in self.column_titles 
                                         if content.attrib['text'].startswith(title)),
                                        None
                                    )
                                    if matching_title:
                                        content_text = self._process_content(content, matching_title)
                                        if content_text:
                                            title_contents[matching_title] = content_text
                                indicator_row.update(title_contents)
                            else:
                                # 处理无标题的情况，将下级内容横向展开为列
                                contents = indicator.findall('outline')
                                for i, content in enumerate(contents, 1):
                                    if self.content_mode == 'sub_only':
                                        sub_contents = self._get_nested_content(content)
                                        indicator_row[i] = '\n'.join(sub_contents) if sub_contents else None
                                    elif self.content_mode == 'smart':
                                        sub_contents = self._get_nested_content(content)
                                        indicator_row[i] = '\n'.join(sub_contents) if sub_contents else content.attrib['text']
                                    else:  # 'both'
                                        text = content.attrib['text']
                                        sub_contents = self._get_nested_content(content)
                                        if sub_contents:
                                            text = f"{text}\n{chr(10).join(sub_contents)}"
                                        indicator_row[i] = text
                                    max_columns = max(max_columns, i)
                            
                            rows.append(indicator_row)
                    else:
                        # 如果没有第N层，则创建一个空行，但保留分类信息
                        row_data['指标名称'] = None
                        rows.append(row_data)
                
                # 继续处理下一层
                elif current_level < self.category_levels - 1:
                    process_level(outline, current_level + 1, new_categories)

        process_level(root.find('body'))
        
        if not rows:
            return [], []

        # 构建列名
        category_columns = [f'分类{i}' for i in range(1, self.category_levels)]
        if self.column_titles:
            numeric_columns = self.column_titles
        else:
            numeric_columns = list(range(1, max_columns + 1))

        all_columns = category_columns + ['指标名称'] + numeric_columns
        
        # 确保所有行都有相同的列
        for row in rows:
            for col in all_columns:
                if col not in row:
                    row[col] = None
                    
        return rows, all_columns

    def _process_content(self, content_level: ET.Element, matching_title: Optional[str] = None) -> Optional[str]:
        """处理内容节点"""
        title = content_level.attrib['text']
        content = title
        sub_contents = self._get_nested_content(content_level)

        if sub_contents:
            if self.content_mode == 'sub_only':
                content = chr(10).join(sub_contents)
            elif self.content_mode == 'smart':
                content = chr(10).join(sub_contents)
            else:  # 'both'
                if matching_title:
                    for separator in ['：', ':', '，', ',']:
                        if title.startswith(matching_title + separator):
                            title = title[len(matching_title + separator):].strip()
                            break
                    content = f'{title}{chr(10)}{chr(10).join(sub_contents)}' if title else chr(10).join(sub_contents)
                else:
                    content = f'{content}\n{chr(10).join(sub_contents)}'
        elif self.content_mode == 'sub_only':
            return None
        elif matching_title:
            for separator in ['：', ':', '，', ',']:
                if title.startswith(matching_title + separator):
                    content = title[len(matching_title + separator):].strip()
                    break

        return content if content else None

def write_to_csv(data: List[Dict[str, Any]], columns: List[str], output_file: str) -> None:
    """将数据写入CSV文件"""
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(data)

def test_notitle():
    """处理无标题的OPML文件示例"""
    test_cases = [
        {
            'category_levels': 7,
            'content_mode': 'both',
            'content_depth': 10,
            'input_file': 'WF - 地理节点（6-7级分类）.opml',
            'output_file': '七级分类_地理节点_完整内容_十级.csv'
        },
        {
            'category_levels': 4,
            'content_mode': 'smart',
            'content_depth': 4,
            'input_file': 'WF - 地理节点（新）（前3层分类，下级为介绍）.opml',
            'output_file': '四级分类_地理节点_智能模式_四级.csv'
        },
    ]
    
    for case in test_cases:
        try:
            processor = OPMLProcessor(
                category_levels=case['category_levels'],
                content_mode=case['content_mode'],
                content_depth=case['content_depth']
            )
            rows, columns = processor.process_opml(case['input_file'])
            write_to_csv(rows, columns, case['output_file'])
        except Exception as e:
            print(f"处理文件 {case['input_file']} 时出错: {str(e)}")


def test_title():
    """处理带标题的OPML文件示例"""
    test_cases = [
        {
            'column_titles': ['人口', '大小', '名胜', '食物', '气候'],
            'category_levels': 4,
            'content_mode': 'smart',
            'content_depth': 4,
            'input_file': 'WF - 地理节点（新）（前3层分类，下级为介绍）.opml',
            'output_file': '四级分类_地理节点_带标题筛选.csv'
        }
    ]
    
    for case in test_cases:
        try:
            processor = OPMLProcessor(
                category_levels=case['category_levels'],
                content_mode=case['content_mode'],
                content_depth=case['content_depth'],
                column_titles=case['column_titles']
            )
            rows, columns = processor.process_opml(case['input_file'])
            write_to_csv(rows, columns, case['output_file'])
        except Exception as e:
            print(f"处理文件 {case['input_file']} 时出错: {str(e)}")

if __name__ == '__main__':
    test_notitle()
    test_title()

    
