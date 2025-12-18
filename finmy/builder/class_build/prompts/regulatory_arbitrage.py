
def regulatory_arbitrage_prompt() -> str:
    return """
You are a forensic financial historian and regulatory reconstruction specialist.

**Objective:** To reconstruct a comprehensive, granular, and analytically profound narrative of a specific regulatory arbitrage event. Your task is to synthesize information from user-provided materials and/or internet research to populate a deeply structured JSON schema. This schema must capture the event's full lifecycle, from its ideological origins to its systemic aftermath, meticulously detailing the mechanisms, actors, incentives, and failures involved in exploiting regulatory differences to reduce capital, liquidity, or reporting requirements.

**Output Format:** A single, extensive, and fully populated JSON object. Do not include any introductory or explanatory text outside the JSON.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must strictly adhere to the provided schema outline. It is organized into top-level sections: `metadata` (for static facts and identifiers) and the six `stage_*` lifecycle phases (for the dynamic narrative).
2.  **Lifecycle Phases:** Populate each stage (I-VI) as a distinct object. Your analysis must frame events, decisions, and perceptions within the conceptual logic of each stage: the "normal" state of belief (I), the hidden accumulation of risk (II), the triggering crisis (III), the immediate collapse (IV), the emergency response (V), and the long-term reform (VI).
3.  **Granular Fields:** Every field must be populated with specific, concrete information. Avoid vague summaries. Use precise names, dates, monetary figures, legal citations, direct quotes from reports, and detailed descriptions of financial instruments and legal structures. Where exact data is unavailable, provide reasoned estimates and label them as such (e.g., "estimated_*").
4.  **Integrated Explanation:** For fields requiring deeper understanding, the "Explanation" should be woven directly into the value. Treat the value as a combined data-and-analysis entry. For example, a field like `regulatory_loophole_exploited` should contain not just the name of the rule, but a concise technical explanation of how it was circumvented.
5.  **Fact-Based:** All information must be grounded in verifiable sources, court documents, regulatory findings, official reports, or reputable journalistic investigations. The narrative should be objective and analytical, not speculative.
6.  **Comprehensiveness:** Strive to include every relevant dimension: economic context, political climate, technological enablers, organizational culture, individual psychology, legal arguments, mathematical models, cross-border coordination failures, and the human impact. The final JSON should serve as a standalone, exhaustive case study.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "regulatory_arbitrage_reconstruction": {
    "metadata": {
      "scheme_common_name": "e.g., 'The London Whale Trades', 'The Use of Special Purpose Entities by Enron', 'The Eurodollar Market Exploitation in the 1970s'. The colloquial or media-given name for the event.",
      "official_legal_case_name": "e.g., 'SEC v. JPMorgan Chase & Co., Admin. Proc. File No. 3-15236'. The formal name of the leading regulatory or court proceeding.",
      "primary_perpetrator_name": "e.g., 'Bruno Iksil (the 'London Whale')'. The key individual(s) or entity most responsible for designing/executing the arbitrage. Explanation: Distinguish between the architect and the executing trader/organization if different.",
      "key_associated_entities": ["e.g., 'JPMorgan Chase & Co.', 'Chief Investment Office (CIO), London', 'Synthetic Credit Portfolio (SCP)'. The legal entities, divisions, or funds central to the scheme."],
      "operational_timeframe": {
        "suspected_inception_date": "YYYY-MM-DD (or best estimate). The date the specific arbitrage strategy was first conceived and implemented.",
        "peak_activity_period": "YYYY-MM to YYYY-MM. The period during which the arbitrage positions were largest and most active.",
        "public_collapse_date": "YYYY-MM-DD. The date the story broke publicly, a major loss was announced, or regulatory action was disclosed.",
        "duration_days": "Integer. Calculated duration from inception to collapse.",
        "explanation": "Notes on why these dates are significant, referencing internal memos, trade tickets, or earnings calls."
      },
      "estimated_global_scale": {
        "currency": "Primary currency of losses/positions.",
        "peak_notional_exposure": "e.g., 'USD 157 billion'. The maximum face value of the derivatives or assets involved.",
        "marked_loss_at_collapse": "e.g., 'USD 6.2 billion'. The realized or paper loss when the scheme unwound.",
        "regulatory_capital_avoided": "e.g., 'Estimated USD 15 billion in risk-weighted asset reduction'. The quantifiable regulatory benefit sought.",
        "direct_victim_count_estimate": "Number if applicable (e.g., counterparties, investors).",
        "indirect_impact_scope": "Description of market volatility, credit freezes, or investor confidence shaken.",
        "geographic_reach_jurisdictions": ["e.g., 'United Kingdom (FCA)', 'United States (OCC, Fed, SEC)', 'Switzerland (FINMA)'. Jurisdictions where activity occurred or regulators were involved."],
        "explanation": "Analysis of how the scale was measured, the reliability of estimates, and the difference between notional value, risk, and actual loss."
      },
      "core_arbitrage_mechanism_summary": {
        "targeted_regulation": "e.g., 'Basel II International Capital Standards, specifically the Internal Models Approach for Credit Risk'. The specific rule, standard, or regime being gamed.",
        "exploited_regulatory_difference": "e.g., 'Difference in treatment of sovereign credit risk between Basel standardized approach (higher risk-weight) and internal model outputs (lower risk-weight for certain EU sovereigns)'. The precise discrepancy between jurisdictions, rules, or accounting treatments.",
        "financial_instruments_used": ["e.g., 'Credit Default Swap (CDS) indices (iTraxx Europe)', 'CDS tranches', 'Total Return Swaps'. The specific tools employed."],
        "legal_vehicles_used": ["e.g., 'Banking book vs. Trading book classification', 'Off-balance-sheet Special Purpose Vehicles (SPVs)'. The structural or accounting classifications exploited."],
        "technical_summary": "A concise 3-4 sentence explanation of the precise 'how': e.g., 'By booking long-dated, deep-out-of-the-money CDS positions on a credit index in the banking book under an internal model, the bank generated artificially low risk-weighted assets for these positions compared to their true economic risk, thereby reducing required regulatory capital while collecting premiums.'"
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "macroeconomic_financial_context": "Description of the prevailing economic conditions (e.g., low-interest-rate environment, search for yield, post-2008 regulatory tightening) that created incentives for such arbitrage.",
      "prevailing_regulatory_philosophy": "e.g., 'Principles-based regulation', 'Light-touch supervision', 'Reliance on internal bank models for capital adequacy'. The dominant regulatory mindset before the event.",
      "industry_best_practices_norms": "The accepted and culturally reinforced ways of operating within the specific financial sector (e.g., aggressive profitability targets for treasury units, normalization of complex derivatives).",
      "perceived_hazards_risks": "What risks were regulators and the industry publicly focused on? (e.g., traditional credit losses, market crashes) What risks were considered remote or managed?",
      "technological_capabilities": "State of risk management systems, valuation models, and reporting infrastructure that defined 'normal' operations.",
      "key_actors_initial_motivations": "The stated business purpose or incentive for the entities involved (e.g., 'hedge residual credit risk in the banking book', 'generate modest profits from excess deposits')."
    },
    "stage_II_-_incubation_period": {
      "initial_implementation_rationale": "The internal business case, memo, or directive that authorized the strategy. Include stated vs. actual goals.",
      "gradual_risk_accumulation": {
        "timeline_of_position_growth": "Chronological data points showing how exposures grew, often exponentially.",
        "escalation_mechanisms": "e.g., 'Doubling down on losing positions to avoid realizing marks', 'Increasing notional to maintain income as spreads tightened'. The behavioral or structural drivers of growth."
      },
      "early_warning_signals_ignored": [
        {
          "signal_description": "e.g., 'Value-at-Risk (VaR) breaches reported to Middle Office in [Month YYYY]'.",
          "source": "e.g., 'Internal risk report', 'Counterparty complaint', 'Model validation flag'.",
          "organizational_response": "e.g., 'VaR model parameters were adjusted', 'Trading limits were informally raised', 'Concerns were dismissed as 'the model doesn't understand the strategy''.",
          "explanation_of_dismissal": "The cultural, cognitive, or incentive-based reason the signal was ignored (e.g., 'Profit center status of the unit', 'Reputation of the trader as a 'star'')."
        }
        // ... (Multiple such signals should be listed)
      ],
      "internal_control_failures": {
        "risk_model_limitations": "Specific flaws in the mathematical models used (e.g., 'Failed to capture basis risk between indices and tranches', 'Assumed normal market liquidity')",
        "valuation_issues": "e.g., 'Use of conservative marks over market-consistent marks', 'Disputes between Front Office and Product Control'.",
        "management_oversight_breakdown": "How reporting lines were circumvented, committees were misinformed, or senior management failed to ask probing questions.",
        "compensation_incentives": "How bonus structures for traders and managers were tied to short-term P&L, encouraging risk-taking and opacity."
      },
      "external_oversight_lapses": {
        "regulatory_examinations_missed": "What did periodic regulatory reviews fail to detect, and why? (e.g., focused on documentation over substance, lack of technical expertise in complex derivatives).",
        "auditor_opinions": "The nature of the external audit reports during this period.",
        "market_skepticism_unheeded": "e.g., 'Rumors in the CDS market about the size of the positions', 'Analyst questions on unusual balance sheet items'."
      }
    },
    "stage_III_-_precipitating_event": {
      "trigger_event_description": "The specific, identifiable event that made the hidden risk unavoidable. e.g., 'A credit rating downgrade of a key sovereign', 'A forced request for collateral from a major counterparty', 'A whistleblower email to senior management'.",
      "date_and_immediate_catalyst": "Precise date and the chain of actions that started the unraveling.",
      "internal_recognition_moment": "The specific meeting, report, or calculation where senior management first understood the magnitude of the problem. Include direct quotes if available.",
      "external_revelation_process": "How did it start to become public? e.g., 'Earnings call announcement', 'Leak to Bloomberg News', 'Regulatory filing amendment'.",
      "market_reaction_initial": "Immediate price movements, spread widening, or counterparty actions following the first whiff of trouble."
    },
    "stage_IV_-_onset": {
      "immediate_financial_collapse": {
        "loss_announcement": "Details of the official loss announcement: date, amount, responsible executive.",
        "counterparty_flee_and_liquidity_crisis": "Description of how other market participants refused to trade with or provide funding to the entity.",
        "credit_rating_actions": "Downgrades and associated commentary.",
        "intraday_market_impact": "Volatility in specific indices or asset classes directly linked to the unwinding."
      },
      "operational_consequences": {
        "trading_cessation": "When and how the specific portfolio/unit was closed or unwound.",
        "key_personnel_departures": "Firings, resignations, or suspensions.",
        "internal_shutdown_of_activities": "Moratorium on similar strategies across the firm."
      },
      "regulatory_legal_onslaught": {
        "cease_and_desist_orders": "Dates and agencies.",
        "asset_freezes": "If applicable.",
        "criminal_charges_filed": "Against whom and on what dates.",
        "civil_lawsuits_initiated": "By shareholders, counterparties, etc."
      },
      "public_and_political_fallout": {
        "congressional_hearing_hearings_dates": "If applicable.",
        "media_frency_key_headlines": "A few representative headlines.",
        "public_statements_by_ceo_regulators": "Key apologetic or accusatory quotes."
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "emergency_internal_response": {
        "crisis_committee_formation": "Who was on it, mandate.",
        "strategic_unwind_process": "How positions were liquidated—fire sale vs. managed wind-down—and the total final loss.",
        "internal_investigation_launch": "Led by whom (e.g., Board committee, outside law firm)."
      },
      "regulatory_supervisory_response": {
        "imposed_business_restrictions": "e.g., 'Increased capital add-ons', 'Required pre-approval for new complex products'.",
        "consent_order_terms": "Summary of immediate enforceable promises made to regulators.",
        "replacement_of_management": "Forced resignations or new appointments demanded by regulators."
      },
      "financial_salvage_measures": {
        "capital_raise": "If needed, details.",
        "settlement_funding_provisioning": "Initial reserves set aside for expected fines/lawsuits.",
        "impact_on_earnings_dividends": "Quarterly results and shareholder returns affected."
      },
      "victim_mitigation_initial": "Any immediate restitution funds or customer outreach programs established."
    },
    "stage_VI_-_full_cultural_readjustment": {
      "official_investigations_reports": [
        {
          "report_title_author": "e.g., 'JPMorgan Chase & Co. Management Task Force Report (January 2013)', 'U.S. Senate Permanent Subcommittee on Investigations Report'.",
          "key_findings_summary": "Bulleted list of the core failures identified (technological, organizational, cultural).",
          "primary_recommendations": "List the main proposed reforms from the report."
        }
      ],
      "legal_penalties_settlements_final": [
        {
          "settling_authority": "e.g., 'U.S. Securities and Exchange Commission', 'U.K. Financial Conduct Authority', 'U.S. Department of Justice'.",
          "total_penalty_amount": "Broken down by fine, disgorgement, restitution.",
          "admissions_of_fact": "Key facts the entity was required to admit.",
          "compliance_monitor_imposition": "Details of any independent monitor appointed."
        }
      ],
      "regulatory_rule_changes_implemented": {
        "specific_new_rules_prompted": "e.g., 'Basel III's Fundamental Review of the Trading Book (FRTB)', 'Enhanced Supervisory Review Process (Pillar 2) for model use', 'U.S. Fed's Enhanced Prudential Standards requiring Chief Risk Officer reporting lines'.",
        "closing_of_the_arbitrage_loophole": "Precise textual or conceptual change in regulation that addressed the exploited difference."
      },
      "industry_practice_reforms": {
        "changes_in_governance": "e.g., 'Elevation of Chief Risk Officer to direct Board reporting', 'Mandatory 'clawback' provisions in bonus contracts'.",
        "advances_in_risk_technology": "e.g., 'Adoption of stress testing that includes 'grey swan' scenarios', 'Improved valuation challenge processes'.",
        "cultural_shifts_rhetoric": "New internal slogans or training programs (e.g., 'conduct risk', 'psychological safety for risk officers')."
      },
      "long_term_systemic_impact_assessment": {
        "perception_of_regulatory_arbitrage": "How the discourse changed—from 'clever' to 'reputationally toxic'.",
        "lasting_impact_on_firm_strategy": "Did the entity exit certain businesses permanently?",
        "legacy_in_academic_policy_literature": "How the case is now cited in textbooks, law reviews, and regulatory speeches as a canonical example of a specific failure mode."
      }
    }
  }
}
"""