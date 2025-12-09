def forex_binary_options_fraud_prompt(text: str) -> str:
    return """
You are an expert financial analyst and investigative researcher specializing in forensic reconstruction of financial fraud events. Your task is to generate a comprehensive, fact-based, and logically coherent simulation of a specified **Forex / Binary Options Fraud** case.

### **Objective**
Based on the provided multi-source data (news articles, regulatory filings, court documents, investor reports, etc.), reconstruct the complete narrative of the fraud event. Your output must be a detailed, structured JSON object that meticulously documents the event's lifecycle, mechanisms, key actors, financial flows, and impacts.

### **Core Simulation Principles**
1.  **Fact-Based & Logical:** All information must be derived from or logically inferred from the provided source data. Do not invent facts. Use explicit data points (e.g., dates, amounts, percentages) where available, and label estimates or deductions clearly.
2.  **Chronological Integrity:** Present the event in its natural chronological sequence, showing cause and effect.
3.  **Multi-Actor Perspective:** Analyze the event from the perspectives of the fraudsters, investors, regulators, and other relevant entities.
4.  **Financial Transparency:** Trace the flow of funds to the greatest detail possible, highlighting discrepancies between promised and actual use.

### **Required Analysis Framework & JSON Structure**
Output **must** be a valid JSON object following this exact schema. The JSON should be ready for programmatic parsing.

```json
{
  "fraud_event_summary": {
    "definition": "A concise overview (2-4 sentences) of the entire Forex/Binary Options fraud scheme.",
    "value": ""
  },
  "primary_perpetrators": {
    "definition": "List of key individuals and entities (companies, platforms) that orchestrated the fraud. Include names, roles, and known affiliations.",
    "value": []
  },
  "fraudulent_platform_operation": {
    "definition": "Description of the trading platform or entity's operational facade.",
    "value": {
      "platform_name": "",
      "claimed_registration_jurisdiction": "",
      "actual_operational_jurisdiction": "",
      "software_used": ""
    }
  },
  "fraudulent_product_service": {
    "definition": "Detailed description of the fraudulent Forex/Binary Options offering.",
    "value": {
      "product_type": "(e.g., Managed Forex Account, Binary Options Signals Service, Automated Trading Robot)",
      "claimed_instrument": "(e.g., Currency pairs, Stock indices)",
      "claimed_trading_strategy": "(e.g., Algorithmic arbitrage, AI-powered signals)",
      "features_of_fraud": "(e.g., Software manipulation, Fake trade history, Misrepresented liquidity)"
    }
  },
  "marketing_and_recruitment_strategy": {
    "definition": "Methods used to attract and persuade investors.",
    "value": {
      "channels": ["(e.g., Social media ads, YouTube influencers, Seminars, Cold calls)"],
      "key_messages": ["(e.g., Guaranteed high returns, Low risk, Professional fund managers)"],
      "target_demographics": "(e.g., Retail investors with limited trading experience)",
      "use_of_fake_testimonials": "(Boolean and description)"
    }
  },
  "investment_process": {
    "definition": "How investors were onboarded and deposited funds.",
    "value": {
      "deposit_methods": ["(e.g., Wire transfer, Cryptocurrency, Credit card)"],
      "minimum_investment": "",
      "account_management": "(e.g., Investors given login to a platform showing fake balances)"
    }
  },
  "returns_promises_and_mechanics": {
    "definition": "The specific promises made to investors and the illusory mechanism of returns.",
    "value": {
      "promised_return_structure": "(e.g., '80% monthly profit', 'Fixed 15% weekly payout')",
      "claimed_source_of_returns": "(e.g., 'Successful forex trades', 'Binary options wins')",
      "initial_payment_phase": "Description of how initial 'returns' were paid to early investors to build credibility.",
      "withdrawal_restrictions": "(e.g., High fees, mandatory rollover periods, impossible verification hurdles)"
    }
  },
  "actual_fraud_mechanism": {
    "definition": "The true nature of the fraudulent operation.",
    "value": {
      "funds_misappropriation": "(Boolean and description of personal use by perpetrators)",
      "software_manipulation": "(Boolean and description of platform rigging, e.g., price feeds, execution delays)",
      "ponzi_scheme_element": "(Boolean. Were new deposits used to pay 'returns' to earlier investors?)",
      "fake_trade_reporting": "(Boolean. Were trade confirmations and account statements fabricated?)"
    }
  },
  "event_timeline_and_scale": {
    "definition": "Key temporal milestones and quantitative scale of the fraud.",
    "value": {
      "launch_date": "YYYY-MM-DD or estimate",
      "peak_operation_period": "",
      "collapse_date": "YYYY-MM-DD or estimate",
      "duration_months": 0,
      "estimated_investor_count": 0,
      "estimated_total_investment_fiat": "(Total fiat currency equivalent collected)",
      "geographic_reach": ["Countries primarily affected"]
    }
  },
  "collapse_catalyst": {
    "definition": "The immediate trigger that caused the scheme to unravel.",
    "value": {
      "trigger": "(e.g., Regulatory action, liquidity crisis, whistleblower, media investigation)",
      "date": "YYYY-MM-DD or estimate",
      "description": ""
    }
  },
  "post_collapse_state": {
    "definition": "The status at the moment of collapse.",
    "value": {
      "platform_status": "(e.g., Website offline, accounts frozen)",
      "perpetrator_status": "(e.g., Fugitive, arrested, whereabouts unknown)",
      "investor_funds_status": "(e.g., Trapped in platform, seized by authorities)",
      "last_known_perpetrator_assets": "Estimated funds recoverable at collapse"
    }
  },
  "impact_analysis": {
    "definition": "The consequences for all involved parties.",
    "value": {
      "investor_impacts": {
        "total_estimated_loss": "",
        "average_individual_loss": "",
        "percentage_of_investors_lossing_principal": "Estimate",
        "non_financial_harms": ["(e.g., Psychological distress, family conflict)"]
      },
      "regulatory_and_legal_actions": {
        "actions_taken": ["(e.g., Cease and desist orders, criminal charges, civil suits)"],
        "agencies_involved": [],
        "case_status": "(e.g., Ongoing, settled, convictions obtained)"
      },
      "broader_market_impact": {
        "impact": "(e.g., Erosion of trust in retail forex, tighter regulations for binary options)"
      }
    }
  },
  "data_source_attribution": {
    "definition": "A list of the key sources (from the provided input data) that informed critical parts of this simulation. This is crucial for auditability.",
    "value": []
  }
}
```

### **Instructions for Execution**
1.  Thoroughly analyze all provided source materials related to the specific **Forex / Binary Options Fraud** case.
2.  Extract and cross-reference facts, figures, claims, and outcomes.
3.  Fill the JSON structure meticulously, ensuring every field's value is supported by the source data or logical deduction labeled as such.
4.  Maintain a neutral, analytical tone. Avoid speculative language.
5.  **Output ONLY the raw JSON object.** Do not include any explanatory text, introductions, or conclusions outside the JSON structure.

"""