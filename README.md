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

### GIS 服务
- **GeoServer 批量发布图层**: [`fabu.py`](fabu.py)
- **验证成功记录 (手动逐个检查确认，问题集V2.1.txt含有部分成功的图层示例)**: [`data_process/server`](data_process/server)

### 数据处理与分析
- **数据处理**:
  - [`data_process/sort_csv_by_questions.py`](data_process/sort_csv_by_questions.py)
  - [`data_process/merge_three_csvs.py`](data_process/merge_three_csvs.py)
- **指标计算**:
  - [`data_process/calculate_metrics_by_level.py`](data_process/calculate_metrics_by_level.py)
