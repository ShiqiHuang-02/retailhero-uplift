-- 输入 scored_customers: split × client_id 一行；模型只在训练集拟合。
-- ROW_NUMBER + client_id 保证同分客户排序稳定。
CREATE OR REPLACE TEMP TABLE ranked_customers AS
SELECT *,
 ROW_NUMBER() OVER (PARTITION BY split ORDER BY uplift_score DESC, client_id) AS uplift_rank,
 ROW_NUMBER() OVER (PARTITION BY split ORDER BY response_score DESC, client_id) AS response_rank,
 ROW_NUMBER() OVER (PARTITION BY split ORDER BY p1 DESC, client_id) AS response_p1_rank,
 ROW_NUMBER() OVER (PARTITION BY split ORDER BY rfm_score DESC, client_id) AS rfm_rank,
 COUNT(*) OVER (PARTITION BY split) AS candidate_count
FROM scored_customers;

-- Random 是同名额随机策略的期望选择概率，不是一次随机抽样。
CREATE OR REPLACE TEMP TABLE policy_assignments AS
SELECT r.*, s.strategy,
 CASE s.strategy
 WHEN 'Random' THEN ROUND(candidate_count * 0.2) / candidate_count
 WHEN 'Uplift' THEN CAST(uplift_rank <= ROUND(candidate_count * 0.2) AS DOUBLE)
 WHEN 'Response' THEN CAST(response_rank <= ROUND(candidate_count * 0.2) AS DOUBLE)
 WHEN 'Response_p1' THEN CAST(response_p1_rank <= ROUND(candidate_count * 0.2) AS DOUBLE)
 WHEN 'RFM' THEN CAST(rfm_rank <= ROUND(candidate_count * 0.2) AS DOUBLE)
 END AS selection_weight
FROM ranked_customers r
CROSS JOIN (VALUES ('Random'), ('RFM'), ('Response'), ('Response_p1'), ('Uplift')) s(strategy);

CREATE OR REPLACE TEMP TABLE policy_summary AS
SELECT split, strategy, COUNT(*) AS candidate_count,
 SUM(selection_weight) AS contact_count,
 1000 * AVG(selection_weight) AS contacts_per_1000,
 1000 * AVG(selection_weight * dr_score) AS gain_per_1000,
 1000 * STDDEV_SAMP(selection_weight * dr_score) / SQRT(COUNT(*)) AS se_per_1000,
 1000 * AVG(selection_weight * dr_score) - 1.96 * 1000 * STDDEV_SAMP(selection_weight * dr_score) / SQRT(COUNT(*)) AS ci_low,
 1000 * AVG(selection_weight * dr_score) + 1.96 * 1000 * STDDEV_SAMP(selection_weight * dr_score) / SQRT(COUNT(*)) AS ci_high
FROM policy_assignments GROUP BY split, strategy;

-- 画像是所选人群描述，不是分组因果效应。
CREATE OR REPLACE TEMP TABLE selected_profiles AS
SELECT split, strategy, SUM(selection_weight) AS expected_contacts,
 SUM(selection_weight * recency_days) / SUM(selection_weight) AS mean_recency_days,
 SUM(selection_weight * txn_count_history) / SUM(selection_weight) AS mean_history_transactions,
 SUM(selection_weight * spend_history) / SUM(selection_weight) AS mean_history_spend,
 SUM(selection_weight * response_score) / SUM(selection_weight) AS mean_response_score,
 SUM(selection_weight * uplift_score) / SUM(selection_weight) AS mean_predicted_uplift
FROM policy_assignments GROUP BY split, strategy;

-- 仅对确定性策略计算集合重合度，Random 无固定选人集合。
CREATE OR REPLACE TEMP TABLE policy_overlap AS
SELECT a.split, a.strategy AS strategy_a, b.strategy AS strategy_b,
 SUM(a.selection_weight * b.selection_weight) AS intersection_count,
 SUM(GREATEST(a.selection_weight, b.selection_weight)) AS union_count,
 SUM(a.selection_weight * b.selection_weight) / SUM(GREATEST(a.selection_weight, b.selection_weight)) AS jaccard,
 SUM(a.selection_weight * b.selection_weight) / SUM(a.selection_weight) AS share_of_a
FROM policy_assignments a JOIN policy_assignments b
 ON a.split = b.split AND a.client_id = b.client_id
WHERE a.strategy != 'Random' AND b.strategy != 'Random'
GROUP BY a.split, a.strategy, b.strategy;
