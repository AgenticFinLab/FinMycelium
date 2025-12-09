def advance_fee_fraud_prompt(text: str) -> str:
    return """
You are a financial event simulation AI tasked with reconstructing an **Advance-Fee Fraud** case based on provided multi-source data (e.g., scraped web content, uploaded PDFs, user-submitted links). Your goal is to generate a **logically coherent, fact-based, and detailed narrative** of the event, covering its entire lifecycle, key actors, mechanisms, impacts, and outcomes.

## Instructions
1. **Data Integration**: Synthesize information from all provided sources. Resolve contradictions by prioritizing official reports, legal documents, or credible investigative journalism.
2. **Factual Accuracy**: Ensure all outputs are grounded in the provided evidence. If specific data points (e.g., exact monetary amounts, dates) are unavailable, explicitly state "Data Not Provided" or "Inferred from Context" and provide a reasoned estimate.
3. **Narrative Structure**: Present the event as a chronological, cause-and-effect story.
4. **Critical Analysis**: Highlight the fraudulent mechanisms, psychological tactics, and systemic vulnerabilities exploited.
5. **Output Format**: Deliver the simulation result **strictly in JSON format** as defined below.

## Required Simulation Output Structure
The JSON must contain the following top-level keys and sub-keys. All field values must be strings, numbers, booleans, arrays, or nested objects—no nulls unless specified.

### JSON Schema Definition

```json
{
  "event_simulation": {
    "metadata": {
      "simulation_id": "A unique identifier for this simulation run, e.g., 'AF-YYYYMMDD-HHMM'",
      "fraud_type": "Advance-Fee Fraud",
      "case_name": "The common name of the simulated case (e.g., '419 Scam Case: Fictitious Inheritance')",
      "simulation_date": "ISO 8601 date of simulation generation",
      "data_sources": ["List of primary data sources used (URLs, document names)"],
      "confidence_level": "High/Medium/Low - indicating confidence in data completeness and accuracy"
    },
    "event_overview": {
      "summary": "A concise paragraph (3-5 sentences) summarizing the entire fraud event from inception to termination.",
      "key_characteristics": ["Array of strings describing hallmarks of this specific advance-fee fraud (e.g., 'Fake lottery winnings', 'Fraudulent loan facilitation', 'Bogus inheritance claim')"]
    },
    "perpetrators": {
      "primary_actor": {
        "name_or_alias": "Name/alias of the main fraudster or group",
        "claimed_identity": "The false identity or entity they portrayed (e.g., 'Bank Official', 'Lawyer', 'Foreign Prince')",
        "actual_identity": "If known, the real identity; otherwise, 'Unknown' or 'Fictitious'"
      },
      "accomplices": [
        {
          "role": "e.g., 'Money Mule', 'Fake Support Agent', 'Document Forger'",
          "description": "How they aided the fraud"
        }
      ],
      "operational_platform": "How they operated (e.g., 'Email Spam Campaign', 'Fake Website', 'Social Media Profiles', 'Phone Calls')"
    },
    "fraud_mechanism": {
      "hook_scenario": "The initial lure or story presented to the victim (e.g., 'You have won a $10M lottery but must pay taxes upfront').",
      "requested_product_or_service": "What the perpetrator falsely offered (e.g., 'Release of locked inheritance funds', 'Approval for a guaranteed large loan', 'Transfer of gold bars')",
      "advance_fee_structure": {
        "fee_types": ["Array of requested fees (e.g., 'Tax Payment', 'Legal Fee', 'Transfer Charge', 'Customs Duty')"],
        "requested_amounts": "Initial and subsequent fee amounts. Can be a range or specific figure.",
        "payment_methods": ["How victims were instructed to pay (e.g., 'Wire Transfer', 'Gift Cards', 'Cryptocurrency')"]
      },
      "promised_benefit": "The larger sum or valuable item promised to the victim upon fee payment.",
      "false_pretense_for_fees": "The fabricated justification for needing the advance payment."
    },
    "propagation_and_recruitment": {
      "target_victim_profile": "Description of the targeted demographic (e.g., 'Elderly individuals', 'Small business owners seeking loans', 'Users of specific online forums').",
      "outreach_methods": ["Mass emails", "Social media ads", "Fake news articles", "Cold calls", "SMS phishing"],
      "persuasion_tactics": ["Array of psychological tactics used (e.g., 'Urgency', 'Authority impersonation', 'Social proof via fake testimonials', 'Flattery')"],
      "fake_documentation_provided": "Were forged documents (contracts, certificates, official letters) used? Boolean and description."
    },
    "event_timeline": {
      "start_date": "Estimated or actual start date of the fraud scheme",
      "peak_activity_period": "When victim recruitment was most active",
      "critical_escalation_events": [
        {
          "date": "Approximate date",
          "description": "Key moment (e.g., 'Introduction of a second fee demand', 'Victim begins to suspect and confronts perpetrator')"
        }
      ],
      "termination_date": "When the scheme effectively ended (e.g., arrest, website takedown)",
      "duration_months": "Total operational duration in months"
    },
    "financial_scope": {
      "estimated_victim_count": "Number of confirmed or estimated victims",
      "estimated_total_advance_fees_collected": "Total sum of fees collected from all victims",
      "average_fee_per_victim": "Calculated average",
      "fee_escalation_pattern": "Description of how fee demands increased over time (e.g., 'Initial $500, then repeated demands for $2000 more')"
    },
    "funds_flow": {
      "promised_use_of_funds": "Where perpetrators claimed the fees would go (e.g., 'To government tax agency', 'For legal processing')",
      "actual_use_of_funds": {
        "personal_enrichment": "Percentage/amount siphoned for personal luxury",
        "operational_costs": "Costs of running the scam (e.g., website hosting, call centers)",
        "funds_recycled": "Were any funds used to pay 'returns' to early victims to build credibility? Boolean and details."
      },
      "money_laundering_channels": "How proceeds were moved and concealed (e.g., 'Through cryptocurrency mixers', 'Via shell companies')"
    },
    "termination": {
      "trigger_event": "What caused the scheme to collapse? (e.g., 'Victim reported to authorities', 'Bank flagged suspicious transactions', 'Investigative journalism expose')",
      "termination_state": {
        "perpetrator_actions": "What the fraudster did at the end (e.g., 'Disappeared', 'Attempted to destroy evidence', 'Fled the country')",
        "victim_awareness": "Were most victims aware it was a fraud at termination? (e.g., 'Some realized, others still believing')",
        "accessible_assets": "Estimated funds remaining in accounts controlled by perpetrators at termination"
      },
      "legal_and_enforcement_action": {
        "arrests": "Were perpetrators apprehended? Boolean and details.",
        "charges_filed": "List of criminal charges (e.g., 'Wire Fraud', 'Money Laundering', 'Conspiracy')",
        "asset_recovery": "Were any funds seized or frozen for restitution?"
      }
    },
    "impact_analysis": {
      "direct_victim_impact": {
        "financial_loss_range": "Min-max loss per victim",
        "psychological_impact": "Common victim repercussions (e.g., 'Shame', 'Debt', 'Loss of trust')",
        "recovery_possibility": "Likelihood of victims recovering funds (e.g., 'Extremely Low')"
      },
      "broader_impacts": {
        "industry_reputation_damage": "Did this affect trust in a legitimate sector (e.g., banking, charities)?",
        "regulatory_changes": "Any new laws or warnings issued because of this or similar cases?",
        "prevention_awareness": "Did it lead to public awareness campaigns?"
      }
    },
    "simulation_metrics": {
      "red_flags_identified": ["Array of key warning signs evident in the simulation (e.g., 'Upfront payment for a windfall', 'Pressure to act quickly', 'Communication only via email')"],
      "systemic_vulnerabilities_exploited": ["e.g., 'Cross-border jurisdictional gaps', 'Difficulty tracing cryptocurrency', 'Public gullibility to authority figures'"],
      "prevention_recommendations": ["2-3 actionable recommendations for potential victims derived from this simulation"]
    }
  }
}
```

## Final Command
Based on all provided source data, generate a complete and detailed simulation of the **Advance-Fee Fraud** case. Ensure the output is **entirely in English**, adheres to the above JSON schema, is wrapped in a markdown code block, and is as comprehensive as the data allows. Begin your output directly with the JSON object.

"""