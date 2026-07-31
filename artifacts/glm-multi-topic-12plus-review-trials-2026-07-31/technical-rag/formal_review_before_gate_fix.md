# 检索增强生成的架构、评价与可靠性技术综述

## 摘要

检索增强生成通过将外部知识库与大型语言模型结合，有效缓解了模型的知识时效性限制和幻觉问题。本文旨在系统综述检索增强生成系统在检索器设计、生成器耦合机制、训练优化策略、评价框架、事实可靠性保障以及计算成本控制等方面的技术路线与证据边界。基于对12篇arXiv论文的严格筛选与综合分析，本文发现RAG架构正从静态的“检索-生成”流程向动态、迭代及纠错式耦合演进。研究表明，迭代检索生成（如ITER-RETGEN）和基于实时信息需求的动态检索（如DRAGIN）在复杂任务中表现优异，但需通过知识蒸馏等手段控制开销。在可靠性方面，纠正性框架（如CRAG）和偏好调优（如KBPT）显著提升了事实准确性，但LLM在负样本拒绝和信息整合上仍存在显著局限。评价体系正从传统的EM/F1指标向包含上下文相关性、引用准确性和鲁棒性的多维指标扩展。本文最后指出了当前在标准化多模态基准、长上下文效率优化及通用纠错机制泛化性方面的证据缺口。

## 引言

大型语言模型在自然语言处理领域取得了突破性进展，但其固有的知识截止日期、幻觉现象以及对特定领域知识的匮乏限制了其在实际应用中的可靠性。检索增强生成作为一种新兴范式，通过在生成过程中引入外部检索模块，动态获取最新或特定领域的知识，从而显著提升了生成内容的准确性与可解释性。然而，随着RAG技术的深入应用，其架构设计、检索器与生成器的耦合方式、训练策略、评估标准以及计算效率之间的权衡成为了学术界和工业界关注的焦点。

本文聚焦于RAG系统的核心技术演进，旨在回答以下核心问题：检索器与生成器的主要耦合机制有哪些？在训练与优化层面存在哪些关键策略？现有的评价框架是否足以衡量RAG系统的可靠性？如何有效控制计算成本并提升事实准确性？通过对最新文献的系统梳理，本文将揭示从静态RAG到动态、纠错式RAG的技术演进路径，并明确当前研究的证据边界与局限性。

## 方法

本研究采用技术综述模式，遵循严格的证据提取与综合流程。真实方法记录显示，所有候选文献均来源于arXiv预印本平台，经标题摘要筛选后，最终纳入12篇可读取全文的论文进行深度分析。

在文献筛选方面，我们排除了非技术性讨论、纯理论推导或未提供具体技术细节的综述文章，重点关注实证研究、框架提案及基准测试。证据提取过程严格依据结构化证据卡，记录了每篇文献的研究对象、方法框架、评估范围、主要发现及计算成本证据。在综合分析阶段，我们依据研究问题将文献归类为“检索器-生成器耦合机制”、“训练与优化策略”、“评价框架”、“事实可靠性”及“计算效率”五个综合单元，通过跨研究比较识别共识、分歧及异质性来源。

## 结果

### 检索器-生成器耦合机制的技术演进

RAG系统的核心挑战在于如何高效地耦合检索器与生成器。传统的静态RAG范式（Naive RAG）仅执行简单的“索引-检索-生成”流程，缺乏对查询复杂度的优化，导致检索精度低和生成幻觉问题突出 `[P1]`。为解决这一问题，技术路线逐渐向迭代耦合、动态耦合及纠错耦合演进。

迭代耦合机制通过让生成输出引导后续检索，实现了检索与生成的深度协同。例如，ITER-RETGEN框架利用生成输出作为查询，检索更相关的知识，并通过生成增强检索适应（Generation-Augmented Retrieval Adaptation）将重排序器的知识蒸馏至检索器，从而在多跳问答任务上实现了显著的性能提升 `[P2]`。然而，迭代过程并非没有代价，过多的迭代可能导致语义不连续和无关信息的累积，从而引入噪声 `[P1]`。

动态耦合机制旨在根据大模型实时的信息需求决定检索时机与内容。DRAGIN框架通过实时信息需求检测（RIND）和基于自注意力的查询 formulation（QFS），实现了对检索过程的动态控制。值得注意的是，DRAGIN在动态设置中表现出一个反直觉的现象：传统的稀疏检索器BM25往往优于复杂的稠密检索模型 `[P3]`。这表明在动态、不确定的检索场景下，基于词频的匹配可能比基于语义向量的相似度更具鲁棒性。

