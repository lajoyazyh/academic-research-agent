# 参数高效微调方法的机制、证据与工程权衡

## 摘要
随着大语言模型（LLM）规模的指数级增长，全参数微调在计算资源与存储成本上构成了严峻挑战。参数高效微调（PEFT）通过冻结预训练模型的大部分参数，仅更新少量附加参数，从而在保持模型性能的同时大幅降低资源消耗[P1]。本文基于对12篇arXiv论文的系统综述，构建了PEFT方法的技术谱系，涵盖加性微调、重参数化微调、混合微调及基于量化的微调四大类。研究发现，LoRA和Houlsby Adapter是当前性能最稳定的方法，能在极低参数量（<1%）下达到全微调性能[P1][P6]；QLoRA通过量化技术将65B模型的训练内存需求降低至48GB以下，实现了单卡训练的可能性[P5]；AdaMix等混合方法在特定任务（如GLUE）上超越了全微调[P10]。本文进一步分析了不同方法在可训练参数规模、结构改动、任务适用性、训练与推理成本及复现性方面的工程权衡，为PEFT技术的选型与应用提供了实证依据。

## 引言
预训练语言模型（PLMs）的涌现标志着自然语言处理领域的范式转移，然而其巨大的参数规模（数十亿至数千亿）使得全参数微调在计算资源受限的工业界和学术界难以普及。参数高效微调（PEFT）应运而生，其核心目标是在冻结预训练模型主体参数的前提下，通过引入少量可训练参数或修改模型结构，使模型适应下游任务。这一技术谱系经历了从早期的Adapter、Prefix Tuning到当前主流的LoRA及其衍生方法的演进。

本文旨在回答以下核心问题：PEFT方法在可训练参数规模、结构改动程度、任务适用性、性能证据、训练与推理成本以及复现性方面形成了怎样的技术谱系？通过整合12篇代表性研究，本文将深入剖析各类PEFT方法的机制原理、实证性能及工程权衡，以期为PEFT技术的选型与优化提供严谨的参考。

## 方法
本研究遵循技术综述模式，基于预先设定的研究协议进行。真实方法记录仅来源于arXiv预印本平台，候选池经标题摘要筛选后，最终纳入12篇可读取全文的论文进行深度分析。证据提取与综合基于结构化证据卡，采用综合单元组织正文，确保每个论点均有明确的来源支撑。研究质量评价涵盖代码可用性、数据集透明度、方差报告及消融实验设计。

## 结果与证据综合

### 1. PEFT方法的技术谱系与机制分类
根据机制原理，现有PEFT方法可划分为加性微调、重参数化微调、混合微调及基于量化的微调四大类。

**加性微调**通过在模型结构中插入额外模块进行微调，不修改原有权重。其中，**Adapter**在Transformer层间插入小型神经网络模块，其可训练参数比例约为1.2%至2.38%[P1][P2]。虽然结构清晰且易于组合，但Adapter通过增加数据流路径，在推理时引入了显著的延迟开销[P1][P6]。**Prefix Tuning**与**Prompt Tuning**则在输入层或隐藏层前添加可学习的连续向量，其可训练参数极低（<0.5%），结构改动最小[P2][P6]。然而，这类方法在标准全微调基线上收敛较慢且性能不稳定，高度依赖随机种子[P6]。

**重参数化微调**通过冻结原权重，利用低秩分解或结构重参数化添加少量可训练参数，推理时将额外参数融合回原权重。**LoRA**是目前最主流的方法，它将权重矩阵分解为低秩矩阵相乘，可训练参数比例约为0.26%至0.73%[P2]。**GLoRA**进一步结合进化搜索和结构重参数化，在视觉任务（如VTAB-1K）上相比标准LoRA提升了2.9%的平均准确率，且通过结构重参数化在推理阶段不增加额外参数或FLOPs[P9]。

