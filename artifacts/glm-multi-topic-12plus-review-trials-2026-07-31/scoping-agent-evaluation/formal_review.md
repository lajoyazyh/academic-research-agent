# LLM Agent 能力评价与基准评估现状

## 摘要
随着大语言模型（LLM）从文本生成向可调用工具并执行多步任务的智能体演进，评价范围扩展到规划、工具使用、记忆、协作与长期任务。本文映射了现有评价体系及其局限。纳入语料显示，基准在任务设计、指标选择、可复现性和有效性风险方面存在差异，且长期记忆、多 Agent 协作与真实动态环境仍缺少充分评估[P2][P9][P12]。

## 引言
LLM Agent 的评价通常围绕规划、记忆、工具使用和协作能力展开。现有研究将 CoT 用作任务分解手段，同时指出复杂多步任务往往需要外部规划或工具机制补充模型内在推理[P3][P10]。工具使用评价关注调用时机、工具选择和参数执行[P8][P10]。针对长期任务，现有基准开始探索多轮交互和动态环境，但相当一部分评测仍偏向较短任务轨迹[P9][P12]。

## 方法
【方法记录】本轮通过 OpenAlex 执行三条预设主题查询，形成43条候选记录；经标题/摘要高召回排序和开放全文可得性验证，取得12条可解析全文记录。事后版本审计发现 [P4] 与 [P5] 是同一综述的期刊版和预印本，因此独立研究数为11；正文解释不把二者视为两份独立证据。候选发现聚焦 LLM Agent 架构、能力评估框架和基准测试；检索式与命中数保存在检索账本中。该流程用于范围映射验证，不是穷尽性系统综述。筛选遵循以下原则：
1.  **主题相关性**：仅保留直接讨论 LLM 智能体评价、基准测试或评估方法的文献。
2.  **来源类型**：优先选择综述类文献以获取领域全景，辅以具体的基准测试论文作为实证支撑。
3.  **证据强度**：优先引用证据强度为“高”或“中”的来源，并严格依据证据卡中的内容进行引用。

【方法记录】
-   **检索策略**：【方法记录】使用三条预设英文查询覆盖 Agent 总体评测、规划/工具使用和长时任务基准，完整检索式见检索账本。
-   **筛选过程**：【方法记录】按研究问题进行标题/摘要高召回排序，并以开放全文可解析作为本轮纳入条件；候选不等同于最终纳入。
-   **纳入来源**：最终保留 [P1]-[P12] 共12条全文记录，对应11项独立研究；[P4] 与 [P5] 为同一综述的关联版本，详见去重审计。

## 结果与证据综合

### 1. 评价维度与核心能力
LLM Agent 的评价通常围绕其核心架构模块展开，包括规划、记忆、工具使用及协作能力。

*   **规划能力**：规划是 Agent 实现长期目标的核心。现有研究指出，LLM 具备内在的推理能力，能够通过 CoT（思维链）进行任务分解 [P3]。然而，在复杂的多步任务中，单纯依赖模型内在推理存在局限性，往往需要引入外部规划工具或机制来增强鲁棒性 [P10]。
*   **记忆系统**：记忆模块分为短期上下文和长期经验存储；Agent 架构综述讨论了混合记忆结构[P4]。RAG 综述则提供了外部知识检索与更新的技术分类，但这些检索指标不能直接替代对长期自主行为的评测[P7]。
*   **工具使用**：工具使用能力是 Agent 赋能现实世界的关键。评价通常关注“何时调用”、“调用哪个工具”以及“如何使用工具”三个维度 [P10]。基准测试如 API-Bank 和 ToolBench 专门针对 API 调用的准确性、检索准确率及参数匹配度进行评估 [P8] [P9]。

### 2. 基准测试与任务设计
为了量化上述能力，学术界提出了多种基准测试，涵盖了从通用任务到特定领域的广泛场景。

