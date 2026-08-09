# 结果总账

| 编号 | 结果/结论 | 数值或文件 | 来源代码 | 验证状态 | 论文位置 |
|---|---|---|---|---|---|
| Q1-R01 | 附件1的 42 条温度--响应低阶候选拟合与冻结推荐描述 | `outputs/q1/tables/q1_model_comparison.csv`、`q1_recommended_models.csv` | `src/q1/reproduce_q1.py` | 交接单附录 A/B 数值核验通过 | `06_problem1.tex`、附录 A |
| Q1-R02 | 附件2的 7 个时刻收率与相邻转化率变化率 | `outputs/q1/tables/q1_time_stability.csv` | `src/q1/reproduce_q1.py` | 交接单表 9 数值核验通过 | `06_problem1.tex` |
| Q1-R03 | 附件2转化率的冻结经验趋势 | $X_{\mathrm{EtOH}}(t)=42.6709-0.05276t$，$R^2=0.9329$，LOOCV RMSE$=2.025$ 百分点 | `src/q1/reproduce_q1.py` | 交接单主文数值核验通过 | `06_problem1.tex` |
| Q1-R04 | 附件1和附件2的三张冻结图 | `paper/figures/q1_handoff/` | 交接单嵌入图片原样提取 | SHA-256 已记录于模型卡；视觉内容已核对 | 附录 A |
