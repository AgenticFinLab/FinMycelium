def other_financial_scam_prompt(text: str) -> str:
    return """ 
You are an expert financial analyst, forensic investigator, and economic historian. Your task is to reconstruct a complete, detailed, and fact-based narrative of a specified **"Other Financial Scam"** event based on provided multi-source data (e.g., parsed web content, PDF documents, news articles, court filings, regulatory reports, academic papers).

An **"Other Financial Scam"** is defined as a deliberate act of financial deception that does not cleanly fit the classical definitions of Ponzi schemes, pyramid schemes, or the other listed categories. It typically involves a unique, complex, or hybrid fraudulent mechanism. Its core characteristic is the intentional creation of a false reality regarding an investment, asset, transaction, or financial condition to illicitly obtain funds or value from victims. Examples could include: long-term fraudulent leasing schemes, complex trade finance frauds, sham royalty or licensing programs, fraudulent pension or insurance schemes not based on a Ponzi structure, or sophisticated forgery-based cons targeting financial institutions.

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of the "Other Financial Scam." Your output must be a structured JSON that meticulously documents the event's origin, unique deceptive mechanics, key events, unraveling, and aftermath.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Fact-Based Synthesis & Source Hierarchy**: Integrate all provided sources. Resolve contradictions using this priority: 1) Official judicial rulings/plea agreements, 2) Regulatory agency findings (SEC, FCA, etc.), 3) Licensed trustee/liquidator reports, 4) Reputable investigative journalism, 5) Other media or forum posts. Document major source conflicts in `analysis.data_discrepancies`.
2.  **Temporal & Causal Logic**: Construct a strict chronological timeline. Clearly articulate cause-and-effect relationships (e.g., how a specific lie enabled fundraising, how a market shift exposed the fraud).
3.  **Financial & Deceptive Logic**: Model the scam's unique financial and deceptive mechanics with internal consistency. Clearly delineate between the **FACADE** (what victims were told/show) and the **REALITY** (what was actually happening). Explain how the scam maintained its illusion without necessarily relying on a "new-investor-pays-old-investor" engine.
4.  **Actor-Centric Analysis**: Identify and analyze the roles, motivations, and knowledge levels of all key actors (perpetrators, facilitators, witting/unwitting agents, victims).

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON.

```json
{
  "other_financial_scam_simulation_report": {
    "metadata": {
      "scam_name": "string | The common name of the event (e.g., 'The Parmalat Fraud').",
      "simulation_date": "string (ISO 8601) | Date this analysis was generated (YYYY-MM-DD).",
      "data_sources_summary": "array[string] | Brief list of the primary data sources used for this simulation.",
      "geographic_scope_primary": "string | Main countries/jurisdictions where the scam was orchestrated and executed.",
      "geographic_scope_victims": "string | Main countries/jurisdictions where victims were located.",
      "scam_type_classification": "string | A descriptive classification of this unique scam (e.g., 'Fraudulent Accounting & Fake Bank Balances', 'Sham Royalty Licensing Program', 'Forged Trade Finance Consortium')."
    },
    "1_overview": {
      "executive_summary": "string | A concise 3-5 sentence summary describing: the facade presented to the world, the core deceptive act(s), the scale, and how it ended.",
      "operating_period": {
        "facade_start": "string (YYYY-MM or YYYY) | When the fraudulent activity or false narrative began.",
        "scam_unravel_start": "string (YYYY-MM-DD or YYYY-MM) | The date or period when the key event triggering the collapse occurred (e.g., default, whistleblower, regulatory query).",
        "public_collapse_date": "string (YYYY-MM-DD) | The date the scam became publicly known or the entity entered administration.",
        "duration_active_years": "number | Estimated number of years the scam operated before unraveling."
      }
    },
    "2_origin_and_key_actors": {
      "primary_perpetrators": "array[object] | List of key individuals who devised and orchestrated the scam. Each object: {'name': 'string', 'title/role': 'string', 'entity_affiliation': 'string', 'background_relevant_to_fraud': 'string'}",
      "fraudulent_entities": "array[object] | The main legal entities used to execute the fraud. Each object: {'entity_name': 'string', 'jurisdiction': 'string', 'stated_purpose': 'string', 'actual_role_in_fraud': 'string'}",
      "key_facilitators": "array[object] | Individuals or entities (e.g., complicit lawyers, corrupt officials, negligent auditors) who enabled the fraud, knowingly or through gross negligence. Each object: {'name': 'string', 'role': 'string', 'nature_of_facilitation': 'string'}",
      "victim_profile": {
        "demographic_categories": "array[string] | Types of victims (e.g., ['Bondholders', 'Banks providing loans', 'Trade creditors', 'Retail investors', 'Pension funds']).",
        "accreditation_status": "string | Predominantly institutional/accredited or retail victims.",
        "basis_of_trust": "string | What led victims to believe the facade (e.g., 'Company's long history', 'Reputable auditor's opinion', 'Complex financial structures mimicking legitimate deals')."
      }
    },
    "3_the_facade_deceptive_mechanism": {
      "core_false_narrative": "string | The central, overarching lie sold to victims and the market (e.g., 'The company had €3.9bn in a liquid bank account', 'A sovereign wealth fund was backing the venture', 'Patented technology generated guaranteed royalties').",
      "fraudulent_product_or_scheme_description": "string | Detailed description of the fake investment, asset, transaction, or financial status that was marketed or reported.",
      "key_supporting_deceptions": "array[object] | The specific fraudulent acts that propped up the core narrative. Each object: {'deception_type': 'string (e.g., Forged Document, Fictitious Revenue, Shell Company Transaction)', 'description': 'string', 'purpose': 'string (e.g., To show liquidity, To inflate earnings, To create a credible counterparty)'}",
      "promotion_and_dissemination_channels": "array[string] | How the false narrative was spread (e.g., ['Fake bank account statements', 'Fraudulent annual reports audited by complicit firm', 'Press releases with false claims', 'Sophisticated presentations to institutional investors'])."
    },
    "4_victim_acquisition_and_financial_flows": {
      "how_victims_provided_funds": "string | The mechanism by which victims transferred value (e.g., 'Purchased corporate bonds', 'Granted loans based on fake collateral', 'Paid upfront licensing fees', 'Extended trade credit based on falsified financials').",
      "typical_financial_commitment_range": "string | The scale of individual victim exposure (e.g., 'Bond purchases from $10k to $50M per institution', 'Bank loans averaging $100M per facility').",
      "promised_return_or_benefit": "string | What victims were explicitly or implicitly promised (e.g., 'Interest payments of 5-7% on bonds', 'Repayment of principal at maturity', 'Royalty streams of 15% per annum', 'Value of goods to be delivered').",
      "method_of_fulfilling_promises_initially": "string | How the scam made payments or showed value in the early/stable phase to maintain credibility (e.g., 'Used new loan proceeds to pay interest on old bonds', 'Used a small fraction of stolen funds to deliver some goods', 'Made royalty payments from principal')."
    },
    "5_financial_engine_and_misappropriation": {
      "claimed_use_of_funds": "string | Where victims were told their money would be used (e.g., 'For working capital and expansion', 'To finance receivables', 'To fund research and development').",
      "actual_use_of_funds": {
        "to_sustain_facade": "string | Funds used to perpetuate the fraud (e.g., 'Making interest payments to earlier victims', 'Paying 'royalties' from new investor capital', 'Funding forgery operations').",
        "for_perpetrator_enrichment": "string | Description of assets purchased or funds diverted for personal gain.",
        "for_operational_costs": "string | Legitimate business costs, if any, of the front operation.",
        "other_diversions": "string"
      },
      "source_of_funds_analysis": "string | Explanation of where the money to run the scam and make any payments came from (e.g., 'Entirely from new victim inflows', 'Partially from legitimate but overstated business income, supplemented by fraud', 'From looting of existing company assets')."
    },
    "6_growth_unraveling_and_collapse": {
      "scale_at_peak": {
        "estimated_number_victim_entities": "number | Approximate number of distinct victim entities (not necessarily individuals).",
        "estimated_total_fraudulent_liabilities_created": "string | Total face value of debts, obligations, or valuations created by the fraud (e.g., '$14bn in fake bank accounts', '$5bn in bonds issued', '$500M in fake invoices').",
        "peak_period": "string"
      },
      "unraveling_trigger": {
        "immediate_catalyst": "string | The specific event that started the collapse (e.g., 'A missed bond interest payment', 'A bank's query about a forged confirmation letter', 'Whistleblower email to regulator', 'A news article investigating discrepancies').",
        "underlying_pressure": "string | The fundamental reason the scam became unsustainable (e.g., 'Cash burn exceeded new fraud inflows', 'Market downturn reduced legitimate revenue cover', 'Increased scrutiny post-Enron').",
        "key_unravel_date": "string (YYYY-MM-DD) | The pivotal date of the triggering event."
      },
      "final_state_at_public_collapse": {
        "total_claimed_assets_per_facade": "string | The asset value reported to the public/victims just before collapse.",
        "estimated_real_assets_available": "string | The approximate actual, traceable assets available to satisfy claims.",
        "immediate_liquidity_crisis_description": "string | What happened when the scam could no longer meet demands (e.g., 'Could not redeem commercial paper', 'Banks froze credit lines', 'Company filed for bankruptcy')."
      }
    },
    "7_aftermath_legal_and_social_outcomes": {
      "legal_regulatory_action": {
        "agencies_involved": "array[string]",
        "primary_charges_indicted": "array[string] | (e.g., ['Securities Fraud', 'Wire Fraud', 'Conspiracy', 'Falsifying Business Records', 'Money Laundering'])",
        "disposition_against_perpetrators": "string | Summary of trials, pleas, and sentences for primary actors.",
        "action_against_facilitators": "string | Summary of outcomes for auditors, lawyers, or others held accountable."
      },
      "asset_recovery_and_creditor_outcomes": {
        "total_assets_recovered_for_liquidation": "string | Value of assets seized/frozen and available for distribution.",
        "estimated_overall_net_loss_to_victims": "string | Estimated total victim loss after expected recoveries.",
        "restitution_bankruptcy_process_status": "string | Description of the recovery process (e.g., 'Bankruptcy court approved plan paying creditors 15 cents on the dollar', 'Litigation against third parties (banks, auditors) ongoing').",
        "recovery_timeline_years": "number | Estimated or actual duration of the asset recovery process."
      },
      "broader_impacts": {
        "regulatory_policy_changes": "array[string] | Changes inspired by this scam (e.g., 'Stricter rules on bank confirmation procedures (Sarbanes-Oxley)', 'Enhanced auditor rotation requirements').",
        "market_or_industry_impact": "string | Impact on specific sectors, investor confidence, or lending practices.",
        "notable_systemic_risks_exposed": "array[string] | Broader financial system vulnerabilities highlighted by the event."
      }
    },
    "8_simulation_analysis_notes": {
      "unique_mechanisms_of_deception": "array[string] | List the innovative or particularly effective deceptive techniques used in this scam.",
      "key_red_flags_missed_by_victims_market": "array[string] | Critical warning signs that were present but overlooked or rationalized.",
      "sustainability_analysis": "string | Analysis of why this specific fraudulent structure was doomed to fail, even if not a classic Ponzi.",
      "data_discrepancies_and_assumptions": "array[string] | Note any major conflicting information from sources and any material assumptions made due to data gaps.",
      "simulation_confidence_assessment": "string | High/Medium/Low, based on data completeness, source reliability, and internal consistency of the reconstructed narrative."
    }
  }
}
```

### **INSTRUCTION FOR EXECUTION**
1.  **Analyze & Synthesize**: Thoroughly process all provided source data for the requested "Other Financial Scam" case.
2.  **Populate the Schema**: Extract information to fill every field in the JSON. If precise data is missing, make logical, evidence-based inferences and **explicitly state these assumptions in `8_simulation_analysis_notes.data_discrepancies_and_assumptions`**.
3.  **Maintain Narrative Coherence**: Ensure the JSON tells a coherent story from `origin` through `facade`, `unraveling`, to `aftermath`. Link fields logically across sections.
4.  **Output Strictly**: Output **ONLY** the raw JSON object, beginning with `{` and ending with `}`. Do not use markdown code block syntax (` ```json `) in your final output.


"""