# ChatMap

## 数据库配置
- **数据库**: 达梦数据库 (Dameng)
- **表结构文件**: [`data/auth_20260318101811.sql`](data/auth_20260318101811.sql)

## 数据集
- **图层数据集（50个）**: 
  - [`dataset/dataset4326_1.zip`](dataset/dataset4326_1.zip)
  - [`dataset/dataset4326_2.zip`](dataset/dataset4326_2.zip)

## 核心脚本说明

### 实验与评测
- **基线实验**: [`batch_code_generator.py`](batch_code_generator.py)
- **Cherry Studio 平台实验**: [`cherry-studio/cherrybatch_ask_v2.py`](cherry-studio/cherrybatch_ask_v2.py)
- **Dify 平台实验**: [`difyresearch.py`](difyresearch.py)
- **测试问题集1**: [`txtquery/问题集V2.1.txt`](txtquery/问题集V2.1.txt)
- **测试问题集2**: [`txtquery/问题集60.txt`](txtquery/问题集60.txt)

### 测试用例
- **10 条测试用例及标准工具链**: [`测试用例及工具链.txt`](测试用例及工具链.txt) — 每个问题含已有图层、标准工具链与说明，文末附与问题集题号的对应表
- **题源**: 10 条均取自 [`txtquery/问题集V2.1.txt`](txtquery/问题集V2.1.txt)（L101～L303，覆盖 1～3 级）；其中"展示美国加州相邻的州"亦见 [`txtquery/问题集60.txt`](txtquery/问题集60.txt) L2 第 7 题
- **工具链缩写**: g 查看图层、k 查看图层字段、v 查看图层字段值、f 过滤图层、o 空间过滤、a 指标计算、d 距离计算、b 缓冲区分析、SH 展示图层

### GIS 服务
- **GeoServer 批量发布图层**: [`fabu.py`](fabu.py)
- **验证成功记录 (手动逐个检查确认，问题集V2.1.txt含有部分成功的图层示例)**: [`data_process/server`](data_process/server)

### 数据处理与分析
- **数据处理**:
  - [`data_process/sort_csv_by_questions.py`](data_process/sort_csv_by_questions.py)
  - [`data_process/merge_three_csvs.py`](data_process/merge_three_csvs.py)
- **指标计算**:
  - [`data_process/calculate_metrics_by_level.py`](data_process/calculate_metrics_by_level.py)
