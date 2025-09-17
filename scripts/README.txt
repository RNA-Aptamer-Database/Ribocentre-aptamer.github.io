# 管理脚本目录

## 📋 脚本概述

本目录包含 Ribocentre-Aptamer 项目的所有管理和维护脚本，涵盖数据管理、分析处理、资源优化等功能。

## 🔧 核心管理脚本

### 1. 统一适配体管理 (`manage_aptamers.py`)

**功能**: 统一管理有3D和无3D结构的适配体数据

**主要特性**:
- 支持两种类型适配体的统一管理
- 命令行界面简化操作
- 自动数据验证和备份
- 分类系统自动管理

**基本用法**:
```bash
# 查看系统统计
python scripts/manage_aptamers.py stats

# 验证所有数据
python scripts/manage_aptamers.py validate
```

**详细命令**:

#### 有3D结构适配体操作
```bash
# 添加新适配体
python scripts/manage_aptamers.py add-3d "适配体名称" "链接URL" "分类名称"

# 更新现有适配体
python scripts/manage_aptamers.py update-3d "旧名称" --name "新名称" --category "新分类"

# 列出所有适配体
python scripts/manage_aptamers.py list-3d

# 按分类筛选
python scripts/manage_aptamers.py list-3d --category "Fluorescent Aptamers"

# 查看可用分类
python scripts/manage_aptamers.py categories-3d
```

#### 无3D结构适配体操作
```bash
# 添加新适配体
python scripts/manage_aptamers.py add-no3d "适配体名称" "链接URL" "分类名称"

# 更新现有适配体
python scripts/manage_aptamers.py update-no3d "旧名称" --name "新名称" --category "新分类"

# 列出所有适配体
python scripts/manage_aptamers.py list-no3d

# 按分类筛选
python scripts/manage_aptamers.py list-no3d --category "Proteins"

# 查看可用分类
python scripts/manage_aptamers.py categories-no3d
```

### 2. 单独适配体管理 (`add_aptamer.py`)

**功能**: 专门管理无3D结构适配体（向后兼容）

**适用场景**: 
- 只需要管理无3D结构适配体
- 保持旧工作流程的兼容性
- 简化的操作界面

**使用方法**:
```bash
# 添加新适配体
python scripts/add_aptamer.py add "适配体名称" "链接URL" "分类名称"

# 更新适配体信息
python scripts/add_aptamer.py update "旧名称" --name "新名称" --category "新分类" --link "新链接"

# 删除适配体
python scripts/add_aptamer.py delete "适配体名称"

# 列出所有适配体
python scripts/add_aptamer.py list

# 按分类筛选
python scripts/add_aptamer.py list --category "Proteins"

# 验证数据完整性
python scripts/add_aptamer.py validate

# 查看所有可用分类
python scripts/add_aptamer.py categories
```

## 📊 数据处理脚本

### 3. 序列数据更新脚本

#### `update_post_tags_from_sequence_json.py`
**功能**: 从序列JSON文件更新文章标签
```bash
python scripts/update_post_tags_from_sequence_json.py
```

#### `update_post_tags_from_sequence_json_fixed.py`
**功能**: 修复版本的序列标签更新脚本
```bash
python scripts/update_post_tags_from_sequence_json_fixed.py
```

### 4. 荧光数据增强 (`add_more_info_to_fluorescence_json.py`)

**功能**: 为荧光适配体数据添加详细信息

**特性**:
- 自动分析荧光适配体属性
- 添加结构和功能信息
- 增强数据完整性

```bash
python scripts/add_more_info_to_fluorescence_json.py
```

### 5. 链接器管理 (`add_linker_to_json.py`)

**功能**: 为JSON数据添加链接器信息

**应用场景**:
- 建立适配体之间的关联
- 添加参考链接
- 完善数据结构

```bash
python scripts/add_linker_to_json.py
```

## 🔍 数据分析脚本

### 6. 结果分析工具

#### `analyze_matching_results.py`
**功能**: 分析匹配结果数据
```bash
python scripts/analyze_matching_results.py
```
- 统计匹配成功率
- 分析数据质量
- 生成分析报告

#### `generate_keyword_freq.py`
**功能**: 生成关键词频率统计
```bash
python scripts/generate_keyword_freq.py
```
- 分析文档关键词分布
- 生成词频统计
- 支持搜索优化

### 7. 结构数据处理

#### `parse_structures.py`
**功能**: 解析结构数据文件
```bash
python scripts/parse_structures.py
```
- 处理PDB结构文件
- 提取结构信息
- 标准化数据格式

#### `extract_refs.py`
**功能**: 提取参考文献信息
```bash
python scripts/extract_refs.py
```
- 从文档中提取引用
- 格式化参考文献
- 建立引用数据库

## 🧹 数据清理脚本

### 8. Excel数据处理 (`excel_cleaner.py`)

**功能**: 清理和标准化Excel数据

**处理内容**:
- 去除空行和无效数据
- 标准化数据格式
- 修复数据错误

```bash
python scripts/excel_cleaner.py
```

### 9. 数据标准化工具

#### `round_gc_content.py`
**功能**: 对GC含量进行四舍五入处理
```bash
python scripts/round_gc_content.py
```

#### `check_linker_validity.py`
**功能**: 检查链接器数据的有效性
```bash
python scripts/check_linker_validity.py
```

#### `jsonmerge.py`
**功能**: 合并多个JSON文件
```bash
python scripts/jsonmerge.py
```

### 10. 其他工具脚本

