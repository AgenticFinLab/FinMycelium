def embezzlement_misappropriation_of_funds_prompt(text: str) -> str:
    return """
You are an expert forensic accountant, financial regulator, and legal analyst specializing in the investigation and reconstruction of complex embezzlement and misappropriation of funds schemes. Your task is to generate a comprehensive, fact-based, and logically consistent simulation of a specified financial embezzlement case based on provided multi-source data (e.g., court documents, audit reports, news articles, internal memos, regulatory filings).

### **CORE OBJECTIVE**
Reconstruct the complete lifecycle of the fund misappropriation event. Your output must be a structured JSON that meticulously details the scheme's setup, execution, concealment, discovery, and consequences, with a sharp focus on the breach of trust, methods of theft, and financial impact.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Primary Source Priority**: Synthesize data from all inputs. Resolve contradictions by prioritizing official legal judgments, regulatory orders, and independent forensic audit reports above other sources.
2.  **Trust Framework**: Clearly establish the legal or fiduciary relationship (e.g., agent-principal, trustee-beneficiary, employer-employee) that was violated. The narrative must hinge on this breach of duty.
3.  **Financial Forensics Logic**: Trace the flow of misappropriated funds with precision. Distinguish between:
    *   **Source Pools**: The original, legitimate funding sources (e.g., client accounts, company revenues, grant funds).
    *   **Diversion Points**: The specific mechanisms (e.g., fraudulent invoices, unauthorized transfers, ghost employees) used to extract funds.
    *   **Final Use**: The ultimate disposition of stolen funds (e.g., personal luxury, covering business losses, other speculative investments).
4.  **Concealment Mechanics**: Explicitly detail the methods (e.g., false accounting entries, forged documents, manipulation of internal controls) used to hide the theft from detection systems and auditors.
5.  **Temporal & Causal Integrity**: Present events in chronological order and clearly link the perpetrator's actions, the concealment tactics, the triggering events for discovery, and the resulting outcomes.

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON.

```json
{
  "embezzlement_simulation_report": {
    "metadata": {
      "case_name": "string | The official or commonly recognized name of the case (e.g., 'ABC Corporation Embezzlement Scandal').",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation.",
      "primary_data_sources": "array[string] | List key sources used (e.g., ['Southern District of NY Indictment No. XX-123', 'SEC Accounting and Auditing Enforcement Release No. YYYY', 'Internal Audit Report Dated 2022-05-15']).",
      "jurisdiction_primary": "string | Primary legal jurisdiction where the case was prosecuted."
    },
    "1_case_overview": {
      "executive_summary": "string | A concise summary (4-6 sentences) describing the nature of the trusted role, the core misappropriation method, the scale, duration, and final status of the case.",
      "key_perpetrators": "array[object] | List of individuals/entities who committed the act. Each object: {'name': 'string', 'title_role_at_time': 'string', 'fiduciary_duty_violated': 'string (e.g., Duty of Care, Duty of Loyalty)'}",
      "victim_entities": "array[object] | List of organizations or funds from which money was stolen. Each object: {'name': 'string', 'type': 'string (e.g., Public Company, Private Trust, Non-Profit, Government Agency)'}",
      "operating_period": {
        "start_date_estimated": "string (YYYY-MM or YYYY) | Estimated start of misappropriation.",
        "end_date_discovery": "string (YYYY-MM-DD) | Date misappropriation was discovered/halted.",
        "duration_months": "number | Calculated duration in months."
      }
    },
    "2_trust_environment_and_opportunity": {
      "perpetrator_authority_level": "string | Detailed description of the perpetrator's official position, granted authorities, and system access (e.g., 'CFO with sole signature authority on bank accounts up to $500k', 'Project manager with ability to approve vendor payments and create new payees').",
      "internal_controls_circumvented": "array[object] | List the specific financial, IT, or operational controls that were overridden or exploited. Each object: {'control_name': 'string (e.g., Dual Signature Requirement, Vendor Master File Review)', 'method_of_circumvention': 'string (e.g., Forged co-signature, Created fake vendor in system)'}",
      "governance_failures": "array[string] | Describe systemic or oversight failures that enabled the scheme (e.g., 'Lack of board audit committee', 'No independent review of executive expenses', 'Over-reliance on a single individual')."
    },
    "3_misappropriation_mechanics": {
      "fund_sources_misappropriated": "array[object] | Detail the origins of the stolen funds. Each object: {'source_name': 'string (e.g., Client Escrow Account, Corporate Operating Account, Research Grant Fund)', 'purpose_of_funds': 'string (e.g., To hold client property taxes, For company payroll, For cancer research)'}",
      "primary_diversion_methods": "array[object] | The specific fraudulent actions used to divert funds. Each object: {'method': 'string (e.g., Fraudulent Invoice/Expense Reimbursement, Unauthorized Wire/ACH Transfer, Ghost Employee/Payroll Fraud, Theft of Cash/Checks)', 'process_description': 'string', 'estimated_frequency': 'string (e.g., Monthly, One-time major transfer)'}",
      "concealment_strategies": "array[object] | The methods used to hide the activity in records. Each object: {'strategy': 'string (e.g., False General Ledger Entries, Forged Bank Statements/Documents, Collusion with Other Employees/Suppliers, Manipulation of Audit Trails)', 'implementation': 'string'}",
      "red_flags_ignored": "array[string] | List specific anomalies that were present but overlooked (e.g., 'Perpetrator living beyond official means', 'Missing original documentation for large expenses', 'Vendor addresses matching perpetrator home address')."
    },
    "4_financial_flows_and_use": {
      "total_amount_misappropriated": "number | The aggregate sum of funds unlawfully diverted, as established by evidence.",
      "disposition_of_funds": {
        "personal_enrichment": {
          "estimated_amount": "number",
          "examples": "array[string] | e.g., ['Purchase of luxury real estate', 'Funding of extravagant lifestyle', 'Personal investment accounts']"
        },
        "business_covering": {
          "estimated_amount": "number",
          "purpose": "string | If used to cover business losses or create false profitability (e.g., 'To meet quarterly revenue targets', 'To pay off other business debts')."
        },
        "other_uses": "array[object] | Any other significant uses. Each object: {'use': 'string', 'estimated_amount': 'number'}"
      },
      "fund_recovery_tracing_challenge": "string | Description of difficulties in tracing funds (e.g., 'Funds commingled in personal accounts', 'Assets transferred to third parties', 'Cash used for untraceable purchases')."
    },
    "5_discovery_and_collapse": {
      "discovery_trigger": {
        "primary_cause": "string | The immediate event leading to discovery (e.g., 'Whistleblower tip', 'Internal audit anomaly', 'External regulatory inquiry', 'Bank alert on suspicious transaction', 'Perpetrator resignation/absence revealing gaps').",
        "date": "string (YYYY-MM-DD)"
      },
      "immediate_response": "array[string] | Actions taken upon discovery (e.g., ['Perpetrator placed on administrative leave', 'Forensic audit firm engaged', 'Regulators notified', 'Assets frozen']).",
      "financial_status_at_discovery": {
        "immediate_financial_impact": "string | The direct effect on victim entity's operations (e.g., 'Unable to meet payroll', 'Client funds missing from escrow', 'Grant project halted').",
        "accounting_gap": "string | The discrepancy found between reported and actual financial position."
      }
    },
    "6_legal_and_restitution_outcomes": {
      "criminal_proceedings": {
        "charges_filed": "array[string] | Legal charges (e.g., ['Embezzlement', 'Wire Fraud', 'Bank Fraud', 'Money Laundering', 'Falsifying Business Records']).",
        "final_disposition": "string | Outcome (e.g., 'Guilty plea to 3 counts of wire fraud', 'Convicted at trial on all counts', 'Sentenced to 10 years imprisonment, ordered to pay $X in restitution').",
        "perpetrator_status": "string | Current status (e.g., 'Incarcerated', 'Released on parole', 'Deceased')."
      },
      "civil_recovery_actions": {
        "lawsuits_filed_by": "array[string] | Entities that filed suits (e.g., ['Company Shareholder Derivative Suit', 'SEC Civil Injunctive Action', 'Trustee in Bankruptcy']).",
        "key_judgments_orders": "array[string] | e.g., ['Permanent injunction barring from serving as officer/director', 'Disgorgement order of $Y plus prejudgment interest']."
      },
      "asset_recovery_and_restitution": {
        "assets_seized_frozen": "array[object] | Assets identified and secured. Each object: {'asset_type': 'string', 'estimated_value': 'number', 'recovery_status': 'string (e.g., Liquidated, Pending sale, Forfeited)'}",
        "total_recovered_to_date": "number | Aggregate value of assets recovered for victims.",
        "estimated_net_loss": "number | Total misappropriated minus total recovered.",
        "restitution_process": "string | Description of victim compensation mechanism and status."
      }
    },
    "7_aftermath_and_impact_analysis": {
      "impact_on_victim_entity": {
        "financial_health": "string | Long-term financial consequences (e.g., 'Forced into Chapter 11 bankruptcy', 'Severe reputational damage leading to lost clients', 'Stock price plummeted 70%').",
        "governance_reforms": "array[string] | Changes implemented post-discovery (e.g., ['Hired new CFO and external auditor', 'Implemented robust whistleblower program', 'Board audit committee now reviews all major expenses'])."
      },
      "broader_impacts": {
        "regulatory_scrutiny_changes": "array[string] | Sector-wide regulatory consequences (e.g., ['New auditing standards for client asset verification', 'Increased regulatory exams for similar entities']).",
        "industry_reputation_damage": "string | Impact on trust within the relevant industry.",
        "notable_victim_stories": "array[string] | Brief mention of severely affected individuals or groups (e.g., 'Pensioners lost retirement savings', 'Charitable programs had to be discontinued')."
      }
    },
    "8_simulation_analysis_notes": {
      "key_control_weaknesses_exploited": "array[string] | Summary of the most critical internal control failures.",
      "concealment_sophistication_assessment": "string | Evaluation of the scheme's complexity (e.g., 'Low: Simple theft with minimal covering; High: Involved complex shell companies and forged audits').",
      "data_discrepancies_noted": "array[string] | Note any major conflicting information from sources.",
      "simulation_confidence_assessment": "string | High/Medium/Low based on completeness and reliability of source data."
    }
  }
}
```

### **INSTRUCTION FOR EXECUTION**
1.  **Analyze All Sources**: Thoroughly process all provided data related to the specified embezzlement case.
2.  **Populate the Schema**: Extract and synthesize information to fill every field in the JSON. If precise data is unavailable, make a **clearly noted, reasoned estimation** in the `simulation_analysis_notes`.
3.  **Maintain Narrative Focus**: Ensure the report consistently emphasizes the **abuse of trust**, the **technical methods of theft and concealment**, and the **forensic and legal pathways** from crime to consequence.
4.  **Output Strictly JSON**: Output **ONLY** the raw JSON object, beginning with `{` and ending with `}`. Do not use markdown code block syntax in your final output.

"""