"""
供需匹配指标构建脚本
输出（不做聚合）：
  1. price_scissors.csv   — 月度价格剪刀差（上游原材料YoY - 出厂PPI YoY）
  2. pmi_detail.csv       — PMI分项：生产指数/新订单/库存（NBS月报HTML解析）
  3. capacity_util.csv    — 分行业季度产能利用率（NBS已缓存HTML解析）
  4. production_sales.csv — 汽车月度产销量及产销率（CPCA数据）
"""
import sys, io, os, re, json, time, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

try:
    import pandas as pd
    import requests
    from bs4 import BeautifulSoup
    import akshare as ak
except ImportError as e:
    print(f"缺少依赖: {e}")
    sys.exit(1)

BASE     = os.path.dirname(os.path.abspath(__file__))
NBS_DIR  = r"F:\严肃\银行\招商银行\数据\NBS数据"
NBS_RPT  = os.path.join(NBS_DIR, "cache", "nbs_reports")
MACRO    = os.path.join(NBS_DIR, "cache", "macro")
OUTDIR   = BASE
os.makedirs(OUTDIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 产业链 → 上游原材料类别（企业商品价格指数分项）
CHAIN_MATERIAL = {
    "半导体产业链":     ["矿产品"],
    "新能源汽车产业链": ["矿产品", "煤油电"],
    "低空经济产业链":   ["矿产品"],
    "机器人产业链":     ["矿产品"],
    "生物医药产业链":   ["矿产品"],
}

# 产业链 → NBS行业名（产能利用率映射）
CHAIN_CAP_INDUSTRY = {
    "半导体产业链":     ["计算机、通信和其他电子设备制造业"],
    "新能源汽车产业链": ["汽车制造业", "电气机械和器材制造业"],
    "低空经济产业链":   ["铁路、船舶、航空航天和其他运输设备制造业"],
    "机器人产业链":     ["通用设备制造业", "专用设备制造业"],
    "生物医药产业链":   ["医药制造业"],
}


# ════════════════════════════════════════════════════════════
# 1. 价格剪刀差
# ════════════════════════════════════════════════════════════

def build_price_scissors():
    print("\n[1/4] 构建价格剪刀差...")

    # 加载企业商品价格指数（上游原材料）
    qysp_path = os.path.join(MACRO, "企业商品价格指数_月度.csv")
    if not os.path.exists(qysp_path):
        print("  [SKIP] 未找到企业商品价格指数文件")
        return pd.DataFrame()

    mat_df = pd.read_csv(qysp_path)
    # 列：月份, 总指数-同比增长, 矿产品-同比增长, 煤油电-同比增长, 农产品-同比增长
    mat_df = mat_df.rename(columns={"月份": "月份"})
    # 提取月份文字 -> 标准化
    mat_df["月份"] = mat_df["月份"].astype(str)

    # 加载PPI出厂价格（中游）
    ppi_path = os.path.join(MACRO, "PPI月度_出厂价格.csv")
    if not os.path.exists(ppi_path):
        print("  [SKIP] 未找到PPI月度文件")
        return pd.DataFrame()

    ppi_df = pd.read_csv(ppi_path)
    print(f"  PPI列名: {list(ppi_df.columns)}")
    # 找YoY列
    ppi_yoy_col = next((c for c in ppi_df.columns if "同比" in c), None)
    if not ppi_yoy_col:
        ppi_yoy_col = ppi_df.columns[2] if len(ppi_df.columns) >= 3 else None
    ppi_df = ppi_df.rename(columns={ppi_df.columns[0]: "月份"})
    ppi_df["月份"] = ppi_df["月份"].astype(str)

    rows = []
    for chain, mat_keys in CHAIN_MATERIAL.items():
        for mat_key in mat_keys:
            # 找对应列
            yoy_col = next((c for c in mat_df.columns if mat_key in c and "同比" in c), None)
            if not yoy_col:
                continue

            merged = pd.merge(
                mat_df[["月份", yoy_col]].rename(columns={yoy_col: "上游原料YoY"}),
                ppi_df[["月份", ppi_yoy_col]].rename(columns={ppi_yoy_col: "出厂PPIYOY"}),
                on="月份", how="inner"
            )
            merged["产业链"] = chain
            merged["原料类别"] = mat_key
            merged["价格剪刀差"] = merged["上游原料YoY"] - merged["出厂PPIYOY"]
            rows.append(merged[["月份", "产业链", "原料类别", "上游原料YoY", "出厂PPIYOY", "价格剪刀差"]])

    if not rows:
        return pd.DataFrame()

    df = pd.concat(rows, ignore_index=True)
    out = os.path.join(OUTDIR, "price_scissors.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"  [OK] 输出 {len(df)} 行 → {out}")
    return df


# ════════════════════════════════════════════════════════════
# 2. PMI 分项指标（NBS月报HTML）
# ════════════════════════════════════════════════════════════

def parse_pmi_html(html_text, pub_date):
    """从NBS月报HTML中提取PMI各分项"""
    soup = BeautifulSoup(html_text, "lxml")
    # 找正文
    content = ""
    for sel in [".TRS_Editor", "#zoom", ".article-content", ".content"]:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 80:
            content = el.get_text("\n", strip=True)
            break
    if not content:
        content = soup.get_text("\n", strip=True)

    rows = []
    # PMI分项通常格式：
    # "生产指数为52.3%，比上月上升0.4个百分点"
    # "新订单指数为50.7%"
    # NBS PMI报告数据表：分项名 | 本月 | 上月
    pmi_items = [
        ("制造业PMI", r"制造业采购经理指数.*?(\d+\.?\d*)%"),
        ("生产指数",  r"生产指数[为是](\d+\.?\d*)%"),
        ("新订单指数", r"新订单指数[为是](\d+\.?\d*)%"),
        ("原材料库存", r"原材料库存指数[为是](\d+\.?\d*)%"),
        ("产成品库存", r"产成品库存指数[为是](\d+\.?\d*)%"),
        ("从业人员",  r"从业人员指数[为是](\d+\.?\d*)%"),
        ("供应商配送", r"供应商配送时间指数[为是](\d+\.?\d*)%"),
        ("新出口订单", r"新出口订单指数[为是](\d+\.?\d*)%"),
        ("进口指数",  r"进口指数[为是](\d+\.?\d*)%"),
    ]

    for item_name, pattern in pmi_items:
        m = re.search(pattern, content)
        if m:
            rows.append({
                "报告日期": pub_date,
                "PMI分项": item_name,
                "指数值": float(m.group(1)),
            })

    # 尝试从表格提取（更准确）
    tables = soup.find_all("table")
    for tbl in tables:
        trs = tbl.find_all("tr")
        for tr in trs:
            tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(tds) >= 2 and re.search(r"指数|PMI", tds[0]):
                try:
                    val = float(re.sub(r"[^\d\.]", "", tds[1]))
                    if 30 < val < 70:  # PMI合理范围
                        rows.append({
                            "报告日期": pub_date,
                            "PMI分项": tds[0],
                            "指数值": val,
                        })
                except (ValueError, IndexError):
                    pass

    return rows


def fetch_pmi_detail():
    print("\n[2/4] 构建PMI分项...")
    all_rows = []

    # 先检查缓存目录是否有PMI报告HTML
    if os.path.exists(NBS_RPT):
        for fname in os.listdir(NBS_RPT):
            if ("采购经理" in fname or "PMI" in fname) and fname.endswith(".html"):
                fpath = os.path.join(NBS_RPT, fname)
                with open(fpath, encoding="utf-8") as f:
                    html = f.read()
                date_m = re.search(r"(20\d{2}年\d{1,2}月)", fname)
                pub_date = date_m.group(1) if date_m else fname[:20]
                rows = parse_pmi_html(html, pub_date)
                all_rows.extend(rows)
                print(f"  [OK] {fname[:50]}: {len(rows)}条")

    # 若无缓存，从AKShare拉取PMI总指数（作为基础）
    if not all_rows:
        print("  NBS PMI月报未缓存，使用AKShare总PMI数据...")
        try:
            df_pmi = ak.macro_china_pmi()
            print(f"  AKShare PMI列名: {list(df_pmi.columns)}")
            # 重塑为长格式
            df_pmi["报告日期"] = df_pmi.iloc[:, 0]
            for col in df_pmi.columns[1:]:
                if col == "报告日期":
                    continue
                sub = df_pmi[["报告日期", col]].copy()
                sub.columns = ["报告日期", "指数值"]
                sub["PMI分项"] = col
                all_rows.extend(sub.to_dict("records"))
        except Exception as e:
            print(f"  [SKIP] AKShare PMI失败: {e}")

    # 从NBS网站尝试获取当月PMI报告
    if not all_rows:
        print("  尝试从NBS网站获取PMI分项...")
        try:
            r = requests.get("https://www.stats.gov.cn/sj/zxfb/", headers=HEADERS, timeout=15, verify=False)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml")
                for a in soup.find_all("a"):
                    href = a.get("href", "")
                    title = a.get_text(strip=True)
                    if "采购经理" in title and re.search(r'\./20\d{4}/', href):
                        url = "https://www.stats.gov.cn/sj/zxfb/" + href.lstrip("./")
                        r2 = requests.get(url, headers=HEADERS, timeout=15, verify=False)
                        if r2.status_code == 200:
                            r2.encoding = "utf-8"
                            date_m = re.search(r"(20\d{2}[年/]\d{1,2}[月/])", title)
                            pub_date = date_m.group(1) if date_m else "2026年7月"
                            rows = parse_pmi_html(r2.text, pub_date)
                            all_rows.extend(rows)
                            print(f"  [OK] {title[:50]}: {len(rows)}条")
                        time.sleep(0.5)
        except Exception as e:
            print(f"  [SKIP] NBS PMI请求失败: {e}")

    if not all_rows:
        print("  [SKIP] 无PMI分项数据")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["报告日期", "PMI分项"])
    out = os.path.join(OUTDIR, "pmi_detail.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"  [OK] 输出 {len(df)} 行 → {out}")
    return df


# ════════════════════════════════════════════════════════════
# 3. 分行业产能利用率
# ════════════════════════════════════════════════════════════

def parse_capacity_html(html_path):
    """解析产能利用率HTML报告中的行业表格"""
    with open(html_path, encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")
    # 提取发布日期
    date_m = re.search(r"(20\d{2})年(一|二|三|四)季度", html)
    if date_m:
        qmap = {"一": "Q1", "二": "Q2", "三": "Q3", "四": "Q4"}
        period = f"{date_m.group(1)}-{qmap[date_m.group(2)]}"
    else:
        period = "未知"

    rows = []
    # 文本解析：段落格式 "行业名为XX.X%"
    content_el = soup.select_one(".TRS_Editor, #zoom, .article-content") or soup.find("body")
    content = content_el.get_text("\n", strip=True) if content_el else ""

    pattern = re.compile(
        r"([^，。\n]{4,30}(?:业|工业))[产能利用率为是]*(?:：)?(?:为|是)?\s*(\d+\.?\d*)\s*%"
    )
    seen = set()
    for m in pattern.finditer(content):
        industry = m.group(1).strip()
        rate = float(m.group(2))
        if industry in seen or rate < 40 or rate > 100:
            continue
        seen.add(industry)
        # 匹配产业链
        chain_tags = []
        for chain, industries in CHAIN_CAP_INDUSTRY.items():
            if any(ind in industry or industry in ind for ind in industries):
                chain_tags.append(chain)
        rows.append({
            "报告期": period,
            "行业": industry,
            "产能利用率_%": rate,
            "产业链标签": ";".join(chain_tags) if chain_tags else "",
        })

    # 表格解析（更准确）
    for tbl in soup.find_all("table"):
        trs = tbl.find_all("tr")
        for tr in trs:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            industry = cells[0].lstrip("其中：").strip()
            try:
                rate = float(cells[1].replace(",", ""))
                if 40 < rate < 100 and len(industry) > 2:
                    if industry not in seen:
                        seen.add(industry)
                        chain_tags = []
                        for chain, industries in CHAIN_CAP_INDUSTRY.items():
                            if any(ind in industry or industry in ind for ind in industries):
                                chain_tags.append(chain)
                        rows.append({
                            "报告期": period,
                            "行业": industry,
                            "产能利用率_%": rate,
                            "产业链标签": ";".join(chain_tags) if chain_tags else "",
                        })
            except (ValueError, IndexError):
                continue

    return rows


def build_capacity_util():
    print("\n[3/4] 构建产能利用率...")
    all_rows = []

    if os.path.exists(NBS_RPT):
        for fname in os.listdir(NBS_RPT):
            if "产能利用率" in fname and fname.endswith(".html"):
                fpath = os.path.join(NBS_RPT, fname)
                rows = parse_capacity_html(fpath)
                all_rows.extend(rows)
                print(f"  [OK] {fname[:60]}: {len(rows)}条")

    if not all_rows:
        print("  [SKIP] 未找到产能利用率报告HTML")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["报告期", "行业"])
    out = os.path.join(OUTDIR, "capacity_util.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"  [OK] 输出 {len(df)} 行 → {out}")
    return df


# ════════════════════════════════════════════════════════════
# 4. 汽车产销率
# ════════════════════════════════════════════════════════════

def build_production_sales():
    print("\n[4/4] 构建汽车产销率...")
    rows_list = []

    # 获取月度销量（CPCA乘联会）
    try:
        sales_df = ak.car_market_total_cpca()
        print(f"  CPCA销量列名: {list(sales_df.columns)}")
        # 重塑：月份 | 年份 | 销量（万辆）
        id_col = sales_df.columns[0]
        for col in sales_df.columns[1:]:
            year = str(col).replace("年", "")
            for _, row in sales_df.iterrows():
                month = str(row[id_col])
                val = row[col]
                try:
                    rows_list.append({
                        "年份": year, "月份": month,
                        "数据类型": "销量_万辆", "产业链": "新能源汽车产业链",
                        "数值": float(val),
                    })
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        print(f"  [SKIP] CPCA销量: {e}")

    # 尝试获取分能源类型产销
    try:
        fuel_df = ak.car_market_fuel_cpca()
        print(f"  CPCA燃料类型列名: {list(fuel_df.columns)}")
        for _, row in fuel_df.iterrows():
            for col in fuel_df.columns[1:]:
                try:
                    rows_list.append({
                        "年份": str(row.get("年份", "")),
                        "月份": str(row.get("月份", row.iloc[0])),
                        "数据类型": f"销量_{col}",
                        "产业链": "新能源汽车产业链",
                        "数值": float(row[col]),
                    })
                except (ValueError, TypeError, KeyError):
                    pass
    except Exception as e:
        print(f"  [SKIP] CPCA燃料: {e}")

    # 从AKShare获取新能源汽车产量（工业增加值代理：集成电路/汽车）
    # macro_china_industrial_production_yoy 仅为整体YoY，尝试获取
    try:
        indprod_df = ak.macro_china_industrial_production_yoy()
        print(f"  工业生产YoY列名: {list(indprod_df.columns)}")
        id_col = indprod_df.columns[0]
        val_col = next((c for c in indprod_df.columns if "工业" in c or "增加值" in c or "today" in c.lower()), indprod_df.columns[1])
        for _, row in indprod_df.iterrows():
            try:
                rows_list.append({
                    "年份": str(row[id_col])[:4],
                    "月份": str(row[id_col])[5:7] + "月",
                    "数据类型": f"规上工业增加值YoY_%",
                    "产业链": "ALL",
                    "数值": float(row[val_col]),
                })
            except (ValueError, TypeError):
                pass
    except Exception as e:
        print(f"  [SKIP] 工业生产YoY: {e}")

    if not rows_list:
        print("  [SKIP] 无产销数据")
        return pd.DataFrame()

    df = pd.DataFrame(rows_list)
    out = os.path.join(OUTDIR, "production_sales.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"  [OK] 输出 {len(df)} 行 → {out}")
    return df


# ════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("供需匹配指标构建")
    print(f"输出目录: {OUTDIR}")
    print("=" * 60)

    df_ps  = build_price_scissors()
    df_pmi = fetch_pmi_detail()
    df_cap = build_capacity_util()
    df_prd = build_production_sales()

    print("\n" + "=" * 60)
    print("输出汇总：")
    for name, df in [
        ("price_scissors.csv",   df_ps),
        ("pmi_detail.csv",       df_pmi),
        ("capacity_util.csv",    df_cap),
        ("production_sales.csv", df_prd),
    ]:
        rows = len(df) if df is not None and len(df) > 0 else 0
        print(f"  {name}: {rows} 行")


if __name__ == "__main__":
    main()