*   **通用与多模态基准**：MMLU、MATH 等基准主要评估 LLM 的通用推理能力，这些能力是 Agent 进行规划的基础 [P1] [P2]。对于多模态 Agent，评估需关注其在视觉或音频输入下的工具调用能力 [P10]。
*   **工具使用专项基准**：API-Bank 构建了包含 73 个真实 API 的基准，评估模型从“调用”到“规划+检索+调用”的进阶能力 [P8]。研究发现，即使是 GPT-3.5，在 API 检索和规划方面的能力也显著弱于调用能力，且主要错误类型集中在检索失败而非参数错误 [P8]。
*   **长期与复杂任务基准**：针对长期任务，现有基准如 AgentDojo、FlowBench 等开始探索多轮交互和动态环境下的评估 [P9]。然而，大多数基准仍侧重于单次交互或短周期任务，难以捕捉 Agent 在长时间运行中的性能漂移或累积效应 [P9]。

### 3. 评价指标与评估方法
评价指标的选择直接影响评估的有效性，主要分为客观指标和主观指标。

*   **客观指标**：包括任务成功率、执行准确率、工具调用准确率（如 MRR, NDCG）以及 Pass@k（一致性评估） [P9]。这些指标易于自动化，但往往难以评估 Agent 的输出质量或推理过程。
*   **主观指标**：包括人类反馈、用户满意度及 Turing Test [P5] [P6]。在社交模拟或心理咨询等场景中，主观评价对于衡量 Agent 的“拟人化”程度至关重要 [P4] [P11]。
*   **LLM-as-a-Judge**：为了解决主观评价的成本问题，研究者开始使用更强的 LLM 作为裁判来评估 Agent 的行为 [P9]。然而，这种方法引入了新的复杂性，且可能受到“Hyper-accuracy distortion”（过度精确化偏差）的影响 [P4] [P5]。

### 4. 可复现性与有效性风险
尽管基准测试层出不穷，但在可复现性和有效性方面仍面临严峻挑战。

*   **可复现性问题**：许多基准测试缺乏开源代码或详细的数据集描述，导致结果难以复现 [P3] [P5]。此外，LLM 的随机性使得在相同任务上多次运行可能产生不同结果，增加了评估的不确定性 [P9]。
*   **有效性风险**：
    *   **数据偏差与过拟合**：基准测试数据集可能包含训练数据，导致模型通过记忆而非推理获得高分 [P2]。
    *   **环境封闭性**：现有基准多在封闭环境中运行，缺乏对真实世界复杂性和动态性的考量 [P6]。
    *   **评估指标局限**：单一的准确率指标可能掩盖 Agent 在安全性、公平性或长期一致性方面的缺陷 [P9]。

## 讨论与局限
尽管现有研究在 LLM Agent 评价方面取得了进展，但仍存在以下局限：

1.  **评估维度的片面性**：目前的基准测试多侧重于任务完成度或工具调用准确率，对于 Agent 在复杂社会交互中的“拟人化”程度、价值观一致性以及长期记忆管理的有效性评估仍显不足 [P6] [P9]。
2.  **环境封闭性与动态性缺失**：大多数基准测试在封闭的、静态的环境中运行，难以模拟真实世界中动态变化的环境和不可预测的用户行为，这可能导致评估结果与实际应用场景存在偏差 [P6] [P12]。
3.  **评估方法的复杂性**：随着 LLM-as-a-Judge 等方法的普及，评估过程本身变得复杂且主观，且可能受到模型自身“过度精确化”偏差的影响，从而影响评估结果的客观性 [P4] [P5] [P9]。

## 结论
LLM Agent 的评价正处于从单一任务测试向多维度、长周期评估过渡的阶段。虽然现有的基准测试在工具使用和通用推理方面取得了显著进展，但在长期记忆管理、多 Agent 协作以及真实世界动态环境下的评估仍存在不足。未来的研究需要开发更具鲁棒性、可复现性且能反映真实复杂场景的评估框架。

## 参考来源

