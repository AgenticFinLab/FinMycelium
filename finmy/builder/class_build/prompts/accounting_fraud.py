
def accounting_fraud_prompt() -> str:
    return """
You are a forensic financial historian and a structured data architect. Your expertise lies in deconstructing complex accounting frauds into their constituent elements across temporal, operational, cultural, and systemic dimensions.

**Objective:** To reconstruct a comprehensive, granular, and deeply analytical profile of a specified accounting fraud case. The output must function as a definitive digital dossier, capturing not only the factual "what" and "who," but the contextual "how" and "why" across the entire lifecycle of the fraud, from its cultural preconditions to its lasting societal impact.

**Output Format:** A single, extensive, and self-contained JSON object. Do not include any explanatory text outside the JSON structure.

**Instructions for JSON Construction:**
1.  **Base Structure:** Follow the provided JSON schema meticulously. Populate every field. If certain information for a field is genuinely unavailable after rigorous consideration, use `null`, but strive for completeness.
2.  **Lifecycle Phases:** The narrative core must be structured according to the six-stage "Failure of Foresight" model. Each stage is a top-level object containing nested objects and arrays that detail its specific themes.
3.  **Granular Fields:** Each field must be populated with highly specific, concrete data. Avoid summaries. Use precise figures, names, dates, direct quotes (sourced), descriptions of specific transactions, internal memo excerpts, regulatory paragraph numbers, etc.
4.  **Integrated Explanation:** For every field, the provided "Explanation" placeholder is a guide for *you* on what to populate. Replace each `"[Explanation]"` string with the actual, detailed data value that fulfills that explanatory prompt. The final JSON should contain *only* data values, not the explanation prompts themselves.
5.  **Fact-Based:** All information must be grounded in verified sources, including court documents, regulatory filings (SEC, FCA, etc.), audit reports, official investigations, credible journalism, and academic studies. Inferences should be clearly stated as such (e.g., "Analysts speculate that...").
6.  **Comprehensiveness:** The JSON must paint a complete picture. Consider: the technical fraud mechanics; the organizational culture that enabled it; the individual actors and their motivations; the failures of internal and external controls; market and media reactions; legal and regulatory consequences; and long-term changes to laws, standards, and professional practices.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "accounting_fraud_reconstruction": {
    "metadata": {
      "scheme_common_name": "[e.g., 'The Enron Scandal', 'The WorldCom Fraud', 'The Satyam Computer Services Fraud']",
      "official_legal_case_name": "[e.g., 'United States v. Jeffrey K. Skilling, et al.', 'SEC v. WorldCom, Inc.', 'CBI vs. B. Ramalinga Raju & Others']",
      "primary_perpetrator_name": "[e.g., 'Bernard Lawrence "Bernie" Madoff', 'Elizabeth "Liz" Holmes', 'B. Ramalinga Raju']. The individual universally acknowledged as the chief architect or driving force.",
      "key_associated_entities": ["[e.g., 'Enron Corp.', 'Arthur Andersen LLP', 'Merrill Lynch (specific desk)']. The core company, its primary subsidiaries used for fraud, and key external enablers (banks, auditors, law firms)."],
      "operational_timeframe": {
        "suspected_inception_year": "YYYY(-MM). The year (and month, if known) the first material fraudulent act occurred.",
        "public_collapse_year": "YYYY(-MM). The year-month the fraud was publicly disclosed, triggering immediate crisis.",
        "duration_years": "X. The calculated span between inception and collapse.",
        "key_milestones": [
          {
            "date": "YYYY-MM-DD",
            "event": "[e.g., 'IPO of the main entity', 'Acquisition of X company used to hide losses', 'First whistleblower report to internal audit']"
          }
        ]
      },
      "estimated_global_scale": {
        "currency": "USD/EUR/GBP/INR/etc.",
        "amount_at_collapse": "XX.XX billion. The total size of fabricated assets, hidden liabilities, or misappropriated funds at the point of discovery.",
        "victim_count_estimate": "XXXXX. The approximate number of direct investors, employees, pensioners, or counterparties financially harmed.",
        "geographic_reach": ["[e.g., 'United States', 'European Union', 'Japan', 'India']. List countries where the entity had material operations, investors, or regulatory issues due to the fraud."],
        "market_cap_loss": "XX.XX billion. The peak-to-trough destruction in shareholder value for the primary entity and key peers."
      },
      "fraud_classification": ["[e.g., 'Revenue Recognition Fraud', 'Asset Overstatement', 'Liability/Expense Understatement', 'Ponzi Scheme', 'Fictitious Sales', 'Round-Tripping']. Use standard accounting fraud typologies."]
    },
    "stage_I_-_-_notionally_normal_starting_point": {
      "cultural_beliefs_context": {
        "prevailing_market_sentiment": "[e.g., 'Dot-com bubble "irrational exuberance"', '"Too big to fail" banking dogma', 'Unquestioning belief in disruptive tech founders']. The macro-economic or sector-specific narrative that lowered skepticism.",
        "industry_specific_norms": "[e.g., 'Mark-to-market accounting for energy trades was nascent and interpretive', 'Software revenue recognition for multi-year contracts was complex']. Accepted practices that contained ambiguity.",
        "regulatory_landscape": "[e.g., 'Pre-Sarbanes-Oxley era with weaker internal control mandates', 'Light-touch regulation for fintech payments processors']. The specific regulatory environment and its perceived gaps."
      },
      "entity_pre_fraud_profile": {
        "public_image": "[e.g., 'Most innovative company in America (Fortune)', 'A fast-growing, profitable blue-chip', 'A trusted, century-old institution']. The media and analyst portrayal before any suspicion.",
        "governance_structure_formal": "[e.g., 'Board with 12 members, including renowned academics', 'Audit committee chaired by a former senator']. The official, published governance framework.",
        "stated_corporate_values": "[e.g., 'Integrity, Communication, Respect, Excellence (from annual report)', '"Radical Transparency"']. The codified ethics and culture statements."
      }
    },
    "stage_II_-_incubation_period": {
      "early_warning_signals_ignored": [
        {
          "date": "YYYY(-MM)",
          "source": "[e.g., 'Internal Auditor', 'Junior Accountant', 'Short-seller report', 'Regulatory query']",
          "signal_description": "[e.g., 'Email to CFO questioning the lack of third-party confirmation for major contract X', 'Analyst report highlighting unsustainable cash flow vs. reported earnings', 'SEC comment letter requesting clarification on related-party transaction Y']",
          "internal_response": "[e.g., 'Whistleblower was reassigned to a different department', 'Management dismissed it as "not understanding the business model"', 'Issue was "clarified" with a legal opinion from a compliant law firm']"
        }
      ],
      "fraud_mechanics_evolution": {
        "initial_method": "[e.g., 'Began with accelerating revenue recognition from legitimate contracts by a few weeks']",
        "escalation_and_complexity": "[e.g., 'Progressed to booking sales to wholly-controlled Special Purpose Entities (SPEs)', 'Created fictitious customers with forged contracts and bank statements']",
        "enabling_internal_controls_failure": {
          "override_of_controls": "[e.g., 'CEO and CFO pressured the accounting department to bypass standard approval workflows']",
          "collusion_departments": "[e.g., 'Sales, Logistics, and Finance worked together to create fake shipping documents and invoices']",
          "it_system_manipulation": "[e.g., 'Direct database access granted to accountants to manually alter receivable balances']"
        }
      },
      "external_gatekeeper_failures": {
        "auditor_actions": "[e.g., 'Relied on management-provided documents without independent verification', 'Ignored specific accounting standards due to "materiality" thresholds', 'Audit partner had a close social relationship with the CFO']",
        "bank_complicity": "[e.g., 'Bank A provided "side letters" confirming cash balances that did not exist', 'Bank B facilitated circular transactions between SPEs to simulate repayment']",
        "analyst_community_stance": "[e.g., 'Maintained "Buy" ratings despite growing discrepancies, due to investment banking relationships', 'Dismissed critical questions in earnings calls as "naive"']",
        "rating_agency_actions": "[e.g., 'Maintained investment-grade rating based on falsified financials, citing "business model strength"']"
      },
      "cultural_decay_within_entity": {
        "tone_at_the_top": "[e.g., 'Aggressive quarterly targets that were impossible to meet legitimately', 'Public humiliation of employees who suggested conservative accounting']",
        "incentive_structure": "[e.g., 'Bonuses solely tied to reported EBITDA, creating immense pressure to manipulate it', 'Stock options that would be worthless if true financials were revealed']",
        "employee_morale_silence": "[e.g., 'Widespread knowledge of "off-book" activities among mid-managers, but fear of job loss prevented reporting', 'Departure of key experienced finance personnel replaced with compliant staff']"
      }
    },
    "stage_III_-_precipitating_event": {
      "trigger_event_description": {
        "date": "YYYY-MM-DD",
        "event_type": "[e.g., 'Whistleblower Goes Public', 'Regulatory Subpoena Served', 'Debt Covenant Breach', 'Key Executive Resignation Unexpectedly']",
        "detailed_narrative": "[e.g., 'A senior vice president, frustrated by internal inaction, sent an anonymous letter with detailed transaction evidence to the SEC and The Wall Street Journal.', 'The company announced it could not file its 10-K on time due to an "internal accounting review," triggering a credit downgrade and stock halt.']",
        "immediate_catalyst": "[e.g., 'The WSJ published a front-page story based on the letter', 'The board's audit committee finally hired an independent forensic firm']"
      },
      "immediate_institutional_reaction": {
        "board_action": "[e.g., 'Placed CEO on administrative leave', 'Formed a special investigation committee']",
        "auditor_action": "[e.g., 'Withdrew previous years' audit opinions', 'Resigned as auditor']",
        "regulatory_action": "[e.g., 'SEC filed an emergency enforcement action seeking an asset freeze', 'Stock exchange delisted the company']",
        "market_reaction": "[e.g., 'Share price fell 95% in two days', 'Credit default swaps exploded']"
      }
    },
    "stage_IV_-_onset": {
      "collapse_sequence": {
        "bankruptcy_filing": {
          "date": "YYYY-MM-DD",
          "chapter": "[e.g., 'Chapter 11', 'Chapter 7', 'Administration (UK)']",
          "listed_assets_liabilities": "Assets: $X billion (likely inflated); Liabilities: $Y billion (likely understated)."
        },
        "operational_cessation": "[e.g., 'All trading floors closed, 20,000 employees laid forthwith', 'Government stepped in to run core infrastructure to prevent systemic collapse']",
        "asset_tracing_complexity": "[e.g., 'Funds were wired through a labyrinth of offshore entities in the Cayman Islands and Cyprus', 'Proceeds were used to purchase illiquid real estate and art']"
      },
      "direct_human_impact": {
        "employee_losses": "[e.g., 'Pension funds wiped out, healthcare terminated', 'Widespread reputational damage for former staff in the industry']",
        "investor_losses": "[e.g., 'Retirees lost life savings invested in company bonds', 'Municipal pension funds faced severe shortfalls']",
        "supplier_creditor_cascade": "[e.g., 'Small business suppliers went bankrupt due to unpaid invoices', 'Counterparty banks took multi-billion dollar write-downs']"
      },
      "public_and_media_frenzy": {
        "narrative_frames": ["[e.g., 'The ultimate corporate betrayal', 'A systemic failure of checks and balances', 'The cult of a charismatic leader']"],
        "key_revelations": ["[e.g., 'The "CEO" had no relevant qualifications', 'The "core technology" was a non-functional prototype']"]
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "immediate_legal_actions": {
        "regulatory_settlements": [
          {
            "agency": "[e.g., 'SEC', 'DOJ', 'FCA']",
            "action": "[e.g., 'Permanent injunction against fraud', 'Civil penalty of $Z billion']",
            "entity_liability_admission": "[e.g., 'Company admitted to securities fraud as part of a Deferred Prosecution Agreement']"
          }
        ],
        "asset_freezes_recovery": "[e.g., 'Court-appointed trustee identified and seized $A billion in assets globally', 'Clawback lawsuits filed against early investors who withdrew "fictitious profits"']"
      },
      "restructuring_efforts": {
        "new_leadership": "[e.g., 'A former federal judge appointed as CEO to oversee bankruptcy and investigation']",
        "core_business_sale": "[e.g., 'Viable operating divisions sold to competitors for pennies on the dollar']",
        "victim_compensation_fund": {
          "established": "YYYY-MM-DD",
          "total_fund_amount": "$B billion",
          "estimated_recovery_rate_for_victims": "X% of principal lost"
        }
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "investigations_and_trials": {
        "key_governmental_inquiry": "[e.g., 'The Permanent Subcommittee on Investigations (U.S. Senate) held hearings and published a 500-page report']",
        "criminal_convictions": [
          {
            "defendant_name": "[e.g., 'Former CEO']",
            "charges": "[e.g., 'Securities fraud, wire fraud, conspiracy']",
            "sentence": "[e.g., '150 years imprisonment, $170 billion in restitution (symbolic)']"
          }
        ]
      },
      "regulatory_and_legal_reforms": {
        "new_legislation": "[e.g., 'Sarbanes-Oxley Act of 2002 (SOX): Established PCAOB, mandated CEO/CFO financial statement certification, strengthened auditor independence rules']",
        "new_accounting_standards": "[e.g., 'FASB Interpretation No. 46(R) on consolidation of Variable Interest Entities (VIEs), directly targeting Enron-style SPEs']",
        "enhanced_listing_rules": "[e.g., 'NYSE and NASDAQ mandated majority-independent boards and fully independent audit committees']"
      },
      "profession_standards_evolution": {
        "auditing_standards": "[e.g., 'PCAOB adopted AS 2401, requiring greater skepticism and specific procedures for fraud detection']",
        "corporate_governance_codes": "[e.g., 'UK Corporate Governance Code strengthened the role of the audit committee and expanded whistleblowing provisions']",
        "ethics_training_focus": "[e.g., 'Professional accounting bodies (AICPA, ACCA) made ethics a mandatory, recurring CPE requirement']"
      },
      "lasting_cultural_legacy": {
        "public_trust_impact": "[e.g., 'Long-term erosion of trust in corporate financial statements and audit opinions', 'Increased popularity of "short-selling" and forensic accounting analysis']",
        "business_education_incorporation": "[e.g., 'The case study became a mandatory module in MBA programs and professional accounting exams worldwide']",
        "archetypal_reference": "[e.g., 'The company's name entered the lexicon as a byword for complex, audacious corporate fraud and governance failure']"
      }
    }
  }
}
"""