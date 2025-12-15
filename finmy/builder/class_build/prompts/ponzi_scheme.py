


def ponzi_scheme_prompt() -> str:

    return """
You are an expert financial forensic analyst and historical event reconstruction specialist. Your task is to reconstruct a detailed, comprehensive, and factually accurate account of a Ponzi scheme event based on user-provided information and/or internet research. The output must be in JSON format, structured to reflect the complete lifecycle of the scheme with extreme granularity.

**Objective:** Create a definitive, multi-dimensional record of the Ponzi scheme that captures every conceivable detail—conceptual, operational, financial, legal, sociological, and psychological—based solely on verified facts and widely reported information.

**Output Format:** A single, extensive JSON object.

**Instructions for JSON Construction:**
1.  **Base Structure:** Organize the JSON under a primary key `"ponzi_scheme_reconstruction"`.
2.  **Lifecycle Phases:** Structure the main object according to the following six lifecycle phases. Each phase is a top-level key.
3.  **Granular Fields:** Under each phase, include an exhaustive set of fields. Each field's value should be a detailed string or object that provides specific, concrete information.
4.  **Integrated Explanation:** For EVERY field, directly embed the explanation or description of what that field represents within its value. For simple string fields, the explanation can be part of the narrative. For object fields, include an `"explanation"` sub-field.
5.  **Fact-Based:** All information must correspond to real, documented events, individuals, dates, figures, and sources. If specific data is unavailable for a particular case, state "Not publicly documented" or "Information not widely available" rather than speculating.
6.  **Comprehensiveness:** Aim to create a JSON that is so detailed it could serve as the master dataset for a documentary, academic study, or legal case. Consider technical details, human stories, systemic interactions, and chronological precision.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "ponzi_scheme_reconstruction": {
    "metadata": {
      "scheme_common_name": "[The most widely recognized name for the scheme, e.g., 'Bernie Madoff Investment Scandal']. Explanation: The colloquial or media-given name of the event.",
      "official_legal_case_name": "[e.g., 'Securities and Exchange Commission v. Bernard L. Madoff Investment Securities LLC']. Explanation: The formal name used in court proceedings.",
      "primary_perpetrator_name": "[Full name of the key architect]. Explanation: The individual centrally responsible for designing and/or operating the scheme.",
      "key_associated_entities": ["List of company names, funds, or organizations used as vehicles for the fraud"]. Explanation: Legal entities instrumental in facilitating the scheme.",
      "operational_timeframe": {
        "suspected_inception_year": "YYYY. Explanation: The estimated year the fraudulent activity began.",
        "public_collapse_year": "YYYY. Explanation: The year the scheme became publicly known and unraveled.",
        "duration_years": "X. Explanation: The approximate operational lifespan from inception to collapse."
      },
      "estimated_global_scale": {
        "currency": "USD/EUR/etc.",
        "amount_at_collapse": "XX billion. Explanation: The approximate nominal value of liabilities or promised returns at the time of collapse.",
        "victim_count_estimate": "Approximate number of individuals or entities defrauded.",
        "geographic_reach": ["List of primary countries or regions affected"]
      }
    },
    "phase_1_conception_and_design": {
      "origin_context": {
        "perpetrator_background": "Detailed biography prior to the fraud, including education, early career, and reputation. Explanation: Provides insight into the origin of capability and social capital.",
        "initial_legitimate_activity": "Description of any legitimate business or investment activity that preceded or was used to cloak the fraud. Explanation: The 'kernel of truth' or operational cover.",
        "catalyst_for_fraud": "The specific circumstance, pressure, or opportunity that initiated the fraudulent plan (e.g., trading losses, desire for status, competitive pressure). Explanation: The perceived trigger point."
      },
      "fraudulent_design": {
        "core_promise_to_investors": "Exact description of the returns promised (e.g., 'consistent 1-2% monthly returns, regardless of market conditions'). Explanation: The unsustainable lure.",
        "claimed_investment_strategy": "The fabricated or misrepresented method for generating returns (e.g., 'split-strike conversion strategy', 'foreign exchange arbitrage'). Explanation: The fictional engine of growth.",
        "identified_exploits": {
          "regulatory_gaps": "Specific financial regulations that were circumvented or loopholes exploited.",
          "auditor_weaknesses": "How audits were avoided, falsified, or conducted by complicit/incompetent firms.",
          "investor_psychology_levers": "The psychological biases targeted (e.g., exclusivity, fear of missing out, trust in affinity groups)."
        },
        "structural_blueprint": "Description of how new investor money was planned to flow to older investors, and how records would be maintained (manually, via simple software, complex accounting)."
      }
    },
    "phase_2_implementation_and_obfuscation": {
      "onboarding_mechanics": {
        "target_demographic": "Specific profile of early investors (e.g., family friends, members of a specific community, institutional clients).",
        "affinity_group_targeting": "Detailed use of religious, ethnic, professional, or social networks to build trust.",
        "initial_investment_vehicles": "The types of accounts, funds, or notes offered to initial participants."
      },
      "fabricated_reality_apparatus": {
        "statement_generation": "Process for creating false account statements: frequency, format, level of detail, and technological method.",
        "falsified_documentation": "Types of documents forged (trade confirmations, auditor reports, regulatory filings).",
        "intermediary_complicity": "Role of feeders, introducers, or third-party marketers: their compensation structure and level of knowledge."
      },
      "trust_maintenance_strategies": {
        "perpetrator_persona_management": "Active cultivation of image (philanthropy, industry boards, perceived lifestyle).",
        "secrecy_and_exclusivity_cues": "Tactics used to discourage scrutiny (e.g., 'the strategy is too complex to explain', turning away some money).",
        "response_to_early_inquiries": "Scripted or ad-hoc responses to initial questions from skeptical investors, journalists, or junior staff."
      }
    },
    "phase_3_growth_and_amplification": {
      "recruitment_acceleration": {
        "tiered_referral_systems": "Existence and structure of formal referral bonuses or incentives.",
        "testimonials_and_evangelists": "Key influential investors who actively promoted the scheme and their profiles.",
        "geographic_expansion_strategy": "How the scheme moved into new regions or countries."
      },
      "external_validation_engineering": {
        "media_manipulation": "Specific positive articles, awards, or rankings obtained, and how they were secured.",
        "elite_and_celebrity_association": "Names of high-profile individuals/institutions invested, and how their participation was used in marketing.",
        "simulated_regulatory_compliance": "Appearances at conferences, superficial interactions with regulators, or use of licensed entities."
      },
      "systemic_intertwining": {
        "banking_relationships": "Banks used for operations; their level of suspicion or complicity; how funds were moved.",
        "legal_and_accounting_service_providers": "Firms providing peripheral services and the nature of their engagement.",
        "dependence_of_legitimate_entities": "Charities, businesses, or municipalities that became financially reliant on the scheme's fake returns."
      }
    },
    "phase_4_stress_and_fracture": {
      "liquidity_pressures": {
        "redemption_trends": "Timing and scale of increased withdrawal requests (due to macroeconomic factors like the 2008 crisis).",
        "cash_flow_analysis": "The growing gap between incoming new investments and required payout obligations.",
        "emergency_funding_measures": "Desperate actions taken to attract large, last-minute investments (e.g., offering preferential terms)."
      },
      "internal_dissent": {
        "key_employee_suspicions": "Instances where staff questioned operations; how they were placated, threatened, or dismissed.",
        "whistleblower_attempts": "Documented efforts by insiders to alert authorities or the media, and the outcome.",
        "perpetrator_stress_signals": "Observable changes in the perpetrator's behavior, health, or public statements."
      },
      "external_threats": {
        "competitor_analysis": "Warnings from legitimate financial analysts or firms.",
        "journalistic_investigations": "Specific reporters or publications that began asking questions.",
        "regulatory_near_misses": "Examinations or inquiries that nearly uncovered the fraud but did not."
      }
    },
    "phase_5_exposure_and_collapse": {
      "trigger_event": {
        "precipitating_factor": "The specific event that made continuation impossible (e.g., a single large redemption request, a whistleblower's report to the SEC, a market crash).",
        "date_and_location": "The precise day and context of the trigger.",
        "perpetrator_response": "The immediate action of the perpetrator (confession to family, attempt to flee, surrender to authorities)."
      },
      "collapse_dynamics": {
        "communication_of_collapse": "How investors were informed (letter, email, news announcement).",
        "freeze_actions": "What was immediately frozen: bank accounts, redemptions, websites.",
        "public_reaction_timeline": "Hour-by-hour or day-by-day account of the public unraveling and media frenzy."
      },
      "immediate_fallout": {
        "suicide_or_extreme_events": "Any tragic immediate consequences among perpetrators or investors.",
        "first_legal_filings": "Details of the first regulatory complaint or civil lawsuit filed.",
        "asset_seizures": "Initial properties, accounts, and valuables seized by authorities."
      }
    },
    "phase_6_aftermath_and_legacy": {
      "legal_proceedings": {
        "criminal_trials": "Charges, plea deals, trial highlights, verdicts, and sentences for the perpetrator and accomplices.",
        "civil_litigation": "Major lawsuits by trustees, investors, or regulators against feeder funds, banks, or auditors.",
        "key_legal_arguments": "The central prosecution and defense theories used in court."
      },
      "financial_reconstruction": {
        "bankruptcy_trust_administration": "The entity formed to liquidate assets and distribute recovered funds.",
        "recovery_statistics": "Total amount recovered, percentage of principal returned to victims, and timeline of distributions.",
        "tax_implications": "How losses were treated for tax purposes by victims."
      },
      "societal_impact": {
        "victim_profiles_and_stories": "Notable case studies of individuals, families, or charities devastated.",
        "industry_reputational_damage": "Impact on the hedge fund, wealth management, or specific community targeted.",
        "regulatory_and_policy_changes": "Laws enacted (e.g., Dodd-Frank acts), SEC procedure reforms, or new oversight bodies created in response."
      },
      "historical_analysis": {
        "classification_in_fraud_typology": "How it compares to other historical frauds (Ponzi, pyramid, etc.).",
        "post_mortem_analysis_reports": "Key findings from official government reports or academic studies.",
        "cultural_artifacts": "Books, films, documentaries, and podcasts produced about the scheme."
      }
    }
  }
}
    """