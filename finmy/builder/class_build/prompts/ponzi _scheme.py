


def ponzi_scheme_prompt(text: str) -> str:

    return """
You are an expert financial analyst and forensic investigator specializing in deconstructing and simulating complex financial frauds, particularly Ponzi schemes. Your task is to reconstruct a complete, detailed, and fact-based narrative of a specified Ponzi scheme event based on the provided multi-source data (e.g., parsed web content, PDF documents, news articles, court filings, regulatory reports).

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of the Ponzi scheme. Your output must be a structured JSON that meticulously documents the event's origin, mechanics, key events, collapse, and aftermath.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Fact-Based Synthesis**: Integrate information from all provided sources. Resolve minor contradictions by prioritizing official documents (e.g., court judgments, SEC filings). Note any significant discrepancies in the `analysis_notes` field.
2.  **Temporal Logic**: The narrative must follow a strict chronological order. All dates, durations, and sequences must be logically consistent.
3.  **Financial Logic**: Model the financial flows (investments, promised returns, actual payouts, misappropriation) with internal consistency. Clearly distinguish between *claimed* and *actual* numbers.
4.  **Causal Links**: Explicitly link causes and effects (e.g., how promotion led to investor influx; how payout pressures led to scheme expansion).

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON.

```json
{
  "ponzi_scheme_simulation_report": {
    "metadata": {
      "scheme_name": "string | The commonly recognized name of the fraud (e.g., 'Madoff Investment Scandal').",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation.",
      "data_sources_summary": "array[string] | Brief list of primary data sources used (e.g., ['SEC Complaint 08-cv-10791', 'DOJ Press Release Dec 2008', 'Trustee's 5th Interim Report']).",
      "geographic_scope": "string | Primary countries/regions where the scheme operated."
    },
    "1_overview": {
      "executive_summary": "string | A concise 3-5 sentence summary of the entire scheme: what it purported to be, its core fraudulent mechanism, scale, and ultimate fate.",
      "operating_period": {
        "start_date": "string (YYYY-MM or YYYY) | Approximate start date of fraudulent solicitation.",
        "end_date": "string (YYYY-MM-DD) | Date of collapse/regulatory intervention.",
        "duration_years": "number | Calculated duration in years."
      }
    },
    "2_origin_and_actors": {
      "primary_perpetrator": {
        "name": "string | Name of the key individual architect.",
        "entity_name": "string | The legal entity used (e.g., Bernard L. Madoff Investment Securities LLC).",
        "background": "string | Relevant pre-scheme background that lent credibility."
      },
      "key_associates": "array[object] | List of major accomplices (e.g., CFO, head of sales). Each object: {'name': 'string', 'role': 'string', 'involvement': 'string'}",
      "victim_profile": {
        "demographic": "string | General description of typical investors (e.g., 'retirees, hedge funds, charities').",
        "accreditation_status": "string | Were investors predominantly accredited/sophisticated or retail?"
      }
    },
    "3_fraudulent_product_and_promotion": {
      "claimed_product_service": "string | Detailed description of the fake investment product or strategy (e.g., 'Split-strike conversion strategy', 'High-yield CDs').",
      "promotion_channels": "array[string] | Methods used for marketing (e.g., ['Exclusive referral networks', 'False auditor websites', 'Seminars at luxury venues', 'Fake performance statements']).",
      "key_lies_and_misrepresentations": "array[string] | List specific false claims (e.g., 'Guaranteed 10-12% annual returns', 'SEC-reviewed', 'AAA-rated')."
    },
    "4_investor_acquisition_and_mechanics": {
      "investment_process": "string | How an investor would typically invest (e.g., 'Sign limited partnership agreement, wire funds to designated bank account').",
      "typical_investment_amount_range": "string | e.g., '$50,000 minimum, often $1M+'",
      "promised_return_terms": "string | Detailed promised returns (e.g., '1-2% per month, consistently, regardless of market conditions').",
      "payout_method_to_investors": "string | How returns were distributed (e.g., 'Regular monthly/quarterly wires', 'Fake account statements showing growth').",
      "evidence_of_legitimate_business": "string | Description of any minimal legitimate business activity, if any, used as a front."
    },
    "5_financial_engine_and_misappropriation": {
      "claimed_use_of_funds": "string | Where investors were told their money would be invested.",
      "actual_use_of_funds": {
        "for_ponzi_payouts": "boolean | True/False if used to pay fake returns.",
        "for_perpetrator_lifestyle": "string | Description of luxuries purchased (e.g., 'mansions, yachts, art').",
        "for_operational_facade": "string | Costs to maintain the illusion (e.g., 'rent for prestigious office, fake audit fees').",
        "other_misappropriation": "string"
      },
      "new_vs_old_investor_flow_analysis": "string | Description of how new investments were critical to sustaining payouts to old investors."
    },
    "6_growth_and_collapse": {
      "scale_at_peak": {
        "estimated_investors": "number | Approximate number of investor accounts.",
        "estimated_total_inflows": "string | Total sum of money received from investors (e.g., '$64.8B').",
        "peak_date_period": "string"
      },
      "collapse_trigger": {
        "primary_cause": "string | The immediate trigger (e.g., 'Massive redemption requests during 2008 financial crisis', 'Regulatory investigation', 'Whistleblower').",
        "unable_to_meet_redemptions_date": "string (YYYY-MM-DD) | Key date when payments stopped."
      },
      "final_state_at_collapse": {
        "outstanding_promised_liabilities": "string | The theoretical amount owed to investors based on last statements.",
        "actual_assets_on_hand": "string | Approximate real assets available at collapse.",
        "liquidity_crisis_description": "string"
      }
    },
    "7_legal_and_social_outcomes": {
      "regulatory_criminal_action": {
        "agencies_involved": "array[string] | e.g., ['SEC', 'DOJ', 'FBI'].",
        "charges_filed": "array[string] | e.g., ['Securities Fraud', 'Wire Fraud', 'Money Laundering'].",
        "disposition": "string | Summary of sentences/pleas for the primary perpetrator and key associates."
      },
      "asset_recovery_and_restitution": {
        "total_assets_recovered_for_liquidation": "string | Value of assets seized/frozen by trustee.",
        "estimated_overall_loss_to_investors": "string | Net investor loss after recoveries (estimated).",
        "restitution_process_status": "string | e.g., 'Trustee distributing 5th interim payment, 75% of allowed claims paid back.'"
      },
      "broader_impacts": {
        "regulatory_changes": "array[string] | Policy or rule changes prompted by the scandal.",
        "industry_reputation_impact": "string | Impact on related financial sectors.",
        "notable_victim_stories": "array[string] | Brief mentions of severely affected groups/individuals."
      }
    },
    "8_simulation_analysis_notes": {
      "key_red_flags_missed": "array[string] | List critical warning signs that were overlooked.",
      "scheme_sustainability_analysis": "string | Brief analysis of why the scheme was mathematically doomed.",
      "data_discrepancies": "array[string] | Note any major conflicting information from sources.",
      "simulation_confidence_level": "string | High/Medium/Low based on data quality and consistency."
    }
  }
}
```

### **INSTRUCTION FOR EXECUTION**
1.  **Thoroughly Analyze** all provided source data pertaining to the requested Ponzi scheme case (e.g., "蓝天格锐事件 / Lantian Gerui Event").
2.  **Extract and Synthesize** information to populate every field in the JSON schema above. If precise data for a field is unavailable, make a reasoned estimation clearly marked in the `simulation_analysis_notes`.
3.  **Ensure Logical Flow** across sections. The report should read as a coherent story from origin to aftermath.
4.  **Output ONLY** the raw JSON object, beginning with `{` and ending with `}`. Do not use markdown code block syntax in your final output.


    """