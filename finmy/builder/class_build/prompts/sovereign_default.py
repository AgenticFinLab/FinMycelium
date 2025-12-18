

def sovereign_default_prompt() -> str:
    return """
You are a financial historian and sovereign debt crisis reconstruction specialist, equipped with deep knowledge in macroeconomics, international finance, political economy, and legal frameworks governing sovereign debt.

**Objective:** To meticulously reconstruct a specific sovereign default event by synthesizing provided information and/or web-retrieved data. You must produce a comprehensive, granular, and factual narrative that captures the event's full lifecycle, causes, mechanisms, consequences, and long-term implications, structured according to a prescribed sociological framework of disaster development.

**Output Format:** A single, extensive JSON object. Do not include any explanatory text, markdown formatting, or code fences outside this JSON object. The output must be the JSON only.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON's root key is `"sovereign_default"`. It contains top-level sections: `"metadata"`, `"definitions_and_context"`, and the six sequential lifecycle stages (`stage_I` to `stage_VI`).
2.  **Lifecycle Phases:** Populate each stage according to the "Sequence of Events Associated with a Failure of Foresight" model. Treat each stage as a distinct chapter in the event's narrative. Data must be chronologically and thematically placed within the correct stage.
3.  **Granular Fields:** Every object must contain specific, detailed fields. Avoid high-level summaries. Use nested objects and arrays to capture complexity. Quantify wherever possible (dates, amounts, percentages, counts). For qualitative aspects, provide precise descriptions, quotes from key figures, or references to specific policies/actions.
4.  **Integrated Explanation:** Each field's value must serve as its own explanation. The data you populate should be self-explanatory and illustrative. For example, instead of a field value saying "high debt," it should state "Public debt-to-GDP ratio reached 165% in the year prior to default, driven by cumulative primary fiscal deficits averaging 5% of GDP over the preceding decade."
5.  **Fact-Based:** All information must be anchored in verified historical data, official reports, academic analyses, or reputable news sources. If certain details are ambiguous or disputed, note the discrepancy (e.g., `"reported_range": "X-Y billion"`, `"conflicting_accounts": "Description of the different viewpoints"`). Do not invent or speculate.
6.  **Comprehensiveness:** Strive to create a multi-dimensional portrait. Cover economic indicators, political dynamics, legal processes, social impact, market reactions, institutional roles, and discursive shifts. The JSON should be exhaustive enough to serve as a primary research dossier on the event.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "sovereign_default_reconstruction": {
    "metadata": {
      "event_common_name": "[The widely recognized name, e.g., 'Greek Government Debt Crisis (2012 Default/Restructuring)']",
      "official_legal_designation": "[e.g., 'The Greek Bond Haircut under the PSI (Private Sector Involvement) program, governed by Greek Law 4050/2012']",
      "defaulting_entity": {
        "official_name": "[Full name of the sovereign, e.g., 'The Hellenic Republic']",
        "government_type_at_time": "[e.g., 'Parliamentary Republic']",
        "ruling_party_coalition": "[e.g., 'Panhellenic Socialist Movement (PASOK) led by Prime Minister George Papandreou, later coalition with New Democracy']"
      },
      "key_associated_entities": {
        "domestic_institutions": ["e.g., 'Bank of Greece', 'Hellenic Parliament', 'Ministry of Finance'"],
        "international_institutions": ["e.g., 'European Commission (EC)', 'European Central Bank (ECB)', 'International Monetary Fund (IMF) - collectively the Troika'"],
        "major_creditor_groups": ["e.g., 'Private bondholders represented by the Institute of International Finance (IIF)', 'Eurosystem central banks via the Securities Markets Programme (SMP)'"]
      },
      "critical_timeline": {
        "technical_default_trigger_date": "YYYY-MM-DD. The date a payment was missed or a restructuring offer was formally launched constituting a default under relevant definitions.",
        "debt_restructuring_effective_date": "YYYY-MM-DD. The date the exchange offer settled and new bonds were issued.",
        "pre_crisis_accumulation_period": "e.g., '2001-2009: Entry into Eurozone, period of high growth fueled by capital inflows and rising debt.'",
        "acute_crisis_period": "e.g., 'Q4 2009 - Q1 2012: From revelation of deficit revisions to completion of PSI.'",
        "post_default_adjustment_period": "e.g., '2012-2018: Under third economic adjustment program, involving further austerity and reforms.'"
      },
      "scale_and_scope": {
        "debt_instruments_in_default": ["e.g., 'Greek government bonds issued under Greek law (approx. €177bn), bonds issued under English law (approx. €29bn), and other obligations'"],
        "nominal_value_of_debt_affected": {
          "currency": "EUR",
          "amount": "XXX billion. The aggregate face value of obligations subject to the restructuring."
        },
        "haircut_metrics": {
          "net_present_value_haircut": "X%. The estimated reduction in the net present value of claims as a result of the restructuring terms.",
          "face_value_reduction": "X%. The nominal reduction applied (e.g., 53.5% on the face value of eligible bonds in the 2012 Greek PSI)."
        },
        "direct_financial_impact": {
          "domestic_banking_sector_recapitalization_cost": "XX billion. Cost to recapitalize Greek banks that suffered massive losses on their sovereign bond holdings.",
          "eurozone_stability_fund_exposure": "XX billion. Amounts committed by the EFSF/ESM for Greek bank recapitalization and debt buybacks."
        },
        "geographic_contagion_risk": ["List countries most affected by market panic, e.g., 'Portugal, Ireland, Spain, Italy (peripheral Eurozone contagion)'"]
      }
    },
    "definitions_and_context": {
      "default_definition_applied": {
        "standard_used": "[e.g., 'IMF Definition: A failure to meet a principal or interest payment on the due date (or within the specified grace period). Also includes distressed debt exchanges that offer less favorable terms than the original.' Includes reference to rating agency actions (e.g., 'S&P declared a selective default (SD) on specific bond series').]",
        "specific_trigger": "[e.g., 'The retroactive insertion of Collective Action Clauses (CACs) into Greek-law bonds (Law 4050/2012) and their subsequent activation to force holdout creditors into a distressed exchange, constituting a 'restructuring default'.']"
      },
      "pre_default_macroeconomic_context": {
        "fiscal_position": {
          "debt_to_gdp_ratio_year_before_default": "X%",
          "budget_deficit_to_gdp_ratio": "X%",
          "primary_balance_to_gdp": "X%",
          "structural_factors": ["e.g., 'Chronic tax evasion, large public sector wage bill, generous pension system'"]
        },
        "external_position": {
          "current_account_deficit_to_gdp": "X%",
          "net_international_investment_position": "X% of GDP",
          "loss_of_competitiveness": "e.g., 'Unit labor costs increased by over 30% relative to Germany since Eurozone entry.'"
        },
        "financial_sector_health": {
          "banking_sector_exposure_to_sovereign_debt": "X% of total assets",
          "private_sector_credit_boom": "e.g., 'Private credit grew from 80% to 130% of GDP between 2001-2009.'",
          "dependence_on_ecb_liquidity": "e.g., 'Reliance on ECB Emergency Liquidity Assistance (ELA) by Q4 2011.'"
        },
        "political_situation": "e.g., 'Fragile coalition government, frequent social unrest (e.g., the 'Aganaktismenoi' movement), declining public trust in institutions.'"
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "dominant_economic_paradigm": "e.g., 'The 'Great Moderation' and the belief in the stability of the Eurozone as a optimal currency area, with convergence of sovereign bond yields ('Euro dividend') seen as permanent.'",
      "accepted_beliefs_about_sovereign_risk": {
        "market_belief": "e.g., 'Eurozone membership de-risked sovereign debt for all members; default within a monetary union was considered politically and legally inconceivable ('Euro irreversibility').'",
        "policy_maker_belief": "e.g., 'Stability and Growth Pact (SGP) rules, though often breached, were considered a sufficient disciplinary framework. Market discipline would correct minor fiscal lapses.'",
        "academic_consensus": "e.g., 'Emphasis on the benefits of monetary union with insufficient focus on asymmetric shock adjustment mechanisms and banking-sovereign doom loops.'"
      },
      "institutional_precautionary_norms": {
        "european_treaty_provisions": "e.g., 'Article 125 TFEU (the 'no-bailout clause') explicitly prohibited assumption of liabilities of other member states.'",
        "financial_regulations": "e.g., 'European banking regulations (Basel II) assigned zero risk weight to all Eurozone sovereign debt, encouraging concentrated bank holdings.'",
        "market_conventions": "e.g., 'Credit Default Swaps (CDS) on sovereign debt were relatively illiquid and not seen as a primary hedging tool.'"
      },
      "domestic_socio_political_setting": "e.g., 'Post-2004 Olympics optimism, widespread public and political support for Euro membership, belief in sustained EU cohesion funds and cheap credit fueling growth.'"
    },
    "stage_II_-_incubation_period": {
      "accumulating_divergences_from_norm": {
        "fiscal_data_revisions": "e.g., 'October 2009: Incoming government revises 2009 budget deficit forecast from 6.7% to 12.5% of GDP (later revised to 15.1%), revealing years of misreported statistics.'",
        "early_warning_signals_ignored": {
          "market_signals": "e.g., 'Gradual widening of Greek bond spreads vs. German Bunds from 2008 onwards, initially dismissed as global financial crisis spillover.'",
          "institutional_warnings": "e.g., '2004 and 2007 EU reports criticizing Greek fiscal data reliability, which elicited limited policy response.'",
          "academic_critiques": "e.g., 'Papers by economists like Wynne Godley (1992) and others warning about the design flaws of the Eurozone without fiscal union.'"
        },
        "political_inaction_and_denial": {
          "domestic": "e.g., 'Successive governments delayed meaningful structural reforms (pensions, labor market, tax administration) due to political cost.'",
          "european": "e.g., 'Initial Eurogroup responses focused on verbal assurances and small conditional loans, avoiding discussion of deep restructuring or collective burden-sharing.'"
        },
        "underlying_vulnerabilities_growing": {
          "debt_dynamics": "e.g., 'Debt-to-GDP continued rising despite austerity due to collapsing GDP (debt deflation dynamics) and high borrowing costs.'",
          "bank_sovereign_feedback_loop": "e.g., 'Downgrades of sovereign debt led to losses for domestic banks holding that debt, weakening the banks, which then required state support, worsening the sovereign's fiscal position.'"
        }
      },
      "key_events_during_incubation": [
        "e.g., 'April 2010: First €110bn bailout package agreed with Troika, imposing severe austerity. Market relief is short-lived.'",
        "e.g., 'May 2010: ECB begins Securities Markets Programme (SMP) to buy peripheral bonds, a first breach of the 'no-bailout' principle.'",
        "e.g., 'July 2011: 'Voluntary' private sector involvement (PSI) proposal by Euro Summit, initially aiming for a 21% NPV haircut, is deemed insufficient by markets.'",
        "e.g., 'October 2011: Private creditors are asked to accept a 50% nominal haircut in a new proposal. EU leaders vow to prevent 'uncontrolled default'.'"
      ]
    },
    "stage_III_-_precipitating_event": {
      "catalyst_description": "e.g., 'The failure of the October 2011 voluntary PSI deal to stabilize markets, combined with a deteriorating Greek fiscal position and rising political resistance to further austerity, forces European leaders to confront the necessity of a deep, coercive restructuring to restore debt sustainability.'",
      "immediate_trigger": "e.g., 'Q1 2012: Negotiations between the Greek government and its private creditors, mediated by the IIF, break down. Simultaneously, the Second Economic Adjustment Programme requires a successful debt restructuring as a condition for its €130bn funding. This creates a hard deadline.'",
      "decision_point": "e.g., 'Late February 2012: Eurogroup finance ministers officially endorse the use of Collective Action Clauses (CACs) to force participation if a high but insufficient voluntary participation rate is achieved. This is a public admission that a coercive default is now the chosen path.'",
      "announcement_and_market_immediate_reaction": {
        "date_of_key_announcement": "YYYY-MM-DD",
        "content": "e.g., 'Announcement of the final PSI terms: exchange of old bonds for new bonds with a 53.5% face value reduction, longer maturities, and lower coupons, financed by EFSF notes.'",
        "rating_agency_action": "e.g., 'S&P downgrades Greece to 'Selective Default' (SD) upon the launch of the exchange offer.'",
        "cds_auction_trigger": "e.g., 'The ISDA Determinations Committee rules the use of CACs constitutes a 'Restructuring Credit Event', triggering a payout on Greek CDS contracts (approx. $3.2bn).'",
        "initial_market_spillover": "e.g., 'Temporary spike in Portuguese and Italian bond yields, but contained due to ECB's SMP and anticipation of the event.'"
      }
    },
    "stage_IV_-_onset": {
      "immediate_mechanical_outcomes": {
        "debt_exchange_result": {
          "participation_rate": "X% of eligible bonds tendered.",
          "cac_activation": "e.g., 'CACs were activated on Greek-law bonds where needed to achieve over 95% participation in those series.'",
          "final_nominal_debt_reduction": "€XX billion written off."
        },
        "balance_sheet_impacts": {
          "domestic_bank_losses": "e.g., 'Greek banks recorded losses exceeding €40bn from the PSI, rendering them insolvent and requiring recapitalization with EFSF funds.'",
          "eurosystem_losses_avoided": "e.g., 'ECB and national central banks avoided the PSI haircut on their SMP holdings due to 'preferred creditor status'.'",
          "foreign_investor_losses": "e.g., 'Major European and global financial institutions (e.g., certain hedge funds, Cypriot banks) took significant write-downs.'"
        }
      },
      "domestic_economic_and_social_consequences": {
        "deepening_recession": "e.g., 'GDP contracted by an additional 6-7% in 2012; unemployment surged to over 25%.'",
        "banking_sector_freeze": "e.g., 'Capital controls were not yet imposed (these came in 2015), but a severe credit crunch ensued due to bank recapitalization.'",
        "social_unrest": "e.g., 'Intensification of protests and strikes against austerity; rise of anti-austerity political parties (Syriza, Golden Dawn).'",
        "humanitarian_impact": "e.g., 'Reports of rising poverty, homelessness, and deterioration in public health indicators.'"
      },
      "legal_and_contractual_fallout": {
        "holdout_litigation": ["e.g., 'Case brought by holdout creditors (e.g., Palikot group) in Greek courts, ultimately unsuccessful due to CACs.'", "e.g., 'Litigation by some bondholders in foreign jurisdictions (e.g., UK) regarding English-law bonds.'"],
        "sovereign_immunity_issues": "e.g., 'The use of retroactive Greek law to insert CACs raised debates about the sanctity of contract and sovereign power.'"
      },
      "systemic_financial_market_reaction": "e.g., 'While contained, the event led to a permanent repricing of Eurozone sovereign risk, ending the 'risk-free' illusion. It established a precedent for future restructurings within the monetary union.'"
    },
    "stage_V_-_rescue_and_salvage": {
      "immediate_firefighting_measures": {
        "bank_recapitalization_program": "e.g., '€48.2bn from the EFSF was channeled through the Hellenic Financial Stability Fund (HFSF) to recapitalize the four systemic Greek banks in 2012-2013.'",
        "continuation_of_troika_program": "e.g., 'The second €130bn adjustment program was unlocked post-PSI, providing funding for government operations and bank recapitalization.'",
        "ecb_liquidity_support": "e.g., 'ECB continued and expanded Emergency Liquidity Assistance (ELA) to Greek banks to prevent a total collapse of the payments system.'"
      },
      "debt_relief_from_official_sector": {
        "initial_official_sector_concessions": "e.g., '2012: Euro area member states reduced interest rates on their bilateral loans from the first program, extended maturities, and passed on SMP profits to Greece.'",
        "ongoing_negotiations": "e.g., 'Post-2012, debates continued about the need for further 'Official Sector Involvement' (OSI) to achieve debt sustainability targets.'"
      },
      "political_management_of_fallout": {
        "government_stability": "e.g., 'Formation of a grand coalition government under technocrat Prime Minister Lucas Papademos to oversee the PSI and later elections.'",
        "eurozone_crisis_management_institutions": "e.g., 'Acceleration of plans for a permanent rescue mechanism, leading to the operational launch of the European Stability Mechanism (ESM) in October 2012.'"
      },
      "narrative_control_and_communication": "e.g., 'Official statements framed the PSI as a 'unique' and 'exceptional' case to limit contagion, emphasizing Greece's specific failings rather than systemic Eurozone flaws.'"
    },
    "stage_VI_-_full_cultural_readjustment": {
      "formal_inquiries_and_assessments": {
        "european_level": ["e.g., 'EU task forces on strengthened economic governance (Six-Pack, Two-Pack, Fiscal Compact).'", "e.g., 'The 2015 'Five Presidents' Report' on Completing Europe's Economic and Monetary Union.'"],
        "imf_self_critique": "e.g., 'The IMF's 2013 Independent Evaluation Office (IEO) report critically assessed its role in the Greek program, admitting to major errors in debt sustainability analysis.'"
      },
      "paradigm_shift_in_beliefs": {
        "market_beliefs": "e.g., 'The 'redenomination risk' (risk of euro exit) became a permanent component of pricing for peripheral Eurozone sovereign debt.'",
        "policy_maker_beliefs": "e.g., 'Broad acceptance that monetary union requires banking union (SSM, SRM) and some form of fiscal risk-sharing to survive.'",
        "academic_consensus": "e.g., 'Overwhelming focus on the flaws of incomplete currency unions, the theory of Optimal Currency Areas, and the 'doom loop'.'"
      },
      "new_precautionary_norms_and_institutions": {
        "european_financial_architecture": ["e.g., 'Establishment of the Single Supervisory Mechanism (SSM) and Single Resolution Mechanism (SRM).'", "e.g., 'Introduction of the Eurozone's sovereign debt restructuring framework in 2021 - a standardized, non-retroactive CAC model.'"],
        "regulatory_changes": "e.g., 'Banking regulations (Basel III, CRD IV/CRR) introduced sovereign exposure concentration limits and more realistic risk-weighting considerations.'",
        "contractual_innovations": "e.g., 'Standardized, aggregate CACs become mandatory for new Euro area sovereign bonds from 2013, making future restructurings more orderly.'"
      },
      "long_term_consequences_and_legacy": {
        "for_the_defaulting_country": "e.g., 'A decade of depression-level output loss, deep social scars, political realignment (rise and fall of Syriza), and a legacy of very high debt despite restructuring.'",
        "for_the_eurozone": "e.g., 'A more resilient but less trusting union; north-south divisions deepened; Germany's influence cemented; the ECB's role transformed into a de facto lender of last resort.'",
        "for_international_finance": "e.g., 'The Greek PSI became a key case study in modern sovereign restructuring, highlighting the complexities of restructuring within a monetary union and the role of official creditors.'",
        "historical_narrative": "e.g., 'Viewed as the largest sovereign debt restructuring in history, a pivotal moment in the Eurozone crisis that forced a fundamental, if still incomplete, evolution of the European project.'"
      }
    }
  }
}
"""