**混合微调**旨在结合多种机制的优点。**AdaMix**提出Mixture-of-Adaptations，在每一层引入多个适配器模块，训练时随机路由，推理时通过权重平均合并。该方法在GLUE基准上平均准确率达到84.5%，超越了全微调的82.7%[P10]。**HETLORA**则针对联邦学习中的异构客户端，允许不同客户端使用不同秩的LoRA，通过自剪枝和稀疏加权聚合，将通信开销降低至全微调的0.004倍[P12]。

**基于量化的微调**通过结合低比特量化技术降低内存占用。**QLoRA**采用4-bit NormalFloat量化、双重量化和分页优化器，将65B模型的训练内存需求从>780GB降低至<48GB，使得单卡训练成为可能[P5]。

### 2. 可训练参数与结构改动
PEFT方法在可训练参数规模上存在显著差异，这直接影响了其结构改动程度和部署成本。
BitFit仅微调偏置项，可训练参数比例仅为0.003%，效率最高[P1]。LoRA和Adapter作为中间代表，参数量分别约为0.38%和2.38%[P1]。Prompt Tuning的参数量最低，但在某些设置下（如T5XXL）其可训练参数比例被低估，实际可能达到0.01%[P6]。
结构改动方面，Adapter和Prefix Tuning显著改变了模型的前向传播路径，增加了计算延迟[P1][P6]。LoRA和GLoRA通过旁路参数实现微调，不改变原模型结构，推理速度较快（合并后）[P6][P9]。HETLORA在客户端侧引入了结构异构性，但通过聚合机制保持了服务端的一致性[P12]。

### 3. 性能证据与任务适用性
在性能表现上，LoRA和Houlsby Adapter被证明是唯一能一致达到全微调性能且无需复杂超参调优的方法[P6]。在超过100个NLP任务（如GLUE、SuperGLUE、情感分析、问答等）上，Delta Tuning方法（包含LoRA、Adapter、BitFit）表现出与全参数微调一致且非平凡的性能[P1][P2]。
然而，不同方法在特定任务上的表现存在异质性。AdaMix在GLUE任务上超越了全微调，证明了混合路由策略的有效性[P10]。GLoRA在ImageNet-A和ImageNet-Sketch等视觉任务上相比标准LoRA提升了50%至100%的性能[P9]。在推理任务上，小规模LLM（如LLaMA-13B）结合PEFT可以在算术和常识推理任务上超越大规模GPT-3.5[P3]。
在联邦学习场景下，PEFT方法（如FedPETuning）能有效降低通信开销（最高达190倍）并防御梯度反演攻击，但在数据非独立同分布（Non-IID）场景下，性能可能下降[P11]。

### 4. 训练与推理成本
PEFT方法在训练阶段显著降低了GPU内存消耗。在小批量（1和8）下，Delta Tuning方法可节省高达3/4的GPU内存；在大批量（32和64）下，可节省约1/2到1/3的GPU内存[P1]。QLoRA通过量化技术进一步突破了内存瓶颈，使得65B模型在单卡上训练成为可能[P5]。
在训练速度上，由于减少了可训练参数的梯度计算量，Delta Tuning方法的反向传播时间通常短于全参数微调[P1]。LLaMA-Adapter引入零初始化注意力机制，在8块A100 GPU上训练时间少于1小时，比全微调快3倍[P4]。
然而，推理成本存在权衡。Adapter由于增加了数据流路径，推理延迟可能增加[P1]。LoRA在未合并参数时推理速度较慢，但通过结构重参数化（如GLoRA）可以在推理阶段融合参数，保持与全微调相当的吞吐量[P9]。AdaMix通过权重平均合并机制，在推理时保持了与单模块相同的参数量和FLOPs[P10]。