纠错耦合机制则侧重于处理检索错误。CRAG框架引入了一个轻量级的T5评估器来判定检索结果的质量（正确、错误或模糊），并据此触发纠错动作，如调用外部网络搜索或对检索文档进行分解重组。在COVID-19事实核查任务中，CRAG和SRAG等纠错框架显著优于Naive RAG和Self-RAG，准确率分别达到了0.972和0.973 `[P8]` `[P11]`。这种基于评估器的纠错机制在处理长文本生成和事实核查时表现出色，但同时也增加了额外的计算开销 `[P8]`。

### 训练与优化策略

在RAG系统的训练与优化中，检索器与生成器的处理策略存在显著差异。对于检索器，微调通常被视为提升性能的有效手段。研究表明，通过微调嵌入模型（如Sentence-transformers）可以显著提高特定领域的召回率和F1分数 `[P9]`。此外，将重排序器的知识蒸馏到检索器中（Generation-Augmented Retrieval Adaptation）不仅能提升性能，还能减少迭代检索所需的步数，从而降低计算成本 `[P2]`。

然而，对生成器核心模型的微调则需格外谨慎。一项针对领域特定查询的案例研究显示，在规模较小且分布不均的数据集上微调LLaMA-2等大模型，可能导致模型输出变得冗长且重复，反而降低了生成质量 `[P9]`。针对这一问题，知识平衡偏好调优（KBPT）被提出用于平衡模型内部知识与外部检索上下文。在医学视觉语言模型（Med-LVLM）中，KBPT通过构建偏好数据集，有效缓解了模型对检索上下文的过度依赖，将过度依赖率从约47%降低至27% `[P7]`。这表明，通过偏好学习而非直接微调，可以在不牺牲生成能力的前提下提升事实可靠性。

### 评价框架的多元化发展

随着RAG技术的复杂化，传统的准确率（EM/F1）指标已不足以全面评估系统性能。当前的证据表明，评价框架正向多维化和鲁棒性导向转变。

首先，针对RAG特有的能力，如噪声鲁棒性、负样本拒绝、信息整合及反事实鲁棒性，研究者构建了专门的基准。例如，RGB基准测试揭示了LLM在负样本拒绝任务上的显著短板，其拒绝率在英文和中文环境下均低于50% `[P4]`。在信息整合方面，主要错误类型包括合并错误（28%）、忽略错误（28%）和对齐错误（6%） `[P4]`。

其次，医学领域的MIRAGE基准测试揭示了“中间丢失”现象，即模型准确性与检索片段在上下文中的位置呈U型关系，这为优化长上下文RAG的上下文窗口设计提供了重要依据 `[P5]`。此外，评价重点已扩展至上下文相关性和忠实度。P6指出，评估框架必须涵盖检索质量（上下文相关性）和生成质量（忠实度），而不仅仅是下游任务的准确率 `[P6]`。Self-Reasoning等框架甚至引入了引用召回率和引用精确率作为关键指标，证明了生成轨迹的可追溯性对提升事实可靠性的重要性 `[P10]`。

### 事实可靠性与幻觉缓解

幻觉是RAG系统面临的主要挑战之一。缓解幻觉的技术路线主要分为外部纠错和内部控制两类。

外部纠错依赖于检索质量本身。CRAG通过引入外部搜索和文档精炼算法，在PopQA和PubHealth等任务上显著提升了事实准确性 `[P8]`。在医疗事实核查中，集成RAG的系统相比基线GPT-4，能够提供更详细的证据引用，显著降低了幻觉率 `[P11]`。

内部控制则侧重于模型自身的反思与平衡。Self-RAG通过引入反思标记（如'retrieve', 'critic'）使模型能够自主控制检索与生成过程 `[P1]`。Self-Reasoning框架则通过生成推理轨迹，利用RAP、EAP和TAP三个过程来增强证据选择和轨迹分析能力，在引用准确率上甚至超越了GPT-4 `[P10]`。对于多模态RAG，RULE框架通过假设检验控制检索上下文的数量k，并利用KBPT平衡内部与外部知识，在医学视觉问答任务上实现了47.4%的平均准确率提升 `[P7]`。然而，证据也显示，单纯的RAG可能并不稳定，有时甚至会导致性能下降，必须配合特定的调优策略 `[P7]`。

