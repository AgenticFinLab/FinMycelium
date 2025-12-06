"""
Definition of all elements based on the financial knowledge.
"""

from typing import Literal

# Canonical financial scenarios supported by the system, grounded in theory and historical precedent.
SupportedFinancialScenario = Literal[
    "Bank Run",
    "Ponzi Scheme",
    "Short Squeeze",
    "Sovereign Default",
    "Liquidity Spiral",
    "Market Manipulation",
    "Regulatory Arbitrage",
    "Credit Event",
    "Systemic Shock",
    "Accounting Fraud",
    "Leverage Cycle Collapse",
    "Stablecoin Depeg",
]

EpisodeType = Literal[
    # 通用信息披露类
    "Financial Statement Disclosure",
    "Earnings Guidance Update",
    "Whistleblower Report",
    "Short Seller Report",
    "Auditor Resignation",
    "Rating Agency Downgrade",
    # 交易与流动性行为
    "Large-Scale Redemption",
    "Margin Call Issuance",
    "Forced Asset Liquidation",
    "Collateral Rehypothecation",
    "Prime Broker Position Unwind",
    "Retail Investor Panic Selling",
    # 监管与法律行动
    "Regulatory Investigation Launch",
    "Securities Enforcement Action",
    "Trading Suspension",
    "Bankruptcy Filing",
    "Court Receivership Order",
    "Central Bank Emergency Lending",
    # 市场机制事件
    "Exchange Price Limit Hit",
    "Clearing House Default Declaration",
    "Stablecoin Redemption Suspension",
    "Cross-Margin Call Cascade",
    # 恶意行为（仅用于欺诈/操纵类）
    "Fictitious Revenue Recording",
    "Fake Cash Balance Fabrication",
    "Pump and Dump Trade Pattern",
]

ParticipantRole = Literal[
    # 核心义务方
    "Issuer",
    "Obligor",
    "Fund Manager",
    "Platform Operator",
    # 监管与公共机构
    "Financial Regulator",
    "Central Bank",
    "Deposit Insurance Agency",
    "Securities Enforcement Authority",
    # 市场参与者
    "Retail Investor",
    "Institutional Investor",
    "Hedge Fund",
    "Prime Broker",
    "Market Maker",
    "Short Seller",
    "Liquidity Provider",
    # 信息与验证中介
    "External Auditor",
    "Credit Rating Agency",
    "Financial News Media",
    "Independent Research Firm",
    # 金融基础设施
    "Central Counterparty (CCP)",
    "Custodian Bank",
    "Payment System Operator",
]
