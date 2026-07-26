# 新浪 ETF 产业链版运行说明

当前简单模式只做新能源汽车产业链：

```text
固定爬取 4 个 ETF 的新浪行情
-> 保存最新报价和日 K 历史数据
-> 读取 data/新能源汽车产业链 下的政策文本
-> 规则计算三个指标：产业趋势、传导效率、政策支持
-> 可选调用 LLM 生成 Agent 解读
```

## 1. 最小测试

只测试爬虫和规则评分，不调用 LLM：

```bash
python orchestrator.py --question "新能源汽车产业链分析" --no-llm
```

成功后会生成：

```text
outputs/crawled/sina_new_energy_etf_YYYYMMDD_HHMMSS/
outputs/reports/new_energy_chain_etf_report_YYYYMMDD_HHMMSS.md
outputs/reports/new_energy_chain_etf_report_YYYYMMDD_HHMMSS.json
```

## 2. 完整评估

默认会调用已配置的大模型生成 Agent 解读：

```bash
python orchestrator.py --question "新能源汽车产业链分析"
```

完整评估中的 LLM 解读采用银行对公产品经理视角，重点输出：

```text
指标含义
当前判断
可落地客群
产品和行动建议
风险与核验
```

如果命令里加了 `--no-llm`，则只会生成规则评分，不会生成对公落地评估。

## 3. 爬取文件

每次运行会生成一个时间戳目录，例如：

```text
outputs/crawled/sina_new_energy_etf_20260718_103000/
```

目录下包含：

```text
etf_latest_quotes.json       4 个 ETF 最新报价
etf_latest_quotes.csv        4 个 ETF 最新报价表
etf_histories_combined.csv   4 个 ETF 合并日 K
etf_history_515030.csv       全链总锚 ETF 日 K
etf_history_159671.csv       上游资源 ETF 日 K
etf_history_159755.csv       中游电池 ETF 日 K
etf_history_159565.csv       下游零部件 ETF 日 K
raw_bundle.json              本次爬取完整数据包
```

查看最新爬虫目录：

```bash
ls -td outputs/crawled/sina_new_energy_etf_* | head -n 1
```

查看合并行情：

```bash
head -n 20 $(ls -td outputs/crawled/sina_new_energy_etf_* | head -n 1)/etf_histories_combined.csv
```

查看最新报告：

```bash
ls -td outputs/reports/new_energy_chain_etf_report_* | head
```

## 4. 固定 ETF

| 层级 | 代码 | 作用 |
|---|---|---|
| 全链总锚 | 515030 | 判断新能源汽车产业链整体市场预期 |
| 上游资源 | 159671 | 判断资源端价格和资源股预期 |
| 中游电池 | 159755 | 判断动力电池核心环节趋势 |
| 下游零部件 | 159565 | 判断整车配套和供应链扩散趋势 |

## 5. 当前指标

| 指标 | 综合权重 | 说明 |
|---|---:|---|
| 产业趋势 | 50% | 看四个 ETF 各自是否形成价格趋势 |
| 传导效率 | 25% | 看上游、中游、下游和全链总锚之间是否顺畅联动 |
| 政策支持 | 25% | 看政策、标准、补贴、基础设施和监管方向是否支撑产业链落地 |

报告末尾会自动写入：

```text
为什么选这四个 ETF
为什么选这三个指标
为什么这样计算
```

## 6. 说明

1. 当前版本使用新浪 ETF 行情，评价的是市场价格视角下的产业链趋势和环节联动。
2. 它不等同于真实供需、利润、产能或政策景气。
3. 非交易日或盘后数据通常对应最近交易日或最后更新时间。
4. 当前版本不构成投资建议。