### 计算效率与成本控制

RAG系统的计算成本主要来源于检索步骤的引入和上下文长度的增加。引入检索步骤必然会增加推理时间，但RAG允许在不重新训练生成器的情况下更新知识，从而降低了长期维护成本 `[P12]`。

上下文长度的控制是效率优化的关键。过长的上下文会引入噪声，导致模型在关键信息上表现下降，即“中间丢失”现象 `[P1]` `[P5]`。为此，上下文压缩和选择技术（如LLMLingua, PRCA）被广泛采用，以过滤无关信息并缓解噪声影响 `[P1]`。

在迭代检索中，计算开销是一个主要顾虑。虽然迭代耦合能提升性能，但P2指出，通过知识蒸馏减少迭代次数可以有效控制开销 `[P2]`。相比之下，CRAG等纠错框架虽然显著提升了准确性，但也带来了更高的FLOPs和执行时间（从0.363s增加到0.512s） `[P8]`。因此，在工程实践中，需要在检索精度、生成质量和计算延迟之间进行精细的权衡。

## 讨论

### 主要发现与解释

本文综述揭示了RAG技术从“静态管道”向“智能代理”演进的清晰轨迹。检索器与生成器的耦合方式直接决定了系统的性能上限。静态RAG在简单任务中表现尚可，但在处理复杂推理和多跳查询时捉襟见肘。相比之下，迭代耦合（如ITER-RETGEN）和动态耦合（如DRAGIN）通过引入反馈机制，显著提升了系统处理复杂信息需求的能力 `[P2]` `[P3]`。值得注意的是，DRAGIN在动态场景下BM25优于稠密检索器的发现，挑战了“稠密检索优于稀疏检索”的普遍假设，提示我们在设计动态RAG时，可能需要重新审视检索器的选择策略 `[P3]`。

在可靠性方面，单纯依赖检索结果往往不足以保证事实准确性。证据表明，模型对检索上下文的“过度依赖”是一个普遍问题，尤其是在多模态领域 `[P7]`。KBPT等偏好调优方法通过显式地教导模型平衡内部知识与外部证据，有效地缓解了这一问题。同时，CRAG等纠错框架证明了引入外部评估器和纠错机制对于事实核查等高风险任务至关重要 `[P8]` `[P11]`。

### 异质性、适用性与证据确定性

不同研究在评估指标和实验设置上的异质性是理解证据边界的关键。P2和P5主要依赖EM和准确率等传统指标，而P4、P6和P10则强调引用准确率、忠实度和鲁棒性等RAG特有指标。这种差异导致直接比较不同研究的性能排名变得困难。例如，P2声称的8.6%绝对增益是基于EM指标，而P8在CRAG中报告的20%+提升是基于准确率和FactScore。因此，在解读“SOTA”性能时，必须明确其适用的指标和任务场景。

此外，数据集的领域差异也导致了结果的异质性。P5的MIRAGE基准专注于医学领域，揭示了“中间丢失”现象和缩放定律 `[P5]`；而P9的CMU案例研究则聚焦于学术日历等特定领域，强调了领域适配的重要性 `[P9]`。这些发现表明，RAG系统的性能高度依赖于领域特性和数据质量。

### 本综述的局限

尽管本文涵盖了12篇高质量文献，但仍存在若干证据缺口。首先，缺乏标准化的多模态RAG基准。虽然P7和P12讨论了多模态应用，但缺乏像RGB或MIRAGE那样广泛认可的多模态评估套件，使得跨模态性能比较受限 `[P7]` `[P12]`。

其次，关于计算成本的量化分析尚不充分。P11虽然提到了数据预处理以减少成本，但缺乏具体的推理延迟和内存使用量的详细指标 `[P11]`。P8提供了FLOPs数据，但未提供端到端的延迟对比。这使得工程实践者在评估不同RAG架构的实际部署成本时面临困难。

最后，对于纠错机制（如CRAG）的泛化性研究不足。这些机制在事实核查等确定性任务中表现优异，但在创意写作、代码生成等开放性任务中的效果尚不明确 `[P8]`。

### 研究与实践启示

对于研究者而言，未来的工作应致力于构建更全面的评估基准，特别是涵盖多模态和长上下文场景的基准。同时，探索更高效的纠错机制和轻量级的动态检索策略是提升RAG系统实用性的关键。