- [P1] Humza Naveed, Asad Ullah Khan, Shi Qiu, Muhammad Saqib, Saeed Anwar, Muhammad Usman, Akhtar, Naveed, Nick Barnes, Ajmal Mian. A Comprehensive Overview of Large Language Models. 2023. https://arxiv.org/abs/2307.06435
- [P2] Yupeng Chang, Xu Wang, Jindong Wang, Yuan-Hsuan Wu, Linyi Yang, Kaijie Zhu, Hao Chen, Xiaoyuan Yi, Cunxiang Wang, Yidong Wang, Wei Ye, Yue Zhang, Yi Chang, Philip S. Yu, Qiang Yang, Xing Xie. A Survey on Evaluation of Large Language Models. 2023. https://arxiv.org/abs/2307.03109
- [P3] Wayne Xin Zhao, Kun Zhou, Junyi Li, Tianyi Tang, Zican Dong, Yupeng Hou, Beichen Zhang, Yingqian Min, Junjie Zhang, Peiyu Liu, Xiaolei Wang, Yifan Du, Yushuo Chen, Yushuo Chen, Zhipeng Chen, Jinhao Jiang, Ruiyang Ren, Yifan Li, Xinyu Tang, Peiyu Liu, Yiwen Hu, Jian‐Yun Nie, Ji-Rong Wen. A Survey of Large Language Models. 2026. https://arxiv.org/abs/2303.18223
- [P4] Lei Wang, Chen Ma, Xueyang Feng, Zeyu Zhang, Hao Yang, Jingsen Zhang, Zhiyuan Chen, Jiakai Tang, Xu Chen, Yankai Lin, Wayne Xin Zhao, Zhewei Wei, Ji-Rong Wen. A survey on large language model based autonomous agents. 2024. https://doi.org/10.1007/s11704-024-40231-1
- [P5] Lei Wang, Chen Ma, Xueyang Feng, Zeyu Zhang, Hao Yang, Jingsen Zhang, Zhiyuan Chen, Jiakai Tang, Xu Chen, Yankai Lin, Wayne Xin Zhao, Zhewei Wei, Ji-Rong Wen. A Survey on Large Language Model based Autonomous Agents. 2023. https://arxiv.org/abs/2308.11432
- [P6] Zhiheng Xi, Wen-Xiang Chen, Xin Guo, Wei He, Yiwen Ding, Boyang Hong, Ming Zhang, Junzhe Wang, Senjie Jin, Enyu Zhou, Rui Zheng, Xiaoran Fan, Xiao Wang, Limao Xiong, Yuhao Zhou, Weiran Wang, Changhao Jiang, Yicheng Zou, Xiangyang Liu, Zhangyue Yin, Shihan Dou, Rongxiang Weng, Wensen Cheng, Qi Zhang, Wenjuan Qin, Yongyan Zheng, Xipeng Qiu, Huang, Xuanjing, Tao Gui. The Rise and Potential of Large Language Model Based Agents: A Survey. 2023. https://arxiv.org/abs/2309.07864
- [P7] Yunfan Gao, Yun Xiong, Xinyu Gao, Kangxiang Jia, Jinliu Pan, Yuxi Bi, Yi Dai, Jiawei Sun, Wang, Meng, Wang, Haofen. Retrieval-Augmented Generation for Large Language Models: A Survey. 2023. https://arxiv.org/abs/2312.10997
- [P8] Minghao Li, Yingxiu Zhao, Bowen Yu, Feifan Song, Hangyu Li, Haiyang Yu, Zhoujun Li, Fei Huang, Yongbin Li. API-Bank: A Comprehensive Benchmark for Tool-Augmented LLMs. 2023. https://doi.org/10.18653/v1/2023.emnlp-main.187
- [P9] Mahmoud Mohammadi, Yipeng Li, Jane C. Lo, Wendy Yip. Evaluation and Benchmarking of LLM Agents: A Survey. 2025. https://arxiv.org/abs/2507.21504
- [P10] Weikai Xu, Chengrui Huang, Shen Gao, Shuo Shang. LLM-Based Agents for Tool Learning: A Survey. 2025. https://doi.org/10.1007/s41019-025-00296-9
- [P11] Chen Gao, Xiaochong Lan, Nian Li, Yuan Yuan, Jingtao Ding, Zhilun Zhou, Fengli Xu, Yong Li. Large language models empowered agent-based modeling and simulation: a survey and perspectives. 2024. https://doi.org/10.1057/s41599-024-03611-3
- [P12] Nikita Mehandru, Brenda Y. Miao, Eduardo Rodriguez Almaraz, Madhumita Sushil, Atul J. Butte, Ahmed M. Alaa. Evaluating large language models as agents in the clinic. 2024. https://doi.org/10.1038/s41746-024-01083-y
