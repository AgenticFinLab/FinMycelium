"""
A session to test the lx_match module.

Run:
    python examples/Matcher/lx_matcher/test_kw_match.py
"""

from finmy.matcher.lx_match import KWMatcher
from finmy.matcher.summarizer import SummarizedUserQuery
from finmy.matcher.base import MatchInput
import dotenv

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

sq = SummarizedUserQuery(summarization=query_text, key_words=key_words)
match_input = MatchInput(match_data=content, summarized_query=sq)

matcher = KWMatcher()
result = matcher.run(match_input)

for item in result.items:
    print(item.start, item.end)
    print(item.paragraph)