对于实践者而言，本文建议在构建RAG系统时，根据任务复杂度选择合适的耦合策略：简单任务可采用静态RAG，复杂推理任务应采用迭代或动态RAG。在训练阶段，优先微调检索器而非生成器，并警惕在数据量不足时微调生成器可能带来的性能退化。在部署阶段，应重视上下文压缩和噪声过滤，以平衡性能与计算成本。

## 结论

检索增强生成技术正经历从基础架构到智能系统的深刻变革。本文综述表明，通过引入迭代、动态及纠错耦合机制，RAG系统在处理复杂推理和事实核查任务时展现出显著优势。训练策略上，检索器的微调与知识蒸馏是提升性能的有效手段，而生成器的微调则需谨慎对待。评价体系的多元化，特别是对引用准确性和鲁棒性的关注，为系统可靠性提供了更全面的度量标准。尽管在多模态基准、长上下文效率及纠错机制泛化性方面仍存在证据缺口，但RAG技术已为构建可靠、高效且可更新的AI生成系统奠定了坚实基础。

## 参考来源

- [P1] Yunfan Gao, Yun Xiong, Xinyu Gao, Kangxiang Jia, Jinliu Pan, Yuxi Bi, Yi Dai, Jiawei Sun, Wang, Meng, Wang, Haofen. Retrieval-Augmented Generation for Large Language Models: A Survey. 2023. https://arxiv.org/abs/2312.10997
- [P2] Zhihong Shao, Yeyun Gong, Yelong Shen, Minlie Huang, Nan Duan, Weizhu Chen. Enhancing Retrieval-Augmented Large Language Models with Iterative Retrieval-Generation Synergy. 2023. https://doi.org/10.18653/v1/2023.findings-emnlp.620
- [P3] Weihang Su, Yichen Tang, Qingyao Ai, Zhijing Wu, Yiqun Liu. DRAGIN: Dynamic Retrieval Augmented Generation based on the Real-time Information Needs of Large Language Models. 2024. https://doi.org/10.18653/v1/2024.acl-long.702
- [P4] Jiawei Chen, Hongyu Lin, Xianpei Han, Le Sun. Benchmarking Large Language Models in Retrieval-Augmented Generation. 2023. https://arxiv.org/abs/2309.01431
- [P5] Guangzhi Xiong, Qiao Jin, Zhiyong Lu, Aidong Zhang. Benchmarking Retrieval-Augmented Generation for Medicine. 2024. https://doi.org/10.18653/v1/2024.findings-acl.372
- [P6] Yizheng Huang, Jimmy Xiangji Huang. A Survey on Retrieval-Augmented Text Generation for Large Language Models. 2026. https://arxiv.org/abs/2404.10981
- [P7] Peng Xia, Kangyu Zhu, Haoran Li, Hongtu Zhu, Yun Li, Gang Li, Linjun Zhang, Huaxiu Yao. RULE: Reliable Multimodal RAG for Factuality in Medical Vision Language Models. 2024. https://doi.org/10.18653/v1/2024.emnlp-main.62
- [P8] Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling. Corrective Retrieval Augmented Generation. 2024. https://arxiv.org/abs/2401.15884
- [P9] Jiarui Li, Ye Yuan, Zehua Zhang. Enhancing LLM Factual Accuracy with RAG to Counter Hallucinations: A Case Study on Domain-Specific Queries in Private Knowledge-Bases. 2024. https://arxiv.org/abs/2403.10446
- [P10] Yuan Xia, Jingbo Zhou, Zhenhui Shi, Jun Chen, Haifeng Huang. Improving Retrieval Augmented Language Model with Self-Reasoning. 2025. https://doi.org/10.1609/aaai.v39i24.34743
- [P11] Hai Li, Jingyi Huang, Mengmeng Ji, Yuyi Yang, Ruopeng An. Use of Retrieval-Augmented Large Language Model for COVID-19 Fact-Checking: Development and Usability Study. 2025. https://doi.org/10.2196/66098
- [P12] Penghao Zhao, Hailin Zhang, Qinhan Yu, Zhengren Wang, Yunteng Geng, Fangcheng Fu, L. Yang, Wentao Zhang, Jiang, Jie, Cui, Bin. Retrieval-Augmented Generation for AI-Generated Content: A Survey. 2024. https://arxiv.org/abs/2402.19473
