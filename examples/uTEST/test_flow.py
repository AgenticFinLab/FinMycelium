import uuid

from finmy.generic import RawData, UserQueryInput
from finmy.converter import (
    write_data_to_file,
    raw_data_and_summarized_query_to_match_input,
    convert_to_build_input,
    match_output_to_meta_samples,
)
from finmy.db_manager import DataManager
from finmy.builder.base import BuildInput
from finmy.matcher.base import MatchInput, SummarizedUserQuery
from finmy.matcher.lm_match import LLMMatcher
from finmy.matcher.summarizer import KWLMSummarizer

data_manager = DataManager()


# 假设我们有原始内容列表
raw_texts = [
    """
    近年来，人工智能在资本市场与零售金融的应用显著增加。部分银行采用机器学习进行信用评分与反欺诈检测，这提升了风控效率与业务响应速度。然而，模型的稳定性与在极端市场情况下的表现仍需持续评估。

    一些机构建立了端到端的风险管理框架，包括数据治理、模型验证、监控与回溯测试。对于黑箱模型，内部与外部审计要求更高的可解释性，以满足监管对于透明度与审慎监管的原则。

    从合规角度来看，模型生命周期管理成为重点。审批、版本控制、变更记录与影响评估需要被完整记录。当模型输出被用于关键业务决策时，应建立人机协同机制与阈值告警。

    此外，数据质量直接影响模型表现。企业应建立数据目录与质量度量体系，确保训练与推断数据的一致性与合法合规使用。对于涉及个人数据的场景，必须遵守隐私保护与跨境数据流动的相关规定。

    展望未来，生成式 AI 在投研、客服与运营场景的应用将更广泛。与此同时，企业需要在创新与风险之间寻找平衡，将模型合规、透明度与韧性纳入治理框架的核心指标。
    """,
    """
    In recent years, artificial intelligence has seen significant growth in capital markets and retail finance applications. Some banks have adopted machine learning for credit scoring and fraud detection, boosting risk control efficiency and operational responsiveness. However, the stability of models and their performance under extreme market conditions still require continuous assessment.Several institutions have established end-to-end risk management frameworks, incorporating data governance, model validation, monitoring, and back-testing. For black-box models, both internal and external audits demand higher levels of explainability to meet regulatory expectations regarding transparency and sound supervision.
    
    From a compliance perspective, model lifecycle management is a key priority. Approval, version control, change tracking, and impact assessments must be fully documented. When model outputs are used for critical business decisions, firms should establish human-in-the-loop mechanisms and threshold alerts.
    
    Moreover, data quality directly affects model performance. Organizations should implement data catalogs and quality metrics systems to ensure consistency and lawful, compliant usage of data for training and inference. For scenarios involving personal data, privacy protection and cross-border data flow regulations must be strictly observed.
    
    Looking ahead, generative AI will be more widely used in investment research, customer service, and operations. At the same time, organizations need to balance innovation and risk by making model compliance, transparency, and resilience central metrics in their governance frameworks.
    """,
]

raw_data_records = []
for text in raw_texts:
    # 将内容写入文件
    filename = write_data_to_file(text)
    # 创建RawData对象
    raw_data = RawData(
        raw_data_id=str(uuid.uuid4()),
        source="https://example.com",
        location=filename,
        time="2024-06-01T12:00:00Z",
        data_copyright="© 2023 ACM, Inc., All rights reserved.",
        tag=["测试"],
        method="人工导入",
    )
    # 假设这里保存到数据库，我们这里只是收集进内存
    raw_data_records.append(raw_data)

print("写入并保存的RawData对象...")
data_manager.insert_raw_data_batch(raw_data_records)
print("写入并保存的RawData对象完成")
print("=" * 25)

print("正在创建用户查询输入对象...")
user_query_input = UserQueryInput(
    query_text="识别与人工智能在金融风控与合规相关的内容",
    key_words=["人工智能", "AI", "风险管理", "模型合规", "透明度"],
)
print("用户查询输入对象创建完成：", user_query_input)
print("用户查询输入对象插入数据库...")
data_manager.insert_user_query(user_query_input)
print("用户查询输入对象插入数据库完成")
print("=" * 25)

print("正在使用Summarizer生成summarized query...")
summarizer = KWLMSummarizer({"llm_name": "deepseek-chat"})
summarized_query = summarizer.summarize(user_query_input)
print("summarized_query构造完成：", summarized_query)
print("=" * 25)


print("使用raw_data_and_summarized_query_to_match_input构造MatchInput对象...")
match_input = raw_data_and_summarized_query_to_match_input(
    raw_data=raw_data_records[0],
    summarized_query=summarized_query,
)
print("MatchInput对象构造完成：", match_input)
print("=" * 25)


print("正在使用lm_matcher进行匹配...")
lm_matcher = LLMMatcher(lm_name="deepseek-chat")
match_output = lm_matcher.run(match_input)
print("匹配结果：", match_output)
print("=" * 25)

print("正在使用match_output_to_meta_samples构造meta_samples...")
meta_samples = match_output_to_meta_samples(
    match_output=match_output,
    raw_data=raw_data_records[0],
    category="金融风控",
    knowledge_field="人工智能",
)
print("构造得到的meta_samples：", meta_samples)
print("=" * 25)

print("正在保存meta_samples到数据库...")

data_manager.insert_meta_samples(meta_samples)
print("meta_samples保存完成")
print("=" * 25)


print("使用convert_to_build_input构造BuildInput对象...")
build_input = convert_to_build_input(
    user_query=user_query_input,
    meta_samples=meta_samples,  # 可根据match_output或其他来源填充MetaSample列表
    extras={},  # 这里可以传递额外信息
)
print("BuildInput对象构造完成：", build_input)
print("=" * 25)
