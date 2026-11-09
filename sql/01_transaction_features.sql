-- DuckDB: purchases_raw 由运行入口绑定到原始交易文件。
-- 金额版本冲突必须先通过审计，不得用 MAX 隐藏不一致。
CREATE OR REPLACE TEMP TABLE transaction_audit AS
    SELECT
        client_id,
        transaction_id,

        COUNT(*) AS detail_rows,
        COUNT(DISTINCT transaction_datetime) AS time_versions,
        COUNT(DISTINCT store_id) AS store_versions,
        COUNT(DISTINCT purchase_sum) AS amount_versions,

        COUNT(*) FILTER (
            WHERE purchase_sum IS NULL
        ) AS missing_amount_rows,

        MIN(purchase_sum) AS min_amount,
        MAX(purchase_sum) AS max_amount

    FROM purchases_raw
    GROUP BY client_id, transaction_id;

CREATE OR REPLACE TEMP TABLE transactions AS
    SELECT
        client_id,
        transaction_id,

        MIN(transaction_datetime) AS transaction_datetime,
        MAX(store_id) AS store_id,
        MAX(purchase_sum) AS transaction_amount,

        COUNT(*) AS detail_rows,

        COUNT(*) FILTER (
            WHERE transaction_datetime IS NULL
        ) AS missing_time_rows,

        COUNT(*) FILTER (
            WHERE store_id IS NULL
        ) AS missing_store_rows

    FROM purchases_raw
    GROUP BY client_id, transaction_id;

CREATE OR REPLACE TEMP TABLE customer_rfm AS

    WITH params AS (
        SELECT
            TIMESTAMP '2019-03-19 00:00:00' AS feature_cutoff
    )

    SELECT
        t.client_id,
        p.feature_cutoff,

        DATE_DIFF(
            'day',
            CAST(MAX(t.transaction_datetime) AS DATE),
            CAST(p.feature_cutoff AS DATE)
        ) AS recency_days,

        COUNT(*) AS txn_count_history,

        SUM(t.transaction_amount ORDER BY t.transaction_id) AS spend_history,

        AVG(t.transaction_amount ORDER BY t.transaction_id) AS avg_transaction_amount,

        COUNT(*) FILTER (
            WHERE t.transaction_datetime
                >= p.feature_cutoff - INTERVAL '30 days'
        ) AS txn_count_30d,

        COALESCE(
            SUM(t.transaction_amount ORDER BY t.transaction_id) FILTER (
                WHERE t.transaction_datetime
                    >= p.feature_cutoff - INTERVAL '30 days'
            ),
            0
        ) AS spend_30d,

        COUNT(*) FILTER (
            WHERE t.transaction_amount = 0
        ) AS zero_amount_txn_count

    FROM transactions AS t
    CROSS JOIN params AS p

    WHERE t.transaction_datetime < p.feature_cutoff

    GROUP BY t.client_id, p.feature_cutoff;
