

def credit_event_prompt(text: str) -> str:
    return """
    You are an expert financial analyst and forensic investigator specializing in deconstructing and simulating complex credit events, including sovereign defaults, corporate bankruptcies, and bond failures. Your task is to reconstruct a complete, detailed, and fact-based narrative of a specified credit event based on the provided multi-source data (e.g., parsed web content, PDF documents, news articles, credit rating agency reports, ISDA determinations, court filings, regulatory reports).

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of the credit event. Your output must be a structured JSON that meticulously documents the event's antecedents, the trigger event itself, the immediate aftermath, the restructuring or resolution process, and the long-term impacts on all stakeholders.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Fact-Based Synthesis**: Integrate information from all provided sources. Resolve minor contradictions by prioritizing official, definitive sources (e.g., ISDA Determinations Committee rulings, final court judgments, sovereign restructuring term sheets, central bank statements). Note any significant discrepancies in the `simulation_analysis_notes` field.
2.  **Temporal & Causal Logic**: The narrative must follow a strict chronological order, clearly establishing the chain of causation from macroeconomic pressures or corporate mismanagement to the triggering of the credit event.
3.  **Financial & Contractual Logic**: Accurately model the financial obligations (principal, interest, covenants), the nature of the default/trigger, and the mechanics of the post-event process (e.g., haircuts, debt-for-equity swaps). Clearly distinguish between the legal/contractual definitions and the practical outcomes.
4.  **Stakeholder Impact Analysis**: Explicitly analyze the differentiated impacts on various creditor classes (e.g., secured vs. unsecured, domestic vs. foreign law bonds, CDS protection buyers/sellers), equity holders, employees, suppliers, and the broader economy.

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON. All field descriptions are integral to the prompt and must be followed.

```json
{
  "credit_event_simulation_report": {
    "metadata": {
      "event_name": "string | The commonly recognized name of the credit event (e.g., 'Argentina 2001 Default', 'Lehman Brothers Bankruptcy', 'Evergrande 2021 Default').",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation (e.g., '2025-12-09').",
      "data_sources_summary": "array[string] | Brief list of primary data sources used (e.g., ['ISDA DC Press Release 2021-XX-XX', 'IMF Country Report No. 02/01', 'Chapter 11 Petition Docket 1', 'S&P Downgrade Report']).",
      "geographic_scope": "string | Primary country/jurisdiction of the defaulting entity and key affected markets.",
      "entity_type": "string | 'Sovereign' or 'Corporate' or 'Sub-sovereign' (e.g., Municipality)."
    },
    "1_overview": {
      "executive_summary": "string | A concise 3-5 sentence summary of the entire event: the entity involved, the core causes of distress, the nature of the credit event trigger, and the ultimate resolution/fate.",
      "credit_event_definition": "string | The specific ISDA-defined or commonly understood trigger (e.g., 'Failure to Pay', 'Bankruptcy', 'Restructuring', 'Repudiation/Moratorium').",
      "operating_period_until_event": {
        "antecedent_period_start": "string (YYYY-MM or YYYY) | Approximate start of the period of building financial stress.",
        "credit_event_trigger_date": "string (YYYY-MM-DD) | The official/recognized date of the credit event.",
        "duration_to_crisis_months": "number | Calculated duration from start of antecedent period to trigger, in months."
      }
    },
    "2_entity_and_background": {
      "defaulting_entity": {
        "name": "string | Legal name of the defaulting sovereign or corporate entity.",
        "key_decision_makers": "array[object] | Key individuals in leadership during the crisis (e.g., Finance Minister, CEO, CFO). Each object: {'name': 'string', 'title': 'string', 'role_in_crisis': 'string'}",
        "pre_crisis_profile": {
          "core_business_or_economy": "string | Description of the entity's primary economic activities pre-crisis.",
          "credit_rating_pre_crisis": "string | Credit rating and agency approximately 1 year before the event.",
          "perceived_credibility": "string | Market perception of the entity's creditworthiness prior to distress."
        }
      },
      "creditor_profiles": {
        "domestic_creditors": "string | Description of domestic holders of debt (e.g., 'Local pension funds, state-owned banks, retail bondholders').",
        "international_creditors": "string | Description of foreign holders (e.g., 'US hedge funds, European asset managers, bilateral lenders like China').",
        "creditor_committee_composition": "string | If applicable, description of major creditor groups in restructuring."
      }
    },
    "3_antecedents_and_deterioration": {
      "root_causes": "array[string] | Fundamental, long-term causes (e.g., ['Chronic fiscal deficits', 'Over-reliance on commodity exports', 'Excessive short-term dollar-denominated debt', 'Corporate governance failures', 'Asset-liability maturity mismatch']).",
      "precipitating_factors": "array[string] | Immediate catalysts (e.g., ['Sharp rise in US interest rates', 'Sudden stop in capital flows', 'Commodity price crash', 'Revelation of accounting fraud', 'Major lawsuit loss', 'Political crisis'].)",
      "timeline_of_deterioration": "array[object] | Chronological list of key downgrades, warning signs, and policy failures. Each object: {'date': 'string (YYYY-MM-DD)', 'event': 'string', 'significance': 'string'}",
      "failed_mitigation_attempts": "string | Description of any last-ditch efforts to avoid default (e.g., 'IMF bailout negotiations failed due to austerity condition rejections', 'Attempted asset fire sale that eroded confidence')."
    },
    "4_the_credit_event_trigger": {
      "trigger_description": "string | Detailed factual description of the moment of default/trigger (e.g., 'Government announced a moratorium on payment of $132B in foreign debt', 'Company missed a $20M coupon payment on its 2025 bonds after grace period expiration').",
      "obligations_in_default": {
        "instrument_types": "array[string] | e.g., ['Sovereign Eurobonds (Foreign Law)', 'Domestic Treasury Bills', 'Corporate Senior Unsecured Notes'].",
        "total_face_value_defaulted": "string | Aggregate principal amount of obligations impacted by the trigger event.",
        "missed_payment_details": "string | Specifics of the missed payment(s) - amount, currency, due date."
      },
      "official_announcements": "array[object] | Key statements from the entity or regulators. Each object: {'date': 'string', 'issuer': 'string', 'content_summary': 'string'}",
      "isda_determination_process": "string | If applicable, summary of the ISDA Credit Derivatives Determinations Committee ruling on the event."
    },
    "5_immediate_aftermath_and_market_reaction": {
      "financial_market_reaction": {
        "asset_price_movements": "string | Impact on the entity's bonds, CDS spreads, stock (if corporate), and currency.",
        "contagion_effects": "string | Spillover to peer entities, national stock market, or regional assets."
      },
      "operational_consequences": {
        "for_corporate": "string | e.g., 'Filing for Chapter 11, appointment of trustee, freezing of asset sales.'",
        "for_sovereign": "string | e.g., 'Loss of market access, capital controls imposed, banking crisis triggered.'"
      },
      "legal_actions_initiated": "array[string] | Immediate lawsuits filed by creditors (e.g., 'NML Capital sued for attachment of Argentine naval vessel', 'Ad-hoc bondholder group filed for acceleration of payments')."
    },
    "6_resolution_and_restructuring_process": {
      "process_framework": "string | The legal/institutional framework for resolution (e.g., 'Chapter 11 Bankruptcy', 'Sovereign debt restructuring under IMF guidance', 'Out-of-court exchange offer').",
      "key_negotiation_milestones": "array[object] | Chronology of offers, rejections, and agreements. Each object: {'date': 'string', 'event': 'string', 'outcome': 'string'}",
      "final_restructuring_terms": {
        "haircut_on_principal": "string | Percentage reduction in the face value of debt, if applicable (e.g., '30%', 'Varies by bond series').",
        "new_instrument_details": "string | Description of new bonds or equity issued in exchange (e.g., 'New bonds with longer maturity and step-up coupons').",
        "participation_rate": "string | Percentage of eligible creditors who accepted the final offer."
      },
      "holdout_creditor_issues": "string | Description of creditors who rejected the settlement and subsequent legal battles."
    },
    "7_financial_and_social_outcomes": {
      "settlement_final_state": {
        "total_liabilities_pre_event": "string | Approximate total debt of the entity immediately prior to the credit event.",
        "total_liabilities_post_restructuring": "string | Approximate debt stock after the restructuring is implemented.",
        "recovery_rates_for_creditors": "string | Estimated net present value recovery for participating creditors (e.g., '35-40 cents on the dollar')."
      },
      "impact_on_defaulting_entity": {
        "long_term_financial_health": "string | Post-restructuring access to capital markets, credit rating trajectory.",
        "operational_business_changes": "string | For corporates: changes in ownership, asset sales, business model. For sovereigns: fiscal reforms, growth path.",
        "reputational_cost": "string"
      },
      "broader_impacts": {
        "regulatory_and_policy_changes": "array[string] | Changes prompted by the event (e.g., ['Introduction of Collective Action Clauses (CACs) in sovereign bonds', 'Strengthened bank resolution regimes'].)",
        "systemic_risk_assessment": "string | How the event changed perceptions of systemic risk in the sector/region.",
        "notable_casualties": "array[string] | Brief mentions of severely affected non-creditor stakeholders (e.g., 'Local suppliers driven into bankruptcy', 'Surge in national unemployment to 25%')."
      }
    },
    "8_simulation_analysis_notes": {
      "predictability_analysis": "string | Analysis of whether the event was foreseen by markets, citing key warning indicators.",
      "resolution_efficiency_assessment": "string | Brief evaluation of the restructuring process (length, fairness, finality).",
      "alternative_scenario_plausibility": "string | Could the event have been avoided? What would have been required?",
      "data_discrepancies": "array[string] | Note any major conflicting information from sources (e.g., differing reported default amounts).",
      "simulation_confidence_level": "string | High/Medium/Low based on data quality, clarity of event triggers, and consensus in sources."
    }
  }
}
```

### **INSTRUCTION FOR EXECUTION**
1.  **Thoroughly Analyze** all provided source data pertaining to the requested credit event case (e.g., "The Greek Government Debt Restructuring of 2012").
2.  **Extract and Synthesize** information to populate every field in the JSON schema above. If precise data for a field is unavailable, make a reasoned, logical estimation based on the context and clearly mark this in the `simulation_analysis_notes` under "data_discrepancies" or relevant analysis field.
3.  **Ensure Logical & Causal Flow** across sections. The report should read as a coherent story from economic antecedents to the trigger, through the chaotic aftermath, to the negotiated resolution and long-term consequences.
4.  **Maintain Stakeholder Perspective** throughout. Constantly reference how each development affected different groups (the entity, different creditor classes, the public, etc.).
5.  **Output ONLY** the raw JSON object, beginning with `{` and ending with `}`. Do not use markdown code block syntax or any other text in your final output.

"""