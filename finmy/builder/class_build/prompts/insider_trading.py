def insider_trading_prompt() -> str:
    return """
You are a forensic financial historian and a narrative reconstruction specialist.

**Objective:** To reconstruct a comprehensive, deeply detailed, and historically accurate profile of a specific insider trading fraud event. Your output must capture the event's full lifecycle, from its sociocultural origins to its long-term societal impact, mirroring the detailed analysis of a cinematic historical documentary. The reconstruction must be based strictly on factual information provided by the user or retrieved from credible sources, with no speculative or fictional elements.

**Output Format:** A single, extensive, and self-contained JSON object.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must follow the exact top-level key structure provided: `metadata`, followed by the six lifecycle stages (`stage_I` through `stage_VI`). Each stage must contain multiple nested objects and arrays to capture granular detail.
2.  **Lifecycle Phases:** Populate each stage according to its sociological definition. Treat each phase as a chapter in the event's story, detailing the conditions, actions, perceptions, and consequences specific to that period.
3.  **Granular Fields:** Every field must be populated with specific, concrete information. Avoid generalizations. Use exact names, dates, figures, quotes (where documented), legal citations, and descriptions of specific actions. Where an exact value is unknown but a detail is relevant, use a carefully qualified statement (e.g., "alleged to be," "reportedly," "estimated at").
4.  **Integrated Explanation:** The "value" for each field should itself contain both the factual data and its explanatory context. Do not add a separate "explanation" key. Instead, write the value as a concise but informative statement that makes the field's significance clear.
5.  **Fact-Based:** All information must be rooted in verifiable facts from the provided case materials or credible external sources. Distinguish clearly between established fact, allegation, and insider testimony. Cite the source of key facts where possible within the value string (e.g., "As stated in the SEC complaint...").
6.  **Comprehensiveness:** Strive to create a holistic portrait. Beyond the core illegal trade, include details on the corporate environment, technological tools used, psychological states, regulatory interactions, media narrative shifts, legal strategy nuances, and the personal consequences for all involved parties (perpetrators, victims, colleagues, families).

Here is the required JSON schema outline with exemplary field descriptions. **Populate it with exhaustive, specific data from the target insider trading case.**

{
  "insider_trading_reconstruction": {
    "metadata": {
      "scheme_common_name": "e.g., 'The Galleon Group Insider Trading Network' or 'Martha Stewart ImClone Case'. The colloquial or media-given name for the scandal.",
      "official_legal_case_name": "e.g., 'United States v. Raj Rajaratnam et al., 11 Cr. 00906 (SDNY)'. The formal title of the leading criminal or regulatory proceeding.",
      "primary_perpetrator_name": "e.g., 'Raj Rajaratnam'. The central figure who either executed the most significant trades or orchestrated the network, with their title and affiliation at the time: 'Founder and Managing Member of Galleon Management, LP'.",
      "key_associated_entities": ["e.g., 'Galleon Group, LP', 'New Castle Funds LLC', 'Intel Corporation', 'Goldman Sachs & Co.']. A list of firms central to the scheme: the perpetrator's fund, the source companies, and facilitating institutions.",
      "operational_timeframe": {
        "suspected_inception_year": "e.g., 2006. The year the first identified material non-public information (MNPI) exchange and trade in this scheme occurred.",
        "public_collapse_year": "e.g., 2009. The year the investigation became public with arrests or SEC charges.",
        "duration_years": "e.g., 3. The span between inception and public collapse.",
        "key_date_arrests": "YYYY-MM-DD, e.g., 2009-10-16. The date the primary perpetrator was arrested.",
        "key_date_indictment": "YYYY-MM-DD, e.g., 2009-10-16. The date the formal indictment was unsealed."
      },
      "estimated_global_scale": {
        "currency": "e.g., USD",
        "illegal_profit_gain_avoided_loss": "e.g., 'Over $60 million in illicit profits and loss avoided'. The total monetary benefit from the illegal trades as determined by prosecutors.",
        "victim_count_estimate": "Describes the victim class: e.g., 'The investing public and counterparties to the fraudulent trades; direct individual victims are diffuse but number in the millions of market participants'.",
        "geographic_reach": ["e.g., 'United States', 'India', 'Sri Lanka']. Countries where crimes occurred, proceeds flowed, or investigations took place.",
        "securities_impacted": ["e.g., 'Google Inc. (GOOG)', 'Hilton Hotels Corp. (HLT)', 'Polycom Inc. (PLCM)']. A non-exhaustive list of publicly traded companies whose stock was traded based on MNPI."
      },
      "core_legal_violations": ["e.g., 'Securities Fraud under 15 U.S.C. § 78j(b) and Rule 10b-5', 'Conspiracy to Commit Securities Fraud', 'Criminal Insider Trading under 15 U.S.C. § 78ff']. The specific statutes and rules violated.",
      "investigative_agencies": ["e.g., 'U.S. Securities and Exchange Commission (SEC), Enforcement Division', 'Federal Bureau of Investigation (FBI), New York Field Office', 'U.S. Attorney's Office for the Southern District of New York (SDNY)']."
    },
    "stage_I_-_notionally_normal_starting_point": {
      "cultural_environment": {
        "industry_norms_circa_period": "Describes the accepted, perhaps lax, practices in the hedge fund/finance industry before the scandal. e.g., 'Era of "mosaic theory" often blurred with aggressive information gathering; expert networks were widely used and largely unscrutinized; the "Wall Street club" culture fostered discreet information sharing'.",
        "perceived_regulatory_rigor": "The market's perception of enforcement risk. e.g., 'SEC was perceived as under-resourced post-2008 crisis, focused on larger market-structure issues; insider trading convictions were seen as difficult to prove without a clear quid pro quo'."
      },
      "precautionary_norms": {
        "formal_compliance_framework": "The existing legal and internal rules. e.g., 'The Securities Exchange Act of 1934, Rule 10b-5; corporate insider trading policies; hedge fund compliance manuals prohibiting receipt of MNPI; mandatory employee training'.",
        "informal_safeguards": "The unwritten cultural barriers. e.g., 'Professional reputation risk; understood bright lines against explicit tips on earnings or M&A; fear of wiretaps was minimal'."
      },
      "perpetrator_profile_initial": {
        "professional_background": "e.g., 'A Wharton MBA, former analyst at Needham & Co., founded Galleon in 1997, built it into a multi-billion dollar hedge fund, renowned for technology stock expertise'.",
        "reputation_pre_scandal": "e.g., 'Viewed as a savvy, hard-working, and charismatic investor; featured in positive media profiles; a prominent philanthropist in the Sri Lankan community'.",
        "theoretical_access_to_mnpi": "Describes their legitimate channels. e.g., 'As a large fund manager, had legitimate access to company management through routine "channel checks" and analyst conferences'."
      }
    },
    "stage_II_-_incubation_period": {
      "initial_boundary_transgressions": {
        "first_known_illicit_contact": "e.g., 'In 2006, a junior Intel executive, initially a legitimate source, began providing advance details on Intel's earnings to Rajaratnam beyond public guidance'.",
        "rationalization_method": "How the perpetrator justified early actions. e.g., 'Viewed it as superior research within the "gray area" of mosaic theory; considered it a reciprocal favor within a network of contacts'.",
        "communication_methods_early": "e.g., 'Use of personal cell phones and email from non-office locations; vague yet understood code words during calls'."
      },
      "network_expansion_and_routinization": {
        "recruitment_of_tippers": "e.g., 'Leveraged his alumni network and industry stature to cultivate sources at McKinsey, IBM, and Goldman Sachs, often with implicit promises of career support or reciprocal information'.",
        "internalization_within_organization": "How the fraud permeated the perpetrator's firm. e.g., 'Portfolio managers under Rajaratnam were encouraged to develop their own "edge"; a culture of secrecy where lucrative trades were not questioned; compliance function was bypassed or misled'.",
        "escalation_of_stakes": "e.g., 'Trades grew in size from hundreds of thousands to millions of dollars per tip; information moved from earnings to impending mergers and acquisitions'."
      },
      "latent_failures_and_missed_signals": {
        "regulatory_missed_opportunities": "e.g., 'Unusual options activity ahead of deals was noted by regulators but not aggressively pursued initially; tips to the SEC were not acted upon promptly'.",
        "internal_red_flags_ignored": "e.g., 'A Galleon trader expressed concern about a tip's provenance but was reassured by Rajaratnam; the fund's auditor accepted vague explanations for trading patterns'.",
        "technological_enablers": "e.g., 'Use of prepaid "burner" phones increased; encrypted messaging apps were explored; but reliance on recorded office lines for some crucial calls persisted'."
      }
    },
    "stage_III_-_precipitating_event": {
      "triggering_investigative_action": {
        "origin_of_investigation": "e.g., 'A separate investigation into a boutique hedge fund, New Castle, using wiretaps for credit fraud, captured conversations about insider trading with a Galleon trader in 2008'.",
        "key_decision_point": "e.g., 'The SDNY and FBI, led by then-U.S. Attorney Preet Bharara, made the unprecedented decision to seek and obtain court authorization for wiretaps on Rajaratnam's cell phone, applying RICO-era tools to white-collar crime'.",
        "first_major_breakthrough": "e.g., 'A wiretapped call on March 7, 2008, where Rajaratnam is told about a $4 billion earnings write-down at Akamai Technologies by a McKinsey consultant, minutes before trading heavily'."
      },
      "erosion_of_secrecy": {
        "first_cooperating_witness": "e.g., 'A junior Galleon portfolio manager, facing his own charges, agreed to wear a wire and record conversations with Rajaratnam in early 2009'.",
        "key_evidence_gathered": "e.g., 'Over 18 months, prosecutors recorded over 2,400 phone conversations, capturing explicit discussions of earnings figures, deal negotiations, and efforts to conceal sources'.",
        "internal_suspicion_arousal": "e.g., 'Rajaratnam began warning associates to be careful and questioned if phones were tapped, but continued the behavior, believing his prestige made him untouchable'."
      }
    },
    "stage_IV_-_onset": {
      "moment_of_collapse": {
        "arrest_scenario": "e.g., 'At 6:00 AM on October 16, 2009, FBI agents arrested Rajaratnam at his luxury Manhattan apartment; simultaneous raids seized documents from Galleon's offices'.",
        "public_announcement": "e.g., 'A press conference held later that day by the SEC, FBI, and SDNY announced the largest hedge fund insider trading case in history, sending shockwaves through Wall Street'.",
        "immediate_market_reaction": "e.g., 'Galleon Group funds were frozen; investors rushed to submit redemption requests; shares of companies named in the complaint experienced volatile trading'."
      },
      "immediate_consequences": {
        "perpetrator_status_change": "e.g., 'Rajaratnam resigned as Galleon chairman; released on $100 million bond with electronic monitoring; the Galleon fund began immediate wind-down'.",
        "collateral_damage_initial": "e.g., 'Multiple other executives at Intel, McKinsey, and IBM were implicated and placed on leave or resigned; a "circle of trust" evaporated overnight'.",
        "legal_machinery_activation": "e.g., 'The SEC filed a parallel civil suit seeking disgorgement and penalties; a grand jury returned a multi-count indictment; bail conditions restricted international travel.'"
      },
      "media_and_public_narrative": {
        "initial_framing": "e.g., 'Portrayed as a tale of epic greed and corruption at the highest levels of finance; focus on wiretaps as a "game-changer"; scrutiny of the "expert network" industry model'.",
        "victim_perception": "e.g., 'Public anger directed at the unfairness to ordinary investors; political calls for tougher enforcement; the financial industry reacted with a mix of shock and defensiveness'."
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "containment_and_emergency_response": {
        "wind_down_of_operations": "e.g., 'Galleon hired a restructuring firm to liquidate its portfolios in an orderly fashion over several months to return capital to investors, albeit without final profits'.",
        "cooperators_and_plea_deals": "Lists key figures who flipped. e.g., 'Anil Kumar (McKinsey), Rajiv Goel (Intel), and Danielle Chiesi (New Castle) all pleaded guilty and became cooperating witnesses for the prosecution'.",
        "regulatory_triage": "e.g., 'SEC launched a sweep of expert network firms; the Financial Industry Regulatory Authority (FINRA) issued alerts on insider trading compliance'."
      },
      "ad_hoc_adaptations": {
        "industry_compliance_knee_jerk": "e.g., 'Hedge funds abruptly banned or severely restricted the use of expert networks; compliance departments demanded recordings of all trader conversations with outsiders; personal cell phone use on trading floors was restricted'.",
        "legal_defense_strategy": "e.g., 'Rajaratnam's defense team, led by John Dowd, filed motions to suppress the wiretap evidence, arguing it was obtained improperly and its use was an overreach'.",
        "public_relations_battles": "e.g., 'The defense painted Rajaratnam as a self-made immigrant success story being targeted unfairly; the prosecution framed him as the kingpin of a corrupt network.'"
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "formal_inquiry_and_adjudication": {
        "trial_highlights": "e.g., 'The eight-week trial in 2011 featured secret recordings played in court, revealing blatant tips. Key witness Anil Kumar testified tearfully about his corruption. The defense argued trades were based on public information'.",
        "verdict_and_sentencing": "e.g., 'Found guilty on all 14 counts of conspiracy and securities fraud. On October 13, 2011, sentenced to 11 years in federal prison, then the longest sentence for insider trading. Fined $10 million and ordered to forfeit $53.8 million'.",
        "appellate_outcomes": "e.g., 'Appeals upheld the conviction and the use of wiretaps, setting a powerful precedent for future white-collar investigations. The Supreme Court declined to hear the case in 2013'."
      },
      "systemic_reforms_and_new_norms": {
        "regulatory_policy_changes": "e.g., 'The SEC's Enforcement Division increased its use of sophisticated data analytics to detect suspicious trading patterns. The "Rajaratnam precedent" made wiretaps a standard tool in complex financial crime cases'.",
        "industry_practice_overhaul": "e.g., 'Pervasive recording of business-related cell phone calls became common at financial firms. "Information barrier" protocols between advisory and trading divisions were strengthened. Compliance budgets soared'.",
        "legal_doctrine_evolution": "e.g., 'The case reinforced the "de facto" insider theory and the liability of remote tippees. It blurred the line between hard "quid pro quo" and the more subtle "personal benefit" test, later clarified by the Supreme Court in *Salman* and *Dirks*.'"
      },
      "long_term_legacy_and_assessment": {
        "cultural_symbolism": "e.g., 'Rajaratnam became the archetype of the arrogant hedge fund titan brought low by technology and aggressive prosecution. The case marked the end of an era of perceived impunity for elite insider trading'.",
        "enduring_impact_on_perpetrators_and_victims": "e.g., 'Rajaratnam served 7.5 years, released to home confinement in 2021 due to health issues; his fortune and reputation destroyed. The diffuse victim class saw no direct restitution, but the deterrence value was argued to strengthen market integrity'.",
        "scholarly_and_ethical_reappraisal": "e.g., 'The case is a staple in business ethics curricula, used to discuss the slippery slope of information asymmetry. It sparked debate on the boundaries of aggressive research versus fraud, and the ethics of using intrusive surveillance methods in white-collar crime.'"
      }
    }
  }
}
"""