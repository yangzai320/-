-- SQL queries used in the retail order analysis project

-- monthly_kpis
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

-- country_performance
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

-- product_performance
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

-- weekday_performance
SELECT
                    strftime('%w', InvoiceDate) AS weekday_num,
                    ROUND(SUM(Revenue), 2) AS revenue,
                    COUNT(DISTINCT InvoiceNo) AS orders,
                    ROUND(SUM(Revenue) * 1.0 / COUNT(DISTINCT InvoiceNo), 2) AS avg_order_value
                FROM clean_sales
                GROUP BY weekday_num
                ORDER BY weekday_num;