### 5. 复现性与有效性
现有PEFT方法整体具有较高的可复现性，大多数主流方法（LoRA, Adapter, QLoRA, LLaMA-Adapter）都提供了开源代码和数据集[P1][P3][P4][P5][P9][P10][P11]。
然而，部分方法存在显著的不确定性。Prompt Tuning的性能严重依赖随机种子，方差较大，需要多次运行取平均[P6]。P5指出，GPT-4评估系统存在顺序效应和自评偏差，导致模型性能评估可能被高估（如Guanaco 65B的自评Elo为1348，而人类评估为1176）[P5]。此外，HETLORA等针对联邦学习的PEFT方法的理论收敛性和泛化性尚未得到充分证明[P12]。

## 讨论与局限

### 主要发现与解释
本文综述揭示了PEFT技术从“结构插入”向“参数重参数化”演进的趋势。LoRA和Adapter之所以成为主流，是因为它们在参数效率（<1%）和性能稳定性之间取得了最佳平衡[P1][P6]。相比之下，Prompt Tuning虽然参数量最少，但其性能的不稳定性限制了其在生产环境中的应用[P6]。
工程权衡的核心在于“延迟”与“效率”的博弈。Adapter虽然性能稳定，但其增加的推理延迟使其在实时性要求高的场景中受限[P1][P6]。LoRA通过重参数化解决了这一问题，但未合并时推理速度较慢[P6]。QLoRA的出现则解决了大模型训练的内存瓶颈，使得单卡训练65B模型成为现实，极大地降低了PEFT的工程门槛[P5]。

### 异质性、适用性与证据确定性
不同PEFT方法的适用性存在显著异质性。AdaMix在GLUE等NLU任务上表现优异，但在低资源任务（如RTE）上可能因增加模块数量而导致性能下降[P10]。HETLORA在联邦学习场景下表现突出，但在系统资源（秩）与数据分布可能相关的假设下，其理论收敛性仍存疑[P12]。
证据确定性方面，LoRA和Adapter在通用NLU/NLG任务上与全微调性能一致的证据强度较高[P1][P6]。而AdaMix超越全微调、小模型PEFT超越大模型全微调的证据强度中等，且依赖于特定的任务类型和模型配置[P3][P10]。Prompt Tuning在零样本场景下的优势证据强度较高，但在全微调基线下的表现证据强度较低[P2][P6]。

### 本综述的局限
本研究仅纳入了12篇arXiv论文，可能遗漏了部分重要工作。此外，不同论文使用的评估指标、数据集和模型规模存在差异，直接比较存在一定困难。特别是P5中使用的GPT-4评估系统存在偏差，可能高估了某些模型的性能[P5]。

### 研究与实践启示
对于实践者而言，在资源受限场景下，LoRA是首选方案，其性能稳定且易于部署。在需要极致性能的场景下，可考虑AdaMix或GLoRA，但需权衡额外的训练成本。在联邦学习或边缘计算场景下，HETLORA和QLoRA提供了有效的解决方案。对于研究者而言，未来需要关注PEFT方法在复杂多模态任务、对抗性攻击下的鲁棒性，以及建立标准化的PEFT基准测试集[P6][P7]。

## 结论
参数高效微调方法已经形成了一个包含加性、重参数化、混合及量化技术的完整技术谱系。LoRA和Adapter凭借其卓越的参数效率和性能稳定性，确立了其在当前技术栈中的核心地位。QLoRA通过量化技术解决了大模型训练的内存瓶颈，而AdaMix和GLoRA等先进方法通过混合机制和结构搜索在特定任务上实现了性能突破。尽管Prompt Tuning在零样本场景下具有潜力，但其收敛慢和不稳定的特性限制了其广泛应用。未来的研究应致力于解决PEFT方法在理论收敛性、标准化评估及复杂场景适应性方面的不足。

## 参考来源