#### `extractApplications.py`
**功能**: 提取应用信息数据
```bash
python scripts/extractApplications.py
```

#### `temp_phase_replace.py`
**功能**: 临时阶段替换工具
```bash
python scripts/temp_phase_replace.py
```

#### `tiquluzhizhongdewenbenchaoianjie.py`
**功能**: 特定文本处理工具
```bash
python scripts/tiquluzhizhongdewenbenchaoianjie.py
```

## 🌐 外部API集成

### 11. PubMed API集成 (`pubmed_api_updater.py`)

**功能**: 自动更新PubMed文献信息

**特性**:
- 自动获取最新文献数据
- 更新引用信息
- 同步PubMed数据库

```bash
python scripts/pubmed_api_updater.py
```

**配置说明**:
- 需要PubMed API密钥
- 支持批量更新
- 自动错误处理和重试

## ⚡ 前端资源优化

### 12. JavaScript压缩 (`minify-js.js`)

**功能**: 压缩JavaScript文件以提高性能

**特性**:
- 使用UglifyJS进行压缩
- 保留关键注释
- 生成source map

```bash
node scripts/minify-js.js
```

### 13. CSS压缩 (`minify-css.js`)

**功能**: 压缩CSS文件

**特性**:
- 移除冗余代码
- 优化选择器
- 减少文件大小

```bash
node scripts/minify-css.js
```

### 14. 压缩效果测试 (`test-minification.js`)

**功能**: 测试和验证压缩效果

```bash
node scripts/test-minification.js
```

## 📋 脚本分类索引

### 按功能分类

#### 🎯 核心管理
- `manage_aptamers.py` - 统一适配体管理
- `add_aptamer.py` - 单独适配体管理

#### 📊 数据处理
- `update_post_tags_from_sequence_json.py` - 序列标签更新
- `add_more_info_to_fluorescence_json.py` - 荧光数据增强
- `add_linker_to_json.py` - 链接器添加

#### 🔍 分析工具
- `analyze_matching_results.py` - 结果分析
- `generate_keyword_freq.py` - 关键词分析
- `parse_structures.py` - 结构解析
- `extract_refs.py` - 文献提取

#### 🧹 数据清理
- `excel_cleaner.py` - Excel清理
- `round_gc_content.py` - GC含量标准化
- `check_linker_validity.py` - 链接器验证
- `jsonmerge.py` - JSON合并

#### 🌐 外部集成
- `pubmed_api_updater.py` - PubMed API

#### ⚡ 性能优化
- `minify-js.js` - JavaScript压缩
- `minify-css.js` - CSS压缩
- `test-minification.js` - 压缩测试

### 按编程语言分类

#### Python脚本 (18个)
- 数据管理和处理的主力工具
- 完整的命令行界面
- 丰富的数据验证功能

#### JavaScript脚本 (3个)
- 前端资源优化
- 构建和部署工具
- 性能测试工具

## 🚀 使用指南

### 新手快速上手

1. **基础操作**: 从 `manage_aptamers.py` 开始
2. **查看帮助**: 使用 `--help` 参数查看详细说明
3. **验证数据**: 操作前后都要运行 `validate` 命令

### 日常维护流程

```bash
# 1. 检查当前状态
python scripts/manage_aptamers.py stats

# 2. 执行必要的操作
python scripts/manage_aptamers.py add-3d "新适配体" "链接" "分类"

# 3. 验证数据完整性
python scripts/manage_aptamers.py validate

# 4. 更新前端资源（如需要）
node scripts/minify-js.js
node scripts/minify-css.js
```

### 故障排除

#### 常见问题

1. **权限错误**: 确保脚本有执行权限
2. **依赖缺失**: 检查Python/Node.js依赖
3. **数据冲突**: 使用验证命令检查数据完整性

#### 调试技巧

```bash
# 查看脚本详细输出
python scripts/manage_aptamers.py --verbose

# 使用调试模式
python -m pdb scripts/manage_aptamers.py

# 检查脚本语法
python -m py_compile scripts/manage_aptamers.py
```

## 📦 依赖管理

### Python依赖

主要依赖包括：
- `json` - JSON数据处理
- `pathlib` - 文件路径处理
- `argparse` - 命令行参数解析
- `collections` - 数据结构扩展

### Node.js依赖

主要依赖包括：
- `uglify-js` - JavaScript压缩
- `clean-css` - CSS压缩
- `fs` - 文件系统操作

### 安装依赖

```bash
# Python依赖（标准库，通常无需额外安装）
python -m pip install --upgrade pip

# Node.js依赖
npm install uglify-js clean-css-cli
```

## 🔒 安全注意事项

### 数据备份

所有修改数据的脚本都会：
- 自动创建备份文件
- 保留原始数据副本
- 提供回滚机制

### 权限控制

- 脚本只修改指定的数据文件
- 不会访问系统敏感目录
- 提供操作日志记录

## 📝 开发指南

### 添加新脚本

1. 创建新的脚本文件
2. 添加详细的文档注释
3. 实现命令行参数解析
4. 提供帮助信息
5. 更新本README文档

### 代码规范

- 使用有意义的变量名
- 添加详细的注释
- 实现错误处理
- 提供使用示例

## 🔗 相关链接

- **技术文档**: `../doc/README.md`
- **项目主文档**: `../PROJECT_DOCUMENTATION.md`
- **在线版本**: [Ribocentre-Aptamer](https://aptamer.ribocentre.org)

---

*本脚本集合提供了完整的项目管理工具链，涵盖数据管理、分析处理、性能优化等各个方面。*

*最后更新: 2024年12月* 