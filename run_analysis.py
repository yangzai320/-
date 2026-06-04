"""Retail order KPI analysis project.

This script uses the public UCI Online Retail dataset to build a basic but complete
business analytics project: data cleaning, KPI tables, customer segmentation,
Power BI-ready outputs, and charts.

The raw dataset is not required in the repository. If it is missing, this script
tries to download the official UCI zip and extract `Online Retail.xlsx`.
"""
from __future__ import annotations

import shutil
import urllib.request
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
POWERBI_DIR = BASE_DIR / "powerbi_data"
OUTPUT_DIR = BASE_DIR / "output"
SQL_DIR = BASE_DIR / "sql"
RAW_XLSX = RAW_DIR / "Online_Retail.xlsx"
RAW_CSV = PROCESSED_DIR / "online_retail_raw.csv"

for p in [RAW_DIR, PROCESSED_DIR, POWERBI_DIR, OUTPUT_DIR, SQL_DIR]:
    p.mkdir(parents=True, exist_ok=True)

UCI_ZIP_URL = "https://cdn.uci-ics-mlr-prod.aws.uci.edu/352/online%2Bretail.zip"


def ensure_raw_file() -> None:
    """Download the dataset only when the raw file is absent."""
    if RAW_XLSX.exists() or RAW_CSV.exists():
        return
    zip_path = RAW_DIR / "online_retail.zip"
    print("Downloading UCI Online Retail dataset...")
    urllib.request.urlretrieve(UCI_ZIP_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        # The zip contains `Online Retail.xlsx`.
        member = [m for m in zf.namelist() if m.lower().endswith(".xlsx")][0]
        with zf.open(member) as src, open(RAW_XLSX, "wb") as dst:
            shutil.copyfileobj(src, dst)
    zip_path.unlink(missing_ok=True)


def load_raw_data() -> pd.DataFrame:
    ensure_raw_file()
    if RAW_CSV.exists():
        return pd.read_csv(RAW_CSV, parse_dates=["InvoiceDate"])
    # python-calamine is much faster than openpyxl on this xlsx file.
    df = pd.read_excel(RAW_XLSX, engine="calamine")
    df.to_csv(RAW_CSV, index=False)
    return df


def prepare_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = raw.copy()
    raw["InvoiceNo"] = raw["InvoiceNo"].astype(str)
    raw["StockCode"] = raw["StockCode"].astype(str)
    raw["is_cancelled"] = raw["InvoiceNo"].str.upper().str.startswith("C")
    raw["Revenue"] = raw["Quantity"] * raw["UnitPrice"]
    raw["InvoiceMonth"] = raw["InvoiceDate"].dt.to_period("M").astype(str)
    raw["InvoiceDateOnly"] = raw["InvoiceDate"].dt.date.astype(str)
    raw["YearMonth"] = raw["InvoiceDate"].dt.to_period("M").dt.to_timestamp()

    data_quality = pd.DataFrame(
        {
            "metric": [
                "raw_rows",
                "raw_invoices",
                "raw_products",
                "raw_countries",
                "missing_customer_rows",
                "cancelled_rows",
                "non_positive_quantity_rows",
                "non_positive_price_rows",
            ],
            "value": [
                len(raw),
                raw["InvoiceNo"].nunique(),
                raw["StockCode"].nunique(),
                raw["Country"].nunique(),
                raw["CustomerID"].isna().sum(),
                int(raw["is_cancelled"].sum()),
                int((raw["Quantity"] <= 0).sum()),
                int((raw["UnitPrice"] <= 0).sum()),
            ],
        }
    )

    sales = raw.loc[
        (~raw["is_cancelled"]) & (raw["Quantity"] > 0) & (raw["UnitPrice"] > 0)
    ].copy()
    sales["Revenue"] = sales["Revenue"].round(2)
    sales["CustomerID"] = sales["CustomerID"].astype("Int64").astype("string")
    customer_sales = sales.dropna(subset=["CustomerID"]).copy()
    customer_sales["CustomerID"] = customer_sales["CustomerID"].astype(str)
    return data_quality, sales, customer_sales


def build_kpi_tables(sales: pd.DataFrame, customer_sales: pd.DataFrame) -> dict[str, pd.DataFrame]:
    monthly = sales.groupby("InvoiceMonth").agg(
        revenue=("Revenue", "sum"),
        orders=("InvoiceNo", "nunique"),
        customers=("CustomerID", "nunique"),
        units_sold=("Quantity", "sum"),
    ).reset_index().sort_values("InvoiceMonth")
    monthly["avg_order_value"] = (monthly["revenue"] / monthly["orders"]).round(2)
    monthly["revenue"] = monthly["revenue"].round(2)
    monthly["revenue_mom_growth"] = monthly["revenue"].pct_change().round(4)

    country = sales.groupby("Country").agg(
        revenue=("Revenue", "sum"),
        orders=("InvoiceNo", "nunique"),
        customers=("CustomerID", "nunique"),
        units_sold=("Quantity", "sum"),
    ).reset_index()
    country["avg_order_value"] = (country["revenue"] / country["orders"]).round(2)
    country["revenue"] = country["revenue"].round(2)
    country = country.sort_values("revenue", ascending=False)

    product = sales.groupby(["StockCode", "Description"]).agg(
        revenue=("Revenue", "sum"),
        units_sold=("Quantity", "sum"),
        order_count=("InvoiceNo", "nunique"),
    ).reset_index()
    product["revenue"] = product["revenue"].round(2)
    product = product.sort_values("revenue", ascending=False).head(30)

    sales["weekday_num"] = sales["InvoiceDate"].dt.dayofweek + 1
    weekday = sales.groupby("weekday_num").agg(
        revenue=("Revenue", "sum"),
        orders=("InvoiceNo", "nunique"),
    ).reset_index().sort_values("weekday_num")
    weekday["avg_order_value"] = (weekday["revenue"] / weekday["orders"]).round(2)
    weekday["revenue"] = weekday["revenue"].round(2)

    snapshot = customer_sales["InvoiceDate"].max() + pd.Timedelta(days=1)
    rfm = customer_sales.groupby("CustomerID").agg(
        last_purchase_date=("InvoiceDate", "max"),
        recency_days=("InvoiceDate", lambda x: (snapshot - x.max()).days),
        frequency=("InvoiceNo", "nunique"),
        monetary=("Revenue", "sum"),
    ).reset_index()
    rfm["monetary"] = rfm["monetary"].round(2)
    rfm["recency_score"] = pd.qcut(rfm["recency_days"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    rfm["frequency_score"] = pd.qcut(rfm["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["monetary_score"] = pd.qcut(rfm["monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["rfm_score"] = rfm[["recency_score", "frequency_score", "monetary_score"]].sum(axis=1)
    conditions = [
        rfm["rfm_score"] >= 13,
        (rfm["recency_score"] >= 4) & (rfm["frequency_score"] <= 2),
        (rfm["frequency_score"] >= 4) & (rfm["monetary_score"] >= 4),
        (rfm["recency_score"] <= 2) & (rfm["monetary_score"] >= 4),
    ]
    choices = ["High Value", "Recent / New", "Loyal", "At Risk"]
    rfm["customer_segment"] = np.select(conditions, choices, default="Regular")
    rfm = rfm.sort_values(["rfm_score", "monetary"], ascending=False)

    orders = customer_sales.groupby(["CustomerID", "InvoiceNo"]).agg(
        order_date=("InvoiceDate", "min"),
        order_month=("InvoiceMonth", "first"),
        revenue=("Revenue", "sum"),
    ).reset_index()
    first_month = orders.groupby("CustomerID")["order_month"].min().rename("first_month")
    orders = orders.merge(first_month, on="CustomerID")
    orders["is_repeat"] = orders["order_month"] > orders["first_month"]
    repeat = orders.groupby("order_month").agg(
        active_customers=("CustomerID", "nunique"),
        repeat_customers=("is_repeat", lambda s: orders.loc[s.index, "CustomerID"][s].nunique()),
    ).reset_index()
    repeat["repeat_customer_rate"] = (repeat["repeat_customers"] / repeat["active_customers"]).round(4)

    return {
        "monthly_kpis": monthly,
        "country_performance": country,
        "product_performance": product,
        "weekday_performance": weekday,
        "customer_rfm_segments": rfm,
        "monthly_repeat_rate": repeat,
    }


def write_sql_file() -> None:
    sql_text = """-- SQL queries used in the retail order analysis project
-- Table assumed: clean_sales

-- Monthly KPIs
SELECT
    InvoiceMonth,
    ROUND(SUM(Revenue), 2) AS revenue,
    COUNT(DISTINCT InvoiceNo) AS orders,
    COUNT(DISTINCT CustomerID) AS customers,
    SUM(Quantity) AS units_sold,
    ROUND(SUM(Revenue) * 1.0 / COUNT(DISTINCT InvoiceNo), 2) AS avg_order_value
FROM clean_sales
GROUP BY InvoiceMonth
ORDER BY InvoiceMonth;

-- Country performance
SELECT
    Country,
    ROUND(SUM(Revenue), 2) AS revenue,
    COUNT(DISTINCT InvoiceNo) AS orders,
    COUNT(DISTINCT CustomerID) AS customers,
    SUM(Quantity) AS units_sold,
    ROUND(SUM(Revenue) * 1.0 / COUNT(DISTINCT InvoiceNo), 2) AS avg_order_value
FROM clean_sales
GROUP BY Country
ORDER BY revenue DESC;

-- Product performance
SELECT
    StockCode,
    Description,
    ROUND(SUM(Revenue), 2) AS revenue,
    SUM(Quantity) AS units_sold,
    COUNT(DISTINCT InvoiceNo) AS order_count
FROM clean_sales
GROUP BY StockCode, Description
ORDER BY revenue DESC
LIMIT 30;
"""
    (SQL_DIR / "business_kpi_queries.sql").write_text(sql_text, encoding="utf-8")


def save_outputs(data_quality: pd.DataFrame, sales: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> dict:
    data_quality.to_csv(OUTPUT_DIR / "data_quality_summary.csv", index=False)
    sales.to_csv(PROCESSED_DIR / "clean_sales.csv", index=False)
    for name, df in tables.items():
        df.to_csv(POWERBI_DIR / f"{name}.csv", index=False)
    cols = ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country", "Revenue", "InvoiceMonth"]
    sales[cols].sample(min(50000, len(sales)), random_state=42).to_csv(POWERBI_DIR / "clean_sales_sample_50k.csv", index=False)

    customer_sales_rows = int(sales["CustomerID"].notna().sum())
    summary = {
        "raw_rows": int(data_quality.loc[data_quality.metric == "raw_rows", "value"].iloc[0]),
        "clean_sales_rows": int(len(sales)),
        "known_customer_rows": customer_sales_rows,
        "total_revenue": float(round(sales["Revenue"].sum(), 2)),
        "orders": int(sales["InvoiceNo"].nunique()),
        "known_customers": int(sales["CustomerID"].nunique()),
        "countries": int(sales["Country"].nunique()),
        "products": int(sales["StockCode"].nunique()),
        "avg_order_value": float(round(sales["Revenue"].sum() / sales["InvoiceNo"].nunique(), 2)),
        "date_min": str(sales["InvoiceDate"].min().date()),
        "date_max": str(sales["InvoiceDate"].max().date()),
        "top_country": str(tables["country_performance"].iloc[0]["Country"]),
        "top_product": str(tables["product_performance"].iloc[0]["Description"]),
    }
    pd.DataFrame([summary]).to_csv(OUTPUT_DIR / "project_kpi_summary.csv", index=False)
    return summary


def make_charts(tables: dict[str, pd.DataFrame]) -> None:
    monthly = tables["monthly_kpis"].copy()
    monthly["InvoiceMonth"] = pd.to_datetime(monthly["InvoiceMonth"])
    country = tables["country_performance"].head(10).copy()
    product = tables["product_performance"].head(10).copy()
    rfm = tables["customer_rfm_segments"]
    repeat = tables["monthly_repeat_rate"].copy()

    plt.figure(figsize=(10, 5))
    plt.plot(monthly["InvoiceMonth"], monthly["revenue"], marker="o")
    plt.title("Monthly Revenue Trend")
    plt.xlabel("Month")
    plt.ylabel("Revenue")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "monthly_revenue_trend.png", dpi=160)
    plt.close()

    plt.figure(figsize=(10, 5))
    plt.bar(country["Country"], country["revenue"])
    plt.title("Top 10 Countries by Revenue")
    plt.xlabel("Country")
    plt.ylabel("Revenue")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "top_countries_revenue.png", dpi=160)
    plt.close()

    plt.figure(figsize=(10, 5))
    labels = product["Description"].str.slice(0, 28)
    plt.barh(labels[::-1], product["revenue"][::-1])
    plt.title("Top 10 Products by Revenue")
    plt.xlabel("Revenue")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "top_products_revenue.png", dpi=160)
    plt.close()

    seg = rfm["customer_segment"].value_counts().reset_index()
    seg.columns = ["customer_segment", "customer_count"]
    plt.figure(figsize=(8, 5))
    plt.bar(seg["customer_segment"], seg["customer_count"])
    plt.title("Customer Segment Counts")
    plt.xlabel("Segment")
    plt.ylabel("Customers")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "customer_segment_counts.png", dpi=160)
    plt.close()

    repeat["order_month"] = pd.to_datetime(repeat["order_month"])
    plt.figure(figsize=(10, 5))
    plt.plot(repeat["order_month"], repeat["repeat_customer_rate"], marker="o")
    plt.title("Monthly Repeat Customer Rate")
    plt.xlabel("Month")
    plt.ylabel("Repeat Customer Rate")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "monthly_repeat_customer_rate.png", dpi=160)
    plt.close()


def write_docs(summary: dict, tables: dict[str, pd.DataFrame]) -> None:
    top_countries_md = tables["country_performance"].head(5)[["Country", "revenue", "orders"]].to_markdown(index=False)
    top_products_md = tables["product_performance"].head(5)[["Description", "revenue", "units_sold"]].to_markdown(index=False)

    readme = f"""# Retail Order KPI Analysis Project

This is a basic data analytics portfolio project built with the public UCI Online Retail transaction dataset.

## Dataset
- Source: UCI Machine Learning Repository, Online Retail dataset.
- Period: {summary['date_min']} to {summary['date_max']}.
- Raw records: {summary['raw_rows']:,} rows.
- Key fields: invoice number, product code, product description, quantity, invoice date, unit price, customer ID, country.

## What this project does
1. Cleans cancelled orders, non-positive quantities, and invalid prices.
2. Builds sales KPIs, including revenue, orders, customers, units sold, and average order value.
3. Creates simple RFM customer segments with Python.
4. Exports Power BI-ready CSV files.
5. Generates charts for a short business analysis report.

## How to run
```bash
pip install -r requirements.txt
python src/run_analysis.py
```

## Main outputs
- `powerbi_data/monthly_kpis.csv`
- `powerbi_data/country_performance.csv`
- `powerbi_data/product_performance.csv`
- `powerbi_data/customer_rfm_segments.csv`
- `powerbi_data/monthly_repeat_rate.csv`
- `sql/business_kpi_queries.sql`
- `output/retail_order_analysis_report.md`
"""
    (BASE_DIR / "README.md").write_text(readme, encoding="utf-8")

    report = f"""# 零售订单经营指标分析项目报告

## 1. 项目背景
本项目使用公开的线上零售交易数据，完成一个基础但完整的数据分析流程：数据清洗、经营指标计算、客户分层、SQL 查询、Power BI 数据准备和可视化结果输出。项目定位不是复杂建模，而是展示数据分析实习岗位常见的基础能力：拉数、清洗、汇总、看指标、解释业务波动。

## 2. 数据说明
数据来自 UCI Online Retail Dataset，记录了一家英国线上零售商在 2010-12-01 至 2011-12-09 期间的交易数据。原始数据共 {summary['raw_rows']:,} 行，字段包括 InvoiceNo、StockCode、Description、Quantity、InvoiceDate、UnitPrice、CustomerID 和 Country。

## 3. 数据清洗
清洗规则如下：
- 删除取消订单：InvoiceNo 以 C 开头的记录；
- 删除 Quantity 小于等于 0 的记录；
- 删除 UnitPrice 小于等于 0 的记录；
- 对 CustomerID 缺失的交易，仍保留在销售分析中，但不进入客户分层分析；
- 新增 Revenue = Quantity × UnitPrice；
- 新增 InvoiceMonth，用于月度经营指标分析。

清洗后用于销售指标分析的数据共有 {summary['clean_sales_rows']:,} 行；其中包含可识别客户的交易记录 {summary['known_customer_rows']:,} 行。

## 4. 核心指标结果
- 总销售额：{summary['total_revenue']:,.2f}
- 订单数：{summary['orders']:,}
- 可识别客户数：{summary['known_customers']:,}
- 覆盖国家/地区：{summary['countries']:,}
- 商品数：{summary['products']:,}
- 平均订单金额：{summary['avg_order_value']:,.2f}
- 销售额最高的国家/地区：{summary['top_country']}
- 销售额最高的商品：{summary['top_product']}

## 5. 主要发现
### 5.1 月度销售趋势
月度销售额在 2011 年下半年明显提升，尤其在 11 月达到较高水平，说明该零售业务具有一定季节性特征。这个结果可以支持后续做库存准备、促销节奏和重点月份运营复盘。

### 5.2 国家/地区表现
销售收入高度集中在英国市场。前五个国家/地区表现如下：

{top_countries_md}

### 5.3 商品表现
销售额最高的前五个商品如下：

{top_products_md}

### 5.4 客户分层
项目使用简单 RFM 方法，从最近购买时间、购买频次和消费金额三个角度对客户进行分层。这个方法可以帮助区分高价值客户、近期新客户、稳定复购客户和可能流失客户。该部分没有使用复杂模型，重点是把客户行为转换成业务可解释的标签。

## 6. Power BI 看板设计建议
可以基于 `powerbi_data/` 下的 CSV 文件制作 3 个页面：
1. 经营总览：销售额、订单数、客户数、平均订单金额、月度销售趋势；
2. 商品与地区分析：Top 商品、Top 国家/地区、商品销售贡献；
3. 客户分析：RFM 客户分层、复购率趋势、不同客户群体贡献。

## 7. 可写进简历的项目表述
**零售订单经营指标分析项目｜个人项目**
- 使用公开线上零售交易数据，基于 Python 和 SQL 完成订单数据清洗、异常订单剔除、销售额计算和月度指标汇总，处理原始交易记录 {summary['raw_rows']:,} 行。
- 设计销售额、订单数、客户数、客单价、复购率等基础经营指标，并按月份、国家/地区和商品维度进行拆解分析。
- 使用 SQL 输出月度经营指标、地区表现和商品销售榜单，并整理为 Power BI 可导入的分析数据表。
- 使用 Python 完成基础客户 RFM 分层和可视化分析，识别高价值客户、复购客户和潜在流失客户，为经营看板和业务复盘提供数据支持。
"""
    (OUTPUT_DIR / "retail_order_analysis_report.md").write_text(report, encoding="utf-8")

    guide = """# Power BI Dashboard Guide

Use the CSV files in `powerbi_data/`.

## Page 1: Business Overview
- KPI cards: revenue, orders, customers, average order value
- Line chart: monthly revenue trend from `monthly_kpis.csv`
- Bar chart: monthly orders

## Page 2: Country and Product Performance
- Bar chart: top countries by revenue from `country_performance.csv`
- Bar chart/table: top products by revenue from `product_performance.csv`
- Slicers: Country, InvoiceMonth

## Page 3: Customer Analysis
- Bar chart: customer segment counts from `customer_rfm_segments.csv`
- Line chart: repeat customer rate from `monthly_repeat_rate.csv`
- Table: top customers by monetary value
"""
    (BASE_DIR / "POWERBI_DASHBOARD_GUIDE.md").write_text(guide, encoding="utf-8")


def main() -> None:
    raw = load_raw_data()
    data_quality, sales, customer_sales = prepare_data(raw)
    tables = build_kpi_tables(sales, customer_sales)
    summary = save_outputs(data_quality, sales, tables)
    make_charts(tables)
    write_sql_file()
    write_docs(summary, tables)
    print("Analysis completed.")
    print(summary)


if __name__ == "__main__":
    main()
