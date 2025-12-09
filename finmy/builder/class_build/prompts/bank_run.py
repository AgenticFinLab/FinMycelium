

def bank_run_prompt(text: str) -> str:
    return """
    You are an expert financial systemic risk analyst and economic historian specializing in dissecting financial crises, particularly bank runs and liquidity crises. Your task is to reconstruct a complete, detailed, and fact-based narrative of a specified bank run event based on the provided multi-source data (e.g., parsed regulatory filings, news archives, financial statements, post-mortem reports, academic analyses).

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of a bank run. Your output must be a structured JSON that meticulously documents the event's background, triggers, contagion mechanics, resolution, and aftermath. Focus on the dynamics of loss of confidence, liquidity transformation mismatch, and the interplay between solvency and liquidity.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Fact-Based Synthesis**: Integrate information from all provided sources. Resolve contradictions by prioritizing official regulatory reports, central bank communications, and audited financial statements. Note significant discrepancies in `analysis_notes`.
2.  **Temporal & Causal Logic**: The narrative must follow a strict chronological order, clearly identifying preconditions, the triggering event(s), the acceleration phase, and the resolution. Explicitly link cause and effect (e.g., how a specific news article amplified withdrawal requests).
3.  **Financial & Accounting Logic**: Accurately represent key balance sheet items (assets, liabilities, capital), liquidity metrics (LCR, NSFR), and deposit composition. Clearly distinguish between *accounting/book value* and *market/liquidation value* of assets. Model the liquidity drain against the bank's available liquid assets.
4.  **Behavioral & Systemic Dynamics**: Analyze the event as a failure of confidence, highlighting network effects, communication failures, and the role of digital banking/social media in accelerating runs.

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON.

```json
{
  "bank_run_simulation_report": {
    "metadata": {
      "event_name": "string | The commonly recognized name of the bank run (e.g., 'Silicon Valley Bank Collapse 2023').",
      "institution_name": "string | The full name of the bank/financial institution that experienced the run.",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation.",
      "primary_jurisdiction": "string | Country where the bank was primarily regulated.",
      "data_sources_summary": "array[string] | Brief list of primary data sources used (e.g., ['FDIC Failure Report', 'FRB Review of SVB', 'Bank Q4 2022 10-K Filing', 'Twitter API data feed for relevant dates'])."
    },
    "1_preconditions_and_background": {
      "institution_profile_pre_run": {
        "business_model_focus": "string | Core business (e.g., 'Venture capital-backed startup banking', 'Commercial real estate lending').",
        "deposit_base_composition": {
          "total_deposits_amount": "string | Total deposit liabilities pre-crisis (e.g., '$200B').",
          "insured_deposits_percentage": "number | Percentage of deposits under the insurance limit.",
          "concentration": "string | Description of depositor concentration (e.g., 'Heavily concentrated in tech startups and VC firms')."
        },
        "asset_side_risks": {
          "held_to_maturity_securities": "string | Amount and type of HTM securities, and unrealized losses.",
          "loan_book_concentration": "string | Key concentrations in the loan portfolio (e.g., '70% in commercial real estate').",
          "liquidity_coverage_ratio_lcr": "string | Regulatory LCR prior to event, if available."
        },
        "reliance_on_wholesale_funding": "boolean | True if heavily reliant on non-deposit, institutional funding.",
        "recent_stress_indicators": "array[string] | Pre-run warnings (e.g., ['Moody's downgrade watch', 'Rising cost of funds', 'Net interest margin compression'])."
      },
      "macroeconomic_backdrop": "string | Description of the economic environment (e.g., 'Rapidly rising interest rates by the Federal Reserve to combat inflation')."
    },
    "2_trigger_and_ignition": {
      "precipitating_event": {
        "date": "string (YYYY-MM-DD) | The date of the specific trigger.",
        "description": "string | The event that started the loss of confidence (e.g., 'Announcement of a significant loss on sale of securities and a planned capital raise').",
        "source": "string | How the news became public (e.g., '8-K filing with the SEC', 'Leak to financial press')."
      },
      "initial_market_reaction": {
        "stock_price_reaction": "string | e.g., 'Stock price fell 60% in after-hours trading'.",
        "credit_default_swap_spreads": "string | Change in CDS spreads, if applicable.",
        "social_media_sentiment_spike": "string | Qualitative or quantitative measure of online discussion surge."
      },
      "first_mover_withdrawals": {
        "who": "string | Description of the first group to act (e.g., 'Sophisticated venture capital firms advising portfolio companies').",
        "estimated_initial_outflow": "string | Estimated amount of the first wave of withdrawals."
      }
    },
    "3_acceleration_and_contagion": {
      "information_amplification_channels": {
        "traditional_media": "array[string] | Role of news outlets.",
        "social_media_digital": "array[string] | Role of Twitter, WhatsApp groups, Bloomberg chat, etc.",
        "interbank_market_rumors": "string | Rumors in the professional funding market."
      },
      "depositor_behavior_dynamics": {
        "panic_transmission_mechanism": "string | How fear spread among different depositor cohorts (e.g., 'VC to startup to SaaS company network').",
        "digital_banking_effect": "string | Impact of online/instant withdrawal capabilities on speed of run."
      },
      "liquidity_drain_timeline": {
        "requested_withdrawals_timeline": "array[object] | Key milestones. Each object: {'date': 'string', 'cumulative_withdrawal_request_amount': 'string', 'notes': 'string'}",
        "liquid_assets_buffer": "string | Available liquid assets (cash, central bank borrowing capacity) at start of run.",
        "point_of_liquidity_insufficiency": "string | When requested outflows exceeded immediately available liquid assets."
      },
      "management_and_regulator_response_actions": {
        "communication_missteps": "array[string] | Failed attempts to reassure the public (e.g., 'CEO interview seen as out of touch').",
        "liquidity_support_sought": "array[string] | Actions taken (e.g., ['Attempted private capital raise', 'Requested discount window borrowing from Central Bank']).",
        "regulator_engagement_timeline": "array[object] | Key regulator contacts/meetings. Each object: {'date': 'string', 'agency': 'string', 'action': 'string'}"
      }
    },
    "4_resolution_event": {
      "point_of_non_viability": {
        "date_time": "string (ISO 8601) | When regulators determined the bank could not meet obligations.",
        "immediate_cause": "string | The final straw (e.g., 'Unable to process next day's scheduled outgoing wires', 'Run exceeded total deposit base').",
        "closing_agency": "string | e.g., 'FDIC', 'Bank of England'."
      },
      "resolution_method": {
        "method": "string | e.g., 'FDIC receivership and purchase & assumption agreement', 'Bridge bank creation', 'Bail-out with government guarantee'.",
        "acquiring_institution": "string | If applicable, the bank that took over operations.",
        "deposit_handling": "string | How depositors were treated (e.g., 'All depositors, including uninsured, were made whole via systemic risk exception', 'Insured deposits transferred, uninsured claims entered receivership').",
        "shareholder_and_debtholder_treatment": "string | Fate of equity and bondholders (e.g., 'Equity wiped out, AT1 bonds written down to zero')."
      }
    },
    "5_post_mortem_and_impact": {
      "direct_financial_outcomes": {
        "total_deposit_base_at_collapse": "string | Total deposits on the last available balance sheet.",
        "estimated_total_assets_book_value": "string | Book value of total assets.",
        "estimated_asset_market_value_shortfall": "string | Gap between book and fire-sale/market value, if known.",
        "cost_to_deposit_insurance_fund": "string | Estimated loss to the insurance fund.",
        "government_support_extended": "string | Value of any extraordinary government/central bank support."
      },
      "systemic_consequences": {
        "contagion_to_other_institutions": "array[object] | List affected peers. Each object: {'institution_name': 'string', 'mechanism': 'string (e.g., sector sell-off, deposit flight)', 'outcome': 'string'}",
        "market_widening_effects": "array[string] | e.g., ['Regional bank stock index plummeted', 'Short-term funding markets seized up'].",
        "policy_response": "array[string] | Immediate regulatory/central bank actions (e.g., ['Launch of Bank Term Funding Program (BTFP)', 'Emergency liquidity facilities expanded'])."
      },
      "longer_term_analyses": {
        "primary_causes_attributed": "array[string] | Root causes from official reports (e.g., ['Management failure in interest rate risk management', 'Regulatory supervisory lapses', 'Concentrated business model', 'Social media-driven run speed'])",
        "regulatory_reforms_proposed": "array[string] | Changes to capital, liquidity, or resolution rules proposed post-crisis.",
        "industry_business_model_changes": "string | How similar banks adjusted strategies (e.g., 'Increased hedging of HTM portfolios', 'Diversification of deposit base')."
      }
    },
    "6_simulation_analysis_notes": {
      "key_vulnerabilities_exposed": "array[string] | Specific weaknesses in the bank's risk management that were exploited.",
      "critical_inflection_points": "array[string] | Moments where different action could have altered the outcome.",
      "novel_aspects_of_the_run": "string | What made this run different from historical ones (e.g., 'First Twitter-fueled bank run', 'Speed of digital withdrawals').",
      "solvency_vs_liquidity_assessment": "string | Analysis of whether the institution was fundamentally insolvent or purely illiquid at the moment of the run.",
      "data_discrepancies": "array[string] | Note any major conflicting information from sources.",
      "simulation_confidence_level": "string | High/Medium/Low based on data quality and consistency."
    }
  }
}
"""