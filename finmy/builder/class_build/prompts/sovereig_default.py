

def sovereign_default_prompt(text: str) -> str:
    return """
You are an expert international economist and sovereign debt crisis historian. Your task is to reconstruct a complete, detailed, and fact-based narrative of a specified sovereign default event based on provided multi-source data (e.g., parsed web content, PDF documents, IMF reports, central bank publications, bond prospectuses, court rulings, news archives).

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of a sovereign default event. Your output must be a structured JSON that meticulously documents the event's macroeconomic precursors, political context, default mechanics, negotiation processes, resolution, and long-term consequences.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Fact-Based Synthesis**: Integrate information from all provided sources. Resolve contradictions by prioritizing primary official data (e.g., IMF Article IV Consultations, Central Bank statements, Official Debt Sustainability Analyses, Legal Default Declarations, Final Restructuring Agreements).
2.  **Temporal & Causal Logic**: The narrative must establish clear causal links between economic policies, external shocks, fiscal deterioration, and the default decision. Maintain strict chronological order for key events.
3.  **Financial & Accounting Logic**: Accurately model debt stocks, flows (interest payments, primary balances), and sustainability metrics. Clearly distinguish between *external* and *domestic* debt, and between *hard* (foreign law) and *local law* defaults.
4.  **Stakeholder Perspective**: Analyze the differing positions and constraints of key actors: the sovereign debtor, private international creditors, official bilateral creditors (Paris Club), multilateral institutions (IMF, World Bank), domestic political groups, and the citizenry.

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON.

{
  "sovereign_default_simulation_report": {
    "metadata": {
      "event_name": "string | The canonical name for the default event (e.g., 'Greece Private Sector Involvement (PSI) 2012', 'Argentina Default 2001', 'Russian GKO Default 1998').",
      "country_iso3": "string | The ISO 3166-1 alpha-3 country code of the defaulting nation (e.g., 'ARG', 'GRC', 'RUS').",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation (e.g., '2023-11-15').",
      "data_sources_summary": "array[string] | Brief list of primary data sources used (e.g., ['IMF Country Report No. 12/57', 'Prospectus for Bond XYZ', 'Official Gazette Default Decree 123', 'Credit Rating Agency Press Release']).",
      "default_type_classification": {
        "instrument_type": "array[string] | Types of obligations defaulted on (e.g., ['International Sovereign Bonds', 'Paris Club Bilateral Loans', 'Domestic Treasury Bills']).",
        "jurisdiction": "array[string] | Legal jurisdictions of the defaulted debt (e.g., ['Foreign Law (NY/UK)', 'Local Law']).",
        "creditor_type": "array[string] | Primary creditor groups affected (e.g., ['Private Bondholders', 'Official Bilateral Creditors', 'Domestic Banks/Pension Funds'])."
      }
    },
    "1_overview_and_context": {
      "executive_summary": "string | A concise 3-5 sentence summary of the default: key economic/political causes, the scale of the debt restructuring, and the immediate outcome.",
      "crisis_timeline": {
        "pre_crisis_period_start": "string (YYYY-MM) | Start of identifiable economic/fiscal deterioration leading to crisis.",
        "default_event_date": "string (YYYY-MM-DD) | The formal date of the default declaration or first missed payment.",
        "restructuring_agreement_date": "string (YYYY-MM-DD) | Key date for final restructuring agreement. Use 'N/A' if pending.",
        "exit_from_default_status_date": "string (YYYY-MM-DD) | Date of return to market or settlement. Use 'N/A' if pending."
      },
      "pre_default_macroeconomic_backdrop": {
        "primary_imbalances": "string | Description of core problems (e.g., 'Large twin deficits (fiscal & current account)', 'Overvalued fixed exchange rate', 'Banking sector crisis').",
        "key_vulnerabilities": "array[string] | List of critical weaknesses (e.g., ['High Short-Term External Debt', 'Dependence on Commodity Exports', 'Political Fragmentation', 'Contagion from Regional Crisis']).",
        "trigger_event": "string | The proximate catalyst (e.g., 'Sudden stop in capital flows', 'Sharp commodity price decline', 'Political election/unrest', 'Loss of market confidence following a failed auction')."
      }
    },
    "2_key_actors_and_institutions": {
      "sovereign_debtor": {
        "government_at_default": "string | The ruling administration/coalition at the time of default.",
        "central_bank": "string | Name of the central bank and its role in the crisis (e.g., 'Defender of currency peg', 'Lender of last resort to government').",
        "negotiating_authority": "string | The primary entity leading restructuring talks (e.g., 'Ministry of Finance Debt Office', 'Ad Hoc Presidential Committee')."
      },
      "creditor_coalitions": {
        "private_creditor_committee": "string | Name of the main bondholder committee formed, if any (e.g., 'Ad Hoc Group of Argentine Bondholders').",
        "key_bilateral_creditors": "array[string] | Major official bilateral lenders involved (e.g., ['Germany (Paris Club chair)', 'Japan', 'United States']).",
        "multilateral_institutions": "array[object] | Role of IFIs. Each object: {'institution': 'string (e.g., IMF)', 'role': 'string (e.g., 'Provider of Bridge Financing & DSA', 'Catalyst for Private Sector Involvement')}."
      },
      "domestic_stakeholders": {
        "political_constraints": "string | Internal political dynamics affecting default/negotiation decisions (e.g., 'Public opposition to austerity', 'Powerful domestic bondholder lobby', 'Upcoming elections').",
        "public_sentiment": "string | General populace's view of the default and creditors (e.g., 'Widespread support for hard stance against 'vulture funds'', 'Anger directed at political class')."
      }
    },
    "3_debt_profile_and_default_mechanics": {
      "pre_default_debt_snapshot": {
        "total_sovereign_debt_to_gdp": "number | Ratio (%) at the onset of crisis.",
        "debt_composition": {
          "external_vs_domestic": "string | Approximate split (e.g., '70% External / 30% Domestic').",
          "hard_currency_share": "string | Share of debt denominated in foreign currency (e.g., '85% in USD/EUR')."
        },
        "near_term_refinancing_needs": "string | The immediate liquidity challenge (e.g., '$15B in principal + interest due within next 12 months')."
      },
      "the_default_event": {
        "formal_announcement": "string | How the default was communicated (e.g., 'Public decree by President', 'Silent default via missed IMF payment', 'Announcement of debt exchange offer').",
        "legal_technical_definition": "string | The specific contractual trigger (e.g., 'Failure to pay principal upon maturity', 'Expiration of grace period on coupon payment', 'Cross-default triggered on other bonds').",
        "immediate_market_reaction": {
          "currency_move": "string | e.g., 'Currency devalued by 40% within one month'.",
          "cds_spreads": "string | e.g., 'CDS spreads widened to over 5000 bps'.",
          "capital_controls_imposed": "boolean"
        }
      }
    },
    "4_restructuring_process": {
      "negotiation_dynamics": {
        "duration_of_process": "string | Time from default to final agreement (e.g., '15 years of litigation', '6 months of intense negotiations').",
        "major_sticking_points": "array[string] | Key issues of contention (e.g., ['Nominal Haircut vs. NPV Reduction', 'GDP Warrants', 'Collective Action Clause (CAC) thresholds', 'Treatment of 'Holdout' Creditors']).",
        "use_of_coercive_tools": "array[string] | Legal/policy tools used (e.g., ['Retroactive insertion of Local Law CACs', ''Rights Upon Future Offers (RUFO) Clause', 'Payment into local court account'])."
      },
      "restructuring_terms": {
        "haircut_description": "string | Nature of the principal reduction (e.g., '50% nominal face value reduction', 'NPV loss estimated at 65%').",
        "new_instruments": "array[object] | Description of new bonds/loans. Each object: {'type': 'string (e.g., Discount Bond)', 'coupon': 'string', 'maturity': 'string'}.",
        "additional_features": "array[string] | Other terms (e.g., ['GDP-linked warrants', 'Partial up-front cash payment (cash sweetener)', 'Guarantees from third parties'])."
      },
      "creditor_participation_and_holdouts": {
        "participation_rate": "string | Percentage of eligible debt tendered in exchange (e.g., '93% of bonds under Foreign Law').",
        "holdout_fate": "string | Outcome for non-participating creditors (e.g., 'Engaged in prolonged litigation; some received full payment after 15 years', 'Subject to same terms via CACs')."
      }
    },
    "5_immediate_and_long_term_consequences": {
      "economic_impact_domestic": {
        "recession_depth_duration": "string | e.g., 'GDP contracted by 10% over 3 years'.",
        "inflation_hyperinflation_episode": "string | e.g., 'Inflation surged to 40% annually, peaking at 200% in the following crisis'.",
        "banking_system_impact": "string | e.g., 'Bank balance sheets devastated due to sovereign bond holdings; required state recapitalization'.",
        "capital_market_exclusion": {
          "duration": "string | e.g., 'Locked out of international bond markets for 7 years'.",
          "re_access_terms": "string | e.g., 'Returned with a $2.75B bond at a yield of 7.5%'."
        }
      },
      "social_and_political_impact": {
        "income_and_poverty_effects": "string | e.g., 'Poverty rate increased by 15 percentage points; real wages fell 20%'.",
        "political_fallout": "array[string] | e.g., ['Fall of the government within 6 months', 'Rise of anti-establishment political movements'].",
        "sovereign_reputation": "string | Perception in international financial community (e.g., 'Viewed as a recalcitrant debtor for decades', 'Seen as a cooperative but unfortunate case')."
      },
      "systemic_and_international_impact": {
        "contagion_to_other_markets": "string | Did it trigger regional/global risk-off? (e.g., 'Limited to regional peers with similar fundamentals', 'Contributed to a broader emerging market sell-off').",
        "legal_precedents_set": "array[string] | e.g., ['Set precedent on interpretation of pari passu clauses', 'Spurred wider adoption of stronger CACs in bond contracts'].",
        "changes_in_lending_practices": "string | Impact on how creditors assess sovereign risk (e.g., 'Increased focus on debt sustainability analysis (DSA)', 'Higher risk premiums for countries with history of litigation')."
      }
    },
    "6_simulation_analysis_notes": {
      "debt_sustainability_analysis_retrospective": "string | Brief analysis: Was default inevitable given the pre-crisis DSA, or was it a liquidity crisis turned solvency crisis?",
      "critical_decision_points": "array[object] | Key junctures that altered the outcome. Each object: {'decision': 'string', 'actor': 'string', 'consequence': 'string'}.",
      "alternative_scenarios_plausible": "string | Could timely IMF program or different policy mix have averted default?",
      "data_discrepancies": "array[string] | Note any major conflicting information from sources (e.g., differing haircut estimates from IMF vs. private analysts).",
      "simulation_confidence_level": "string | High/Medium/Low based on data quality, availability of restructuring term sheets, and consensus in historical analysis."
    }
  }
}
```

### **INSTRUCTION FOR EXECUTION**
1.  **Thoroughly Analyze** all provided source data pertaining to the requested sovereign default case (e.g., "Lebanon Default 2020").
2.  **Extract and Synthesize** information to populate every field in the JSON schema above. If precise data for a field is unavailable from sources, make a reasoned, logically consistent estimation and explicitly note this in the `simulation_analysis_notes.data_discrepancies` field.
3.  **Ensure Narrative Cohesion** across sections. The report should tell a coherent story from economic origins through crisis, resolution, and legacy.
4.  **Output ONLY** the raw JSON object, beginning with `{` and ending with `}`. Do not wrap the final output in any markdown code block syntax.


"""