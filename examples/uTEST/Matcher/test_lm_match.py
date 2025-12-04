"""
A session to test the lm_match module.

Run:
    python examples/Matcher/test_lm_match.py
"""

import time
import dotenv
import uuid

from finmy.matcher.lm_match import LLMMatcher
from finmy.matcher.summarizer import SummarizedUserQuery
from finmy.matcher.base import MatchInput
from finmy.generic import RawData
from finmy.converter import match_to_samples


dotenv.load_dotenv()

query_text = "识别与人工智能在金融风控与合规相关的内容"
key_words = ["人工智能", "AI", "风险管理", "模型合规", "透明度"]
content = """
近年来，人工智能在资本市场与零售金融的应用显著增加。部分银行采用机器学习进行信用评分与反欺诈检测，这提升了风控效率与业务响应速度。然而，模型的稳定性与在极端市场情况下的表现仍需持续评估。

一些机构建立了端到端的风险管理框架，包括数据治理、模型验证、监控与回溯测试。对于黑箱模型，内部与外部审计要求更高的可解释性，以满足监管对于透明度与审慎监管的原则。

从合规角度来看，模型生命周期管理成为重点。审批、版本控制、变更记录与影响评估需要被完整记录。当模型输出被用于关键业务决策时，应建立人机协同机制与阈值告警。

此外，数据质量直接影响模型表现。企业应建立数据目录与质量度量体系，确保训练与推断数据的一致性与合法合规使用。对于涉及个人数据的场景，必须遵守隐私保护与跨境数据流动的相关规定。

展望未来，生成式 AI 在投研、客服与运营场景的应用将更广泛。与此同时，企业需要在创新与风险之间寻找平衡，将模型合规、透明度与韧性纳入治理框架的核心指标。
"""
rd = RawData(
    raw_data_id=str(uuid.uuid4()),
    source="xxx/technical_report.pdf",
    location="https://example.com/xxx/technical_report.pdf",
    time=time.strftime("%Y-%m-%d %H:%M:%S %z"),
    data_copyright="© 2023 ACM, Inc., All rights reserved.",
    method="PyMuPDF (v1.23.0)",
    tag="AgenticFin",
)

sq = SummarizedUserQuery(summarization=query_text, key_words=key_words)
match_input = MatchInput(
    match_data=content, summarized_query=sq, db_item=rd
)  # TODO: to be determined that removing db_item argument.

matcher = LLMMatcher(lm_name="deepseek/deepseek-chat")
result = matcher.run(match_input)

meta_samples = match_to_samples(
    result, rd, category="fintech", knowledge_field="accountant"
)

print(f"Method: {result.method}")
print(f"Elapsed: {result.time:.6f}s")
print(f"Matched items: {len(result.items)}")

for item in result.items:
    print(f"Span: ({item.start}, {item.end})")
    print(item.paragraph)

print("meta_sample:", meta_samples)
#
