# 问题二代码

reproduce_q2.py 等价实现已确认的“基于温度分层匹配与跨背景效应对比的催化因素影响分析”。它读取附件 1 底层单元格数值，解析 21 组催化剂因素，并输出严格匹配块、六类跨背景同对比族、两个局部四格二阶对比及删一温度敏感性。

运行命令：python src/q2/reproduce_q2.py --strict

输入是 data/raw/q1_attachment1.xlsx；输出位于 data/processed/q2_attachment1_parsed_records.csv 和 outputs/q2/。脚本不使用附件 2，不以 C4 收率为响应，不建立统一回归/黑箱预测模型，也不做全局因素重要性排名。
