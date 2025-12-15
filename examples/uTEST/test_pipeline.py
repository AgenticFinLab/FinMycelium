
from datetime import datetime
from typing import List

from finmy.pipeline import FinmyPipeline


def get_sample_raw_texts() -> List[str]:
    """
    Get sample raw text content for testing purposes.

    Returns:
        List of raw text strings containing financial and AI-related content
        in both Chinese and English.
    """
    return [
        """
            近年来，人工智能在资本市场和零售金融应用方面取得了显著增长。一些银行已采用机器学习进行信用评分和欺诈检测，提高了风险控制效率和运营响应能力。然而，模型的稳定性及其在极端市场条件下的性能仍需要持续评估。

            一些机构已经建立了端到端的风险管理框架，包括数据治理、模型验证、监控和回溯测试。对于黑匣子模型，内部和外部审计都要求更高的可解释性，以满足监管机构对透明度和健全监管的期望。

            从合规性的角度来看，模型生命周期管理是一个关键的优先事项。批准、版本控制、变更跟踪和影响评估必须完整记录。当模型输出用于关键业务决策时，公司应建立人在环机制和阈值警报。

            此外，数据质量直接影响模型性能。组织应实施数据目录和质量指标系统，以确保培训和推理数据的一致性和合法合规使用。对于涉及个人数据的情况，必须严格遵守隐私保护和跨境数据流规定。
            
            展望未来，生成式人工智能将在投资研究、客户服务和运营中得到更广泛的应用。与此同时，组织需要通过在其治理框架中制定模型合规性、透明度和弹性的核心指标来平衡创新和风险。
            """,
        """
            In recent years, artificial intelligence has seen significant growth in capital markets and retail finance applications. Some banks have adopted machine learning for credit scoring and fraud detection, boosting risk control efficiency and operational responsiveness. However, the stability of models and their performance under extreme market conditions still require continuous assessment.Several institutions have established end-to-end risk management frameworks, incorporating data governance, model validation, monitoring, and back-testing. For black-box models, both internal and external audits demand higher levels of explainability to meet regulatory expectations regarding transparency and sound supervision.
            
            From a compliance perspective, model lifecycle management is a key priority. Approval, version control, change tracking, and impact assessments must be fully documented. When model outputs are used for critical business decisions, firms should establish human-in-the-loop mechanisms and threshold alerts.
            
            Moreover, data quality directly affects model performance. Organizations should implement data catalogs and quality metrics systems to ensure consistency and lawful, compliant usage of data for training and inference. For scenarios involving personal data, privacy protection and cross-border data flow regulations must be strictly observed.
            
            Looking ahead, generative AI will be more widely used in investment research, customer service, and operations. At the same time, organizations need to balance innovation and risk by making model compliance, transparency, and resilience central metrics in their governance frameworks.
            """,
    ]


if __name__ == "__main__":
    output_dir = f"./examples/utest/Collector/test_files/event_output_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    pipeline = FinmyPipeline({"output_dir": output_dir})
    raw_texts = get_sample_raw_texts()
    pipeline.lm_build_pipeline_main(
        raw_texts=raw_texts,
        query_text="识别与人工智能在金融风控与合规相关的内容",
        key_words=["人工智能", "AI", "风险管理", "模型合规", "透明度"],
    )
