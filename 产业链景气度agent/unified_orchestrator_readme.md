# 统一 Orchestrator 运行说明

统一入口：

```bash
python orchestrator.py --question "你的自然语言问题"
```

## 路由逻辑

```text
自然语言问题
-> IntentAgent
   -> 如果识别到客户 UID：企业分层链路
   -> 否则如果是新能源汽车/产业链问题：产业链评估链路
```

## 链路一：产业链评估

示例：

```bash
python orchestrator.py --question "新能源汽车产业链分析"
```

执行内容：

```text
抓取新浪 ETF 行情
-> 计算产业趋势、传导效率
-> LLM 生成银行对公产品经理视角报告
```

输出：

```text
outputs/reports/new_energy_chain_etf_report_YYYYMMDD_HHMMSS.md
outputs/reports/new_energy_chain_etf_report_YYYYMMDD_HHMMSS.json
```

## 链路二：企业分层评估

示例：

```bash
python orchestrator.py --question "评估客户UID 3086953029434df7870c1fe17411786920170317111059 的链上地位"
```

执行内容：

```text
抽取 UID
-> 读取 UID 缓存；若无缓存则扫描 data Excel
-> 计算链上地位
-> LLM 生成银行对公客户经理视角的完整经营建议
```

输出：

```text
outputs/enterprise_reports/enterprise_position_UID前缀_YYYYMMDD_HHMMSS.md
outputs/enterprise_reports/enterprise_position_UID前缀_YYYYMMDD_HHMMSS.json
```

## 缓存

企业链路会按 UID 缓存检索结果：

```text
outputs/cache/enterprise_uid/UID.json
```

强制重新扫描 Excel 并刷新缓存：

```bash
python orchestrator.py \
  --question "评估客户UID 3086953029434df7870c1fe17411786920170317111059 的链上地位" \
  --refresh-cache
```

关闭 LLM：

```bash
python orchestrator.py --question "新能源汽车产业链分析" --no-llm
```