- [P1] Ning Ding, Yujia Qin, Guang Yang, Fuchao Wei, Zonghan Yang, Yusheng Su, Shengding Hu, Yulin Chen, Chi-Min Chan, Weize Chen, Jing Yi, Weilin Zhao, Xiaozhi Wang, Zhiyuan Liu, Hai-Tao Zheng, Jianfei Chen, Yang Liu, Jie Tang, Juanzi Li, Maosong Sun. Parameter-efficient fine-tuning of large-scale pre-trained language models. 2023. https://doi.org/10.1038/s42256-023-00626-4
- [P2] Ning Ding, Yujia Qin, Guang Yang, Fuchao Wei, Zonghan Yang, Yusheng Su, Shengding Hu, Yulin Chen, Chi-Min Chan, Weize Chen, Jing Yi, Weilin Zhao, Xiaozhi Wang, Zhiyuan Liu, Hai-Tao Zheng, Jianfei Chen, Yang Liu, Jie Tang, Juanzi Li, Maosong Sun. Delta Tuning: A Comprehensive Study of Parameter Efficient Methods for Pre-trained Language Models. 2022. https://doi.org/10.21203/rs.3.rs-1553541/v1
- [P3] Zhiqiang Hu, Lei Wang, Yihuai Lan, Wanyu Xu, Ee‐Peng Lim, Lidong Bing, Xing Xu, Soujanya Poria, Roy Lee. LLM-Adapters: An Adapter Family for Parameter-Efficient Fine-Tuning of Large Language Models. 2023. https://doi.org/10.18653/v1/2023.emnlp-main.319
- [P4] Renrui Zhang, Jiaming Han, Liu, Chris, Peng Gao, Aojun Zhou, Xiangfei Hu, Shilin Yan, Pan Lu, Hongsheng Li, Yu Qiao. LLaMA-Adapter: Efficient Fine-tuning of Language Models with Zero-init Attention. 2023. https://arxiv.org/abs/2303.16199
- [P5] Tim Dettmers, Artidoro Pagnoni, Ari Holtzman, Luke Zettlemoyer. QLoRA: Efficient Finetuning of Quantized LLMs. 2023. https://arxiv.org/abs/2305.14314
- [P6] Vladislav Lialin, Vijeta Deshpande, Yao, Xiaowei, Rumshisky, Anna. Scaling Down to Scale Up: A Guide to Parameter-Efficient Fine-Tuning. 2023. https://arxiv.org/abs/2303.15647
- [P7] Lingling Xu, Haoran Xie, S. Joe Qin, Xiaohui Tao, Fu Lee Wang. Parameter-Efficient Fine-Tuning Methods for Pretrained Language Models: A Critical Review and Assessment. 2023. https://arxiv.org/abs/2312.12148
- [P8] Zeyu Han, Chao Gao, Jinyang Liu, Jeff, Zhang. Parameter-Efficient Fine-Tuning for Large Models: A Comprehensive Survey. 2024. https://arxiv.org/abs/2403.14608
- [P9] Arnav Chavan, Zhuang Liu, Deepak Gupta, Eric P. Xing, Zhiqiang Shen. One-for-All: Generalized LoRA for Parameter-Efficient Fine-tuning. 2023. https://arxiv.org/abs/2306.07967
- [P10] Yaqing Wang, Sahaj Agarwal, Subhabrata Mukherjee, Xiaodong Liu, Jing Gao, Ahmed Hassan Awadallah, Jianfeng Gao. AdaMix: Mixture-of-Adaptations for Parameter-efficient Model Tuning. 2022. https://doi.org/10.18653/v1/2022.emnlp-main.388
- [P11] Zhuo Zhang, Yuanhang Yang, Yong Dai, Qifan Wang, Yue Yu, Lizhen Qu, Zenglin Xu. FedPETuning: When Federated Learning Meets the Parameter-Efficient Tuning Methods of Pre-trained Language Models. 2023. https://doi.org/10.18653/v1/2023.findings-acl.632
- [P12] Yae Jee Cho, Luyang Liu, Zheng Xu, Aldi Fahrezi, Gauri Joshi. Heterogeneous LoRA for Federated Fine-tuning of On-Device Foundation Models. 2024. https://doi.org/10.18653/v1/2024.emnlp-main.717
