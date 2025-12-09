
def stablecoin_depeg_prompt(text: str) -> str:
    return """
You are an expert financial analyst, forensic investigator, and macroeconomic specialist specializing in deconstructing and simulating complex financial crises, with particular expertise in sovereign defaults. Your task is to reconstruct a complete, detailed, and fact-based narrative of a specified sovereign default event based on provided multi-source data (e.g., parsed web content, PDF documents, IMF reports, World Bank studies, central bank statements, news articles, academic papers, bond prospectuses).

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of the sovereign default. Your output must be a structured JSON that meticulously documents the event's preconditions, triggers, key negotiation and crisis points, resolution mechanisms, and long-term aftermath.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Fact-Based Synthesis & Source Hierarchy**: Integrate information from all provided sources. Resolve contradictions by prioritizing official data from international financial institutions (IMF, World Bank), sovereign debt restructuring agreements, central bank publications, and final court rulings. Note significant discrepancies in the `simulation_analysis_notes.data_discrepancies` field.
2.  **Temporal & Causal Logic**: The narrative must follow a strict chronological order, clearly establishing the sequence from economic vulnerabilities to default trigger to resolution. Explicitly model causal relationships (e.g., how fiscal deficits led to debt accumulation, how a global shock triggered capital flight, how failed negotiations led to a payment suspension).
3.  **Financial & Macroeconomic Logic**: All figures (GDP, debt-to-GDP ratios, primary balances, haircut percentages) must be internally consistent and traceable to stated sources or realistic estimates. Clearly distinguish between *nominal* and *real* values, and *local currency* vs. *foreign currency* debt.
4.  **Multi-Actor Perspective**: Analyze the event from the perspectives of key stakeholders: the sovereign government, domestic citizens, domestic financial institutions, domestic & foreign private bondholders, bilateral official creditors (Paris Club), multilateral creditors (IMF, World Bank), and the broader international financial system.

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON.

```json
{
  "sovereign_default_simulation_report": {
    "metadata": {
      "sovereign_name": "string | The name of the country/sovereign entity that defaulted (e.g., 'Argentine Republic').",
      "default_identifier": "string | A specific identifier for this default episode, often by year or bond series (e.g., '2001 Default', '2020 Eurobond Default').",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation (YYYY-MM-DD).",
      "data_sources_summary": "array[string] | Brief list of primary data sources used (e.g., ['IMF Country Report No. XX/YY', 'Final Judgment from [Court Name]', 'Prospectus for [Bond Series]', 'World Bank Debt Statistics']).",
      "geographic_economic_context": "string | The region and economic classification of the sovereign (e.g., 'South America, Emerging Market')."
    },
    "1_overview": {
      "executive_summary": "string | A concise 3-5 sentence summary of the default: core causes (e.g., fiscal profligacy, terms-of-trade shock), the nature of the default (e.g., moratorium, distressed exchange), scale, and ultimate resolution status.",
      "crisis_period": {
        "pre_crisis_start": "string (YYYY-MM) | Start of the period where vulnerabilities accumulated significantly.",
        "default_trigger_date": "string (YYYY-MM-DD) | The key date when a payment was missed or a formal moratorium was declared.",
        "restructuring_agreement_date": "string (YYYY-MM-DD) | Date of the key restructuring agreement, if reached. Use null if not applicable.",
        "post_restructuring_end": "string (YYYY-MM) | End of the acute crisis phase, e.g., return to market access."
      }
    },
    "2_preconditions_and_actors": {
      "sovereign_government": {
        "administering_administration": "string | The ruling government/party during the default trigger.",
        "key_decision_makers": "array[object] | Key officials (e.g., Finance Minister, Central Bank Governor). Each object: {'name': 'string', 'role': 'string', 'tenure_period': 'string'}",
        "pre_default_economic_policy_stance": "string | Description of fiscal/monetary policy in years leading to crisis (e.g., 'Pro-cyclical fiscal expansion, currency peg maintenance')."
      },
      "debt_structure_at_onset": {
        "total_sovereign_debt_gross": "string | Total sovereign debt stock pre-default, in USD or local currency (specify).",
        "debt_to_gdp_ratio": "number | Gross debt as % of GDP.",
        "currency_composition": "object | Breakdown: {'local_currency': 'string (% and amount)', 'foreign_currency': 'string (% and amount)', 'usd_denominated': 'string (% and amount)'}",
        "creditor_composition": "object | Breakdown: {'domestic_holders': 'string (%)', 'foreign_private_bondholders': 'string (%)', 'multilateral (imf_wb)': 'string (%)', 'bilateral_official (paris_club)': 'string (%)', 'other': 'string (%)'}"
      },
      "key_creditor_groups": {
        "ad_hoc_bondholder_committee": "string | Name/description of the main private creditor negotiation group, if formed.",
        "leading_multilateral_creditor": "string | e.g., 'International Monetary Fund (IMF)'.",
        "key_bilateral_creditors": "array[string] | e.g., ['United States', 'Germany', 'Japan']."
      }
    },
    "3_crisis_trigger_and_escalation": {
      "immediate_triggers": "array[object] | List of proximate causes. Each object: {'trigger': 'string (e.g., 'Commodity price collapse', 'Sudden stop in capital flows', 'Banking crisis', 'Political instability')', 'date_approximate': 'string (YYYY-MM)', 'impact_description': 'string'}",
      "denial_of_service_events": {
        "first_missed_payment": {
          "date": "string (YYYY-MM-DD)",
          "instrument": "string | Which bond or loan payment was missed.",
          "amount_missed": "string"
        },
        "formal_moratorium_declaration": {
          "date": "string (YYYY-MM-DD)",
          "scope": "string | e.g., 'All foreign currency sovereign debt'.",
          "official_statement_summary": "string"
        }
      },
      "market_and_economic_consequences_pre_default": {
        "currency_depreciation": "string | % depreciation of local currency vs. USD in the 12 months before default.",
        "bond_spread_widening": "string | e.g., 'EMBI+ spread increased from 500 to 5000 bps'.",
        "capital_flight": "string | Description and estimated magnitude.",
        "recession_depth": "string | e.g., 'GDP contracted by 10.9% in the year following default'."
      }
    },
    "4_restructuring_process": {
      "negotiation_dynamics": {
        "duration": "string | Time from default trigger to final agreement (e.g., '3 years').",
        "major_sticking_points": "array[string] | e.g., ['Size of principal haircut', 'GDP-linked warrants', 'Legal jurisdiction of new bonds'].", 
        "role_of_imf": "string | Description of IMF's role (e.g., 'Provided bridging loan and technical support, program conditional on restructuring agreement')."
      },
      "restructuring_terms_key": {
        "instruments_restructured": "array[string] | List of bond series/loans included.",
        "face_value_reduction_haircut": "string | Nominal haircut percentage applied to principal.",
        "new_instruments_issued": "array[object] | Description of new bonds. Each object: {'type': 'string (e.g., 'Discount Bond', 'Par Bond')', 'coupon': 'string', 'maturity': 'string', 'collective_action_clauses': 'boolean'}",
        "net_present_value_npv_reduction": "string | Estimated NPV haircut (often different from face value haircut)."
      },
      "holdout_creditors_and_litigation": {
        "presence_of_holdouts": "boolean",
        "major_litigation_cases": "array[object] | If applicable. Each object: {'creditor_name': 'string', 'court': 'string', 'outcome_summary': 'string'}",
        "use_of_collective_action_clauses_cacs": "string | Were CACs used to bind holdouts? Describe."
      }
    },
    "5_final_state_and_resolution": {
      "post_restructuring_debt_sustainability": {
        "new_debt_to_gdp_ratio": "number | Post-restructuring debt/GDP projection.",
        "debt_service_to_revenue_ratio": "string | Key metric for fiscal space.",
        "imf_dsa_assessment": "string | IMF's Debt Sustainability Analysis conclusion post-deal (e.g., 'Sustainable with high probability')."
      },
      "financial_impact_quantification": {
        "total_face_value_of_debt_restructured": "string | Aggregate principal of affected instruments.",
        "estimated_total_losses_to_private_creditors_npv": "string | Total NPV loss absorbed by private bondholders.",
        "losses_for_domestic_banks_pension_funds": "string | Impact on domestic financial holders, if significant."
      },
      "resolution_status": {
        "return_to_international_capital_markets_date": "string (YYYY-MM) | Date of first successful bond issuance post-default.",
        "current_status_of_restructured_bonds": "string | e.g., 'Performing, trading at par' or 'Under subsequent restructuring'.",
        "final_settlement_with_holdouts": "string | Summary of how holdout situations were ultimately resolved."
      }
    },
    "6_domestic_and_global_impact": {
      "domestic_consequences": {
        "banking_sector_crisis": "string | Description of impact on domestic banks (e.g., 'Bank runs, nationalizations').",
        "inflation_and_currency_crisis": "string | Description of hyperinflation or sharp devaluation episodes.",
        "social_and_political_impact": "array[string] | e.g., ['Mass protests', 'Change of government', 'Sharp rise in poverty rates'].",
        "real_gdp_recovery_timeline": "string | Time taken for GDP to return to pre-crisis level."
      },
      "international_spillovers": {
        "contagion_to_other_emerging_markets": "string | Did spreads widen in peer countries? Which ones?",
        "impact_on_global_financial_institutions": "string | Losses reported by major international banks/funds.",
        "changes_in_sovereign_lending_practices": "array[string] | e.g., ['Wider adoption of Collective Action Clauses (CACs)', 'More stringent IMF lending frameworks'].",
        "legal_precedents_set": "array[string] | Key legal rulings from this case (e.g., 'Interpretation of pari passu clauses')."
      }
    },
    "7_simulation_analysis_notes": {
      "root_cause_analysis": "array[string] | Analysis of fundamental causes (e.g., 'Chronic fiscal deficits', 'Lack of monetary policy independence due to currency board', 'Over-reliance on volatile commodity exports').",
      "key_policy_failures": "array[string] | Critical missteps by authorities (e.g., 'Delayed seeking IMF support', 'Attempting to maintain an unsustainable currency peg').",
      "counterfactual_scenarios": "string | Brief analysis of possible alternative paths (e.g., 'Could an earlier restructuring have lessened the social cost?').",
      "data_discrepancies": "array[string] | Note any major conflicting information from sources regarding key figures or dates.",
      "simulation_confidence_level": "string | High/Medium/Low based on data quality, availability of official restructuring terms, and consensus among sources."
    }
  }
}
```

### **INSTRUCTION FOR EXECUTION**
1.  **Thoroughly Analyze** all provided source data pertaining to the requested sovereign default case (e.g., "Greece 2012 Debt Restructuring", "Argentina 2001 Default").
2.  **Extract and Synthesize** information to populate every field in the JSON schema above. For fields requiring precise quantitative data (e.g., haircut percentage, NPV reduction), prioritize the most authoritative source (e.g., IMF report, official term sheet). If data is unavailable, make a reasoned, explicitly stated estimation based on comparable historical cases and note this in `simulation_analysis_notes.data_discrepancies`.
3.  **Ensure Narrative Coherence** across sections. The report should tell a coherent story from the buildup of vulnerabilities, through the crisis and chaotic default period, the arduous restructuring process, to the eventual resolution and long-term scars.
4.  **Maintain Multi-Stakeholder Focus** throughout the analysis. Consider the distinct incentives, constraints, and outcomes for the government, domestic populace, and different classes of creditors.
5.  **Output ONLY** the raw JSON object, beginning with `{` and ending with `}`. Do not use markdown code block syntax in your final output.


"""