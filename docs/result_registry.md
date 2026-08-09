# 结果总账

| 编号 | 结果/结论 | 数值或文件 | 来源代码 | 验证状态 | 论文位置 |
|---|---|---|---|---|---|
| Q1-R01 | 附件1的 42 条温度--响应低阶候选拟合与冻结推荐描述 | outputs/q1/tables/q1_model_comparison.csv、q1_recommended_models.csv | src/q1/reproduce_q1.py | 交接单附录 A/B 数值核验通过 | 06_problem1.tex、附录 A |
| Q1-R02 | 附件2的 7 个时刻收率与相邻转化率变化率 | outputs/q1/tables/q1_time_stability.csv | src/q1/reproduce_q1.py | 交接单表 9 数值核验通过 | 06_problem1.tex |
| Q1-R03 | 附件2转化率的冻结经验趋势 | \(X_{\mathrm{EtOH}}(t)=42.6709-0.05276t\)，\(R^2=0.9329\)，LOOCV RMSE=2.025 百分点 | src/q1/reproduce_q1.py | 交接单主文数值核验通过 | 06_problem1.tex |
| Q1-R04 | 附件1和附件2的三张冻结图 | paper/figures/q1_handoff/ | 交接单嵌入图片原样提取 | SHA-256 已记录于模型卡；视觉内容已核对 | 附录 A |
| Q2-R01 | 21 组因素解析与 114 条温度记录的完整性检查 | data/processed/q2_attachment1_parsed_records.csv、outputs/q2/tables/q2_factor_parsing.csv | src/q2/reproduce_q2.py | 21 组、114 条、选择性总和与 A11 特殊处理校验通过 | 07_problem2.tex、附录 B |
| Q2-R02 | 温度端点总体效应 | 250→350 ℃时 \(X_{\mathrm{EtOH}}\)、\(S_{\mathrm{C4}}\) 均为 21/21 正增量；均值为 24.46、15.30 个百分点 | src/q2/reproduce_q2.py | 严格核验通过 | 07_problem2.tex |
| Q2-R03 | 13 个严格匹配块、6 类跨背景同对比族、2 个局部四格 | outputs/q2/tables/q2_strict_match_blocks.csv、q2_contrast_family_summary.csv、q2_local_rectangle_interactions.csv | src/q2/reproduce_q2.py | 结构单元测试通过 | 07_problem2.tex、附录 B |
| Q2-R04 | 局部二阶对比与删一温度敏感性 | outputs/q2/tables/q2_leave_one_temperature_sensitivity.csv、outputs/q2/figures/q2_leave_one_temperature_sensitivity.png | src/q2/reproduce_q2.py | 所有删一温度结果保持原平均二阶对比符号 | 07_problem2.tex、附录 B |
