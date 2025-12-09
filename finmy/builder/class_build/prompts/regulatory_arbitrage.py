
def regulatory_arbitrage_prompt(text: str) -> str:
    return """
You are an expert financial analyst, regulatory specialist, and forensic investigator specializing in deconstructing and simulating complex financial events involving regulatory arbitrage. Your task is to reconstruct a complete, detailed, and fact-based narrative of a specified regulatory arbitrage event based on the provided multi-source data (e.g., parsed web content, PDF documents, news articles, regulatory filings, academic papers, court documents).

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of the regulatory arbitrage scheme. Your output must be a structured JSON that meticulously documents the event's background, design, execution, discovery, and consequences, with a focus on how regulatory gaps or differences were exploited.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Fact-Based Synthesis**: Integrate information from all provided sources. Resolve contradictions by prioritizing official regulatory reports, court judgments, and audited financial statements. Note significant discrepancies in the `simulation_analysis_notes.data_discrepancies` field.
2.  **Temporal & Causal Logic**: Maintain a strict chronological order. Explicitly link (a) regulatory environments and loopholes to the scheme's design, (b) the execution strategy to its financial and market impact, and (c) triggering events to the eventual unwinding or crackdown.
3.  **Financial & Regulatory Logic**: Clearly model the capital, risk, liquidity, or reporting advantages sought versus the actual economic substance. Distinguish between *claimed compliance* and *actual regulatory exposure*. Quantify impacts where possible.
4.  **Multi-Actor Perspective**: Analyze the event from the perspectives of the executing entity, regulators, investors, counterparties, and the broader financial system.

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON.

```json
{
  "regulatory_arbitrage_simulation_report": {
    "metadata": {
      "event_name": "string | The commonly recognized name of the event (e.g., 'The London Whale', 'Certain Structured Investment Vehicle (SIV) activities pre-2008').",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation (e.g., '2025-12-09').",
      "data_sources_summary": "array[string] | Brief list of primary data sources used (e.g., ['SEC Final Order 34-12345', 'Basel Committee Report on Banking Supervision', 'Company 10-K Filing for FY20XX', 'Senate Subcommittee Hearing Transcript']).",
      "primary_jurisdictions_involved": "array[string] | List of countries/regions where the arbitrage was executed or whose regulations were central (e.g., ['United States', 'European Union', 'United Kingdom', 'Offshore Financial Center X']).",
      "core_financial_sectors": "array[string] | Relevant financial sectors (e.g., ['Banking', 'Shadow Banking', 'Insurance', 'Securitization', 'Derivatives Trading'])."
    },
    "1_overview": {
      "executive_summary": "string | A concise 3-5 sentence summary: the entity involved, the regulatory loophole exploited, the financial mechanic used, the scale, and the ultimate outcome (e.g., market loss, regulatory action, system-wide impact).",
      "event_lifecycle": {
        "design_and_inception_period": "string (YYYY-YYYY) | Period when the arbitrage strategy was conceived and initially deployed.",
        "active_exploitation_period": "string (YYYY-YYYY) | Period during which the strategy was actively used to gain advantage.",
        "crisis_unwind_discovery_date": "string (YYYY-MM-DD or YYYY-MM) | Key date(s) when the strategy failed, was discovered by regulators, or began to unravel publicly.",
        "resolution_period": "string (YYYY-YYYY) | Period of regulatory response, legal proceedings, and market adjustment."
      }
    },
    "2_entities_and_key_actors": {
      "primary_entity_executing_arbitrage": {
        "name": "string | The legal entity (e.g., bank, hedge fund, SPV) that designed and executed the strategy.",
        "type": "string | e.g., 'Global Systemically Important Bank (G-SIB)', 'Investment Bank', 'Special Purpose Vehicle (SPV)', 'Hedge Fund'.",
        "motivation": "string | Primary driver (e.g., 'Boost reported capital ratios (Tier 1)', 'Reduce Risk-Weighted Assets (RWA)', 'Avoid liquidity coverage requirements', 'Lower tax liability', 'Circumvent leverage limits')."
      },
      "key_decision_makers_and_roles": "array[object] | List of individuals/groups within the entity responsible. Each object: {'name_or_title': 'string', 'role': 'string (e.g., Head of Trading, CFO, Chief Risk Officer)', 'involvement_description': 'string'}",
      "external_enablers": "array[object] | List of external parties that facilitated the arbitrage (e.g., law firms, auditors, rating agencies). Each object: {'name': 'string', 'type': 'string', 'role_played': 'string'}",
      "regulatory_bodies_involved": "array[object] | List of regulators whose rules were gamed or who later intervened. Each object: {'name': 'string (e.g., SEC, PRA, Fed)', 'jurisdiction': 'string', 'primary_regulatory_framework': 'string (e.g., 'Basel III', 'Dodd-Frank', 'IFRS 9')'}"
    },
    "3_regulatory_landscape_and_loophole": {
      "regulatory_gap_exploited": "string | Detailed description of the specific difference, inconsistency, or lack of regulation between jurisdictions, entities, or products that was exploited.",
      "intended_regulatory_outcome_vs_form": {
        "substance_of_economic_activity": "string | The actual economic risk, activity, or exposure.",
        "regulatory_treatment_sought": "string | How the activity was structured to be classified for regulatory purposes (e.g., 'Booking trades in a jurisdiction with lower capital charges', 'Using an SPV to move assets off-balance-sheet', 'Using internal models to lower RWA').",
        "difference_created": "string | Quantify or describe the advantage gained (e.g., 'Reduced capital requirement by 80%', 'Avoided $X billion in liquidity reserves')."
      }
    },
    "4_execution_mechanism_and_financial_engineering": {
      "financial_instruments_used": "array[string] | Specific instruments (e.g., ['Credit Default Swaps (CDS)', 'Collateralized Loan Obligations (CLOs)', 'Repurchase Agreements (Repo)', 'Total Return Swaps', 'Special Purpose Entities']).",
      "transaction_structure": "string | Step-by-step description of how the arbitrage was operationally executed. Include flow of funds, assets, and risk.",
      "booking_locations_and_legal_vehicles": "array[object] | Where and through what legal structures transactions were booked. Each object: {'location': 'string', 'vehicle_name_type': 'string', 'purpose_in_arbitrage': 'string'}",
      "accounting_and_reporting_treatment": "string | How the transactions were accounted for (GAAP/IFRS) and reported in financial statements and regulatory filings."
    },
    "5_scale_impact_and_risk_accumulation": {
      "peak_exposure_or_scale": {
        "notional_value_involved": "string | Approximate notional amount of the arbitrage activity at its peak (e.g., '$100B notional CDS portfolio').",
        "risk_transferred_or_concealed": "string | Description and estimated size of the risk that was effectively hidden or misrepresented (e.g., '$20B in credit risk removed from balance sheet').",
        "regulatory_capital_benefit_claimed": "string | Estimated capital, leverage, or liquidity benefit reported by the entity due to the arbitrage."
      },
      "true_economic_risk": "string | Analysis of the actual, unmitigated risk that remained with the entity or the financial system.",
      "financial_performance_impact": {
        "reported_profits_inflated_by": "string | Estimate of how much reported earnings were enhanced by the arbitrage.",
        "funding_cost_advantages": "string | Any reduction in funding costs achieved."
      },
      "systemic_risk_contributions": "string | How this activity contributed to opacity, interconnectedness, or vulnerability in the broader financial system."
    },
    "6_discovery_unwind_and_crisis": {
      "trigger_for_discovery": {
        "internal_trigger": "string | e.g., 'Large market moves causing losses', 'Whistleblower report', 'Internal audit finding'.",
        "external_trigger": "string | e.g., 'Regulatory examination', 'Market counterparty concerns', 'Academic or media analysis', 'Broader financial crisis revealing weaknesses'."
      },
      "unwind_process": "string | Description of how the arbitrage position was unwound, closed, or forcibly terminated. Was it orderly or a fire sale?",
      "realized_losses_and_costs": {
        "direct_financial_loss_to_entity": "string | Monetary loss from unwinding (e.g., '$6.2B trading loss').",
        "regulatory_fines_and_penalties": "string | Total fines levied.",
        "litigation_and_settlement_costs": "string"
      },
      "liquidity_and_solvency_impact": "string | Impact on the entity's liquidity position and solvency during the unwind."
    },
    "7_regulatory_and_legal_aftermath": {
      "enforcement_actions": {
        "regulatory_sanctions": "array[object] | List of actions by regulators. Each object: {'agency': 'string', 'action': 'string (e.g., 'Cease and Desist', 'Capital Directive', 'Fine')', 'details': 'string'}",
        "criminal_or_civil_charges": "array[object] | List of charges against entities or individuals. Each object: {'charges': 'string', 'defendant': 'string', 'outcome': 'string'}",
        "individual_accountability": "string | Summary of consequences for key actors (e.g., 'Fired', 'Banned from industry', 'Personal fines')."
      },
      "regulatory_reforms_prompted": {
        "specific_rule_changes": "array[string] | New rules or amendments introduced to close the exploited loophole (e.g., 'Basel III revisions to securitization framework', 'Dodd-Frank Volcker Rule provisions on proprietary trading').",
        "supervisory_practice_changes": "array[string] | Changes in regulatory examination focus or methodology."
      },
      "market_practice_changes": "array[string] | How industry behavior changed in response (e.g., 'Reduced use of certain SPV structures', 'Increased margin requirements for specific trades')."
    },
    "8_broader_implications_and_analysis": {
      "impact_on_investors_and_counterparties": "string | How shareholders, bondholders, and trading counterparties were affected (losses, loss of confidence).",
      "impact_on_market_integrity": "string | Effect on perceptions of fairness, transparency, and trust in the financial system.",
      "lessons_for_corporate_governance": "array[string] | Key takeaways regarding risk management, internal controls, and board oversight.",
      "comparison_to_similar_arbitrage_events": "string | Brief contextual comparison to other historical regulatory arbitrage cases."
    },
    "9_simulation_analysis_notes": {
      "key_red_flags_missed_by_management_regulators": "array[string] | List of internal or external warning signs that were ignored.",
      "sustainability_of_the_arbitrage": "string | Analysis of why the strategy was inherently unstable or doomed to be discovered.",
      "data_discrepancies": "array[string] | Note any major conflicting information from sources regarding figures, dates, or responsibilities.",
      "ethical_considerations": "string | Brief analysis of the ethical boundary between legal optimization and deceptive practice in this case.",
      "simulation_confidence_level": "string | High/Medium/Low based on data quality, consistency, and transparency of the event."
    }
  }
}
```

### **INSTRUCTION FOR EXECUTION**
1.  **Thoroughly Analyze** all provided source data pertaining to the requested regulatory arbitrage event (e.g., "The use of Special Purpose Vehicles to arbitrage Basel I capital requirements").
2.  **Extract and Synthesize** information to populate every field in the JSON schema above. If precise data for a field is unavailable from sources, make a clear, reasoned estimation based on context and note this in `simulation_analysis_notes.data_discrepancies`. Never invent facts.
3.  **Ensure Logical Flow** across sections. The report should read as a coherent story: from the regulatory environment, to the entity's motivation and design, to execution and scaling, to the trigger for discovery, and finally to the aftermath and reforms.
4.  **Maintain an Analytical Tone**. Focus on explaining the "how" and "why," not just the "what."
5.  **Output ONLY** the raw JSON object, beginning with `{` and ending with `}`. Do not use markdown code block syntax in your final output.
```


"""