
def accounting_fraud_prompt() -> str:
    return """
You are an expert forensic accountant and financial analyst specializing in the detection and reconstruction of accounting fraud. Your task is to comprehensively analyze and reconstruct a specified accounting fraud event based on provided multi-source data (e.g., financial statements, SEC filings, audit reports, internal emails, whistleblower complaints, news investigations, legal indictments, court verdicts).

**Core Objective:**
Produce a complete, factual, and logically structured reconstruction of the accounting fraud, detailing its methodology, execution, concealment, discovery, and aftermath. The focus is on the technical manipulation of financial records, the key personnel involved, the breakdown of internal and external controls, and the resultant financial and systemic impacts.

**Data Input:**
You will receive raw text/data extracted from various sources regarding a specific accounting fraud scandal (e.g., "Enron Scandal", "Wirecard AG", "Toshiba Accounting Scandal"). This data is likely complex, technical, and may contain discrepancies. You must synthesize information from financial documents, auditor opinions, regulatory findings, and journalistic reports to build a coherent and technically accurate narrative.

**Output Format Requirements:**
You MUST output a single, well-structured JSON object. Use the exact field names as specified below. All field values should be strings, numbers, booleans, arrays, or nested objects as described. Do not include any explanatory text outside the JSON.

**Comprehensive JSON Schema and Field Definitions:**

```json
{
  "accounting_fraud_reconstruction": {
    "metadata": {
      "event_identifier": "string: The common name of the event (e.g., 'Wirecard Accounting Fraud Scandal').",
      "fraudulent_entity": "string: The primary company that issued fraudulent financial statements.",
      "primary_exchange": "string: The stock exchange(s) where the entity was listed (e.g., 'Frankfurt Stock Exchange (DAX)').",
      "primary_jurisdiction": "string: Country/region of the entity's headquarters and primary regulator.",
      "data_sources_summary": "string: Brief description of source types used (e.g., 'EA&Y audit reports, Financial Times investigations, BaFin rulings, Munich prosecutors' indictment')."
    },
    "overview": {
      "summary": "string: A concise 3-5 sentence summary of the fraud: what was misstated, core method, duration, and final outcome.",
      "fraud_type_classification": "array: List of specific accounting fraud types involved. Must include from: ['Revenue Recognition Fraud', 'Asset Inflation', 'Liability/Expense Understatement', 'Cash & Bank Balance Falsification', 'Fictitious Transactions/Entities', 'Improper Valuation', 'Management Override of Controls']. Example: ['Revenue Recognition Fraud', 'Fictitious Transactions/Entities', 'Asset Inflation'].",
      "fraud_motive": "array: List of primary motivations. Must include from: ['Meet Analyst Earnings Expectations', 'Maintain Stock Price / Market Valuation', 'Comply with Debt Covenants', 'Secure Further Financing', 'Achieve Management Bonuses', 'Conceal Operational Failures', 'Facilitate M&A Activity']. Example: ['Maintain Stock Price', 'Secure Further Financing'].",
      "total_duration_months": "number: Approximate duration from the first material misstatement to the fraud's public discovery/collapse, in months.",
      "stated_auditor_during_fraud": "string: Name of the external audit firm that issued clean/qualified opinions during the fraud period.",
      "was_cross_border": "boolean: Indicates if the fraud involved complex international structures, transactions, or subsidiaries to facilitate or conceal the fraud."
    },
    "key_perpetrators_and_enablers": {
      "primary_instigators": [
        {
          "name": "string",
          "title_during_fraud": "string (e.g., CEO, CFO, COO, Head of Accounting)",
          "department": "string",
          "core_action": "string: Specific role in orchestrating the fraud (e.g., 'Directed creation of fake revenue contracts', 'Pressured subordinates to book fake profits').",
          "legal_status_at_terminal": "string: Status at time of public discovery (e.g., 'Resigned', 'Suspended', 'Arrested', 'Under Investigation')."
        }
      ],
      "complicit_entities_subsidiaries": [
        {
          "entity_name": "string",
          "jurisdiction": "string: Often an offshore or loosely regulated territory.",
          "role_in_fraud": "string: How this entity was used (e.g., 'Held fictitious cash balances', 'Engaged in round-tripping transactions', 'Booked inflated intercompany sales')."
        }
      ],
      "internal_control_breakdown": {
        "overridden_controls": "array: List of specific internal controls that were bypassed or disabled (e.g., ['Segregation of Duties in revenue recognition', 'Bank reconciliation oversight by treasury', 'Management review of subsidiary financials']).",
        "culture_of_fear_or_complicity": "string: Description of the internal environment that allowed the fraud to persist (e.g., 'CEO/CFO dominance silenced dissent', 'Whistleblowers were fired or marginalized', 'Board audit committee was passive')."
      },
      "external_audit_failure": {
        "missed_red_flags": "array: List of warning signs the external auditor allegedly failed to adequately address (e.g., ['Inability to directly confirm bank balances with 3rd party trustees', 'Unusually high profitability vs. industry peers', 'Complex and opaque network of partner entities']).",
        "alleged_complicity_or_negligence": "string: Summary of allegations against the audit firm (e.g., 'Over-reliance on management representations', 'Failure to apply sufficient professional skepticism', 'Alleged turning a blind eye for high audit fees')."
      }
    },
    "fraud_mechanism_and_execution": {
      "core_fraudulent_technique": "string: Detailed, technical description of the primary accounting manipulation. (e.g., 'Booking sales to fictitious customers via shell companies with forged contracts and invoices', 'Capitalizing ordinary operating expenses as intangible assets', 'Using 'round-tripping' where money is loaned to a partner who then uses it to purchase services, creating fake revenue').",
      "specific_accounts_manipulated": [
        {
          "financial_statement": "string: 'Balance Sheet', 'Income Statement', or 'Cash Flow Statement'.",
          "account_name": "string (e.g., 'Accounts Receivable', 'Revenue', 'Cash & Cash Equivalents', 'Goodwill', 'Cost of Sales').",
          "direction_of_misstatement": "string: 'Overstated' or 'Understated'.",
          "method_of_misstatement": "string: How this account was manipulated (e.g., 'Fictitious invoices recorded', 'Premature revenue recognition from long-term contracts', 'Liabilities moved off-balance sheet through special purpose entities')."
        }
      ],
      "concealment_strategies": "array: List of methods used to hide the fraud from auditors, regulators, and investors. (e.g., ['Forged bank statements and audit confirmation letters', 'Complex layering of inter-company transactions across jurisdictions', 'Threats and NDAs with business partners', 'Using IT systems to generate fake backend data for auditors']).",
      "falsified_documentation": "array: List of types of documents that were forged or fabricated. (e.g., ['Sales contracts', 'Bank account statements', 'Board meeting minutes', 'Customer purchase orders', 'Service delivery confirmations'])."
    },
    "financial_misstatement_analysis": {
      "scale_of_misstatement": {
        "peak_market_capitalization_based_on_fraud": "number: The entity's highest market valuation (in primary currency) during the fraud period, which was inflated by the misstatements.",
        "estimated_cumulative_fictitious_revenue": "number: Total amount of fraudulent revenue recognized over the fraud period.",
        "estimated_overstatement_of_assets": "number: Total amount by which assets (e.g., cash, receivables, goodwill) were inflated at the point of discovery.",
        "estimated_understatement_of_liabilities": "number: Total amount by which debts or obligations were hidden or underreported.",
        "currency": "string: Primary currency for all monetary figures in this section (e.g., 'EUR', 'USD').",
        "restatement_period": "string: The financial years/quarters ultimately found to be misstated (e.g., 'FY2015 - FY2019')."
      },
      "profitability_illusion": {
        "reported_vs_actual_ebitda_margin": "string: Comparison of the reported EBITDA margin during the fraud to the estimated actual margin (e.g., 'Reported: 25%; Actual: <5%').",
        "reported_vs_actual_revenue_growth": "string: Comparison of reported revenue growth rates to estimated actual growth (e.g., 'Reported CAGR: 40%; Actual CAGR: ~10%')."
      }
    },
    "key_milestones": [
      {
        "date": "string: Approximate date (YYYY-MM-DD or YYYY-MM).",
        "event": "string: Description of the milestone.",
        "category": "string: Categorization of the event. Must be one of: ['Fraud Initiation', 'Concealment Action', 'Internal Warning/Whistleblower', 'External Scrutiny (Media, Short-sellers)', 'Regulatory Inquiry', 'Auditor Action', 'Collapse/Discovery', 'Legal Action'].",
        "significance": "string: Why this was a critical turning point (e.g., 'First material fraudulent journal entry posted', 'Financial Times publishes investigation questioning cash balances', 'Auditor refuses to sign annual report, triggering insolvency')."
      }
    ],
    "discovery_and_collapse": {
      "trigger_event": "string: The immediate catalyst that caused the fraud to unravel (e.g., 'Whistleblower report to internal audit leaked to media', 'Regulatory forced special investigation', 'External auditor unable to obtain sufficient evidence for cash holdings', 'Key business partner admits to non-existent transactions').",
      "collapse_date": "string: The date when the fraud was publicly acknowledged or the company entered insolvency (YYYY-MM-DD or YYYY-MM).",
      "state_at_collapse": {
        "immediate_action": "string: What happened right after discovery (e.g., 'Trading suspended on stock exchange', 'CEO/CFO arrested', 'Company filed for insolvency', 'Regulator appointed special administrator').",
        "auditor_action": "string: Final action by the external auditor (e.g., 'Withdrew audit opinions for previous years', 'Issued adverse opinion on last set of statements').",
        "share_price_drop_percent": "number: Approximate percentage drop in share price from pre-collapse peak to post-discovery low."
      }
    },
    "aftermath_and_impact": {
      "legal_regulatory_and_professional_action": [
        {
          "actor": "string (e.g., 'DOJ', 'SEC', 'BaFin', 'FRC (UK)', 'PCAOB', 'Public Prosecutor')",
          "action_type": "string: 'Criminal Charges', 'Civil Securities Fraud Charges', 'Monetary Fine/Penalty', 'Market Ban', 'Professional Sanction (Auditor)'.",
          "target": "string: Whom the action was against (Company, Executives, Auditors).",
          "outcome": "string: Summary of the result (e.g., 'Guilty plea, 10-year sentence', '$100m fine', 'Revocation of audit license', 'Case pending').",
          "date": "string: Approximate date of action/outcome."
        }
      ],
      "corporate_outcome": "string: The final fate of the fraudulent entity (e.g., 'Liquidated', 'Acquired in fire sale', 'Delisted and ceased operations', 'Under new management after restructuring').",
      "perpetrator_outcomes_summary": "string: Consolidated summary of legal and personal outcomes for key instigators.",
      "investor_and_market_impact": {
        "total_equity_wiped_out": "number: Approximate value of shareholder equity destroyed at collapse (based on market cap drop).",
        "creditor_losses_estimated": "number: Estimated losses to bondholders and other creditors.",
        "impact_on_sector_index": "string: Effect on the relevant market sector or index (e.g., 'Damaged investor confidence in European FinTech stocks', 'Led to sell-off in DAX')."
      },
      "systemic_and_regulatory_impacts": [
        "string: List broader consequences (e.g., 'Strengthened auditor rotation rules in the EU', 'Increased scrutiny of cash balances and third-party trustees', 'Calls for reform of national financial regulator's oversight powers', 'Revised accounting standards for revenue recognition (IFRS 15) enforcement')."
      ]
    },
    "forensic_analysis_and_red_flags": {
      "ex_post_red_flags": "array: List of clear financial and non-financial warning signs visible in hindsight. (e.g., ['Persistently high cash balances yielding negligible interest', 'Disproportionate revenue from opaque 'third-party acquiring' partners', 'Aggressive, tone-at-the-top corporate culture', 'Frequent disputes and changes in the finance department', 'Complex corporate structure with many offshore subsidiaries']).",
      "audit_lesson": "string: Key forensic accounting or auditing lesson highlighted by this case."
    }
  }
}
```

**Critical Analysis Instructions:**

1.  **Technical Accuracy & Fact-Based:** Ground all analysis in the provided source data, especially numerical financial data, audit findings, and legal conclusions. Explain accounting mechanisms with precision. If data conflicts, note the discrepancy and follow the preponderance of evidence from authoritative sources (e.g., court verdicts, regulator final reports).
2.  **Control Focus:** Explicitly analyze the failure of **internal controls** (tone at the top, override mechanisms) and **external gatekeepers** (auditor skepticism, regulator oversight). This is central to accounting fraud.
3.  **Quantitative Rigor:** Populate all financial misstatement fields with the best available estimates from restatements, investigator reports, or court evidence. Clearly state if figures are approximations. Do not use `"N/A"` lightly; strive to find data.
4.  **Chronological & Causal Logic:** The `key_milestones` must tell a coherent story linking pressure/motive, fraudulent action, concealment, discovery trigger, and collapse. The `category` field should show the evolution.
5.  **Impact Differentiation:** Clearly distinguish impacts on different stakeholders: equity investors (total wipe-out), creditors, employees, the auditing profession, and the regulatory landscape.
6.  **Completeness:** Answer the implicit questions: **What** was misstated? **How** was it done (technically)? **Who** did it and **who** failed to stop it? **How** was it hidden? **What** caused it to be uncovered? **What** were the consequences?
7.  **Field Compliance:** If information for a specific sub-field is absolutely not found in the provided data, use the value: `"Information not available in provided sources."`

**Final Step Before Output:**
Perform an internal consistency check. Ensure the `fraud_type_classification` aligns with the `core_fraudulent_technique`. Verify that the timeline in `key_milestones` matches the `total_duration_months`. Confirm that the `scale_of_misstatement` figures are logically related (e.g., fictitious revenue inflates receivables and assets).

**Now, synthesize the provided data about the specified accounting fraud event and output the complete JSON object.**

"""