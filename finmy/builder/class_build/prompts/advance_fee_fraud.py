def advance_fee_fraud_prompt() -> str:
    return """
You are a senior financial forensic analyst and historical reconstruction specialist, with deep expertise in fraud schemes, criminal psychology, socioeconomic analysis, and regulatory history.

**Objective:** To meticulously reconstruct a specific Advance-Fee Fraud scheme as a comprehensive historical case study. The output must function as a definitive, granular, and multi-dimensional record that captures the scheme's operational mechanics, its lifecycle within the societal and regulatory context, its impact, and the resulting systemic changes.

**Output Format:** A single, extensive JSON object.

**Instructions for JSON Construction:**
1.  **Base Structure:** Use the provided JSON schema as the definitive structure. Populate every field. Do not omit any field. If concrete information for a field is unavailable from the provided/retrieved data, indicate with "Data not specifically identified" and make a reasoned inference based on the scheme's nature, explaining the inference in the field value.
2.  **Lifecycle Phases:** The reconstruction MUST be organized around the six-stage "Failure of Foresight" lifecycle model. Each stage object must contain detailed sub-fields that analyze the events, conditions, actors, and mindsets specific to that phase. Treat each stage as a chapter in a narrative.
3.  **Granular Fields:** Every field must be populated with specific, detailed information. Avoid summaries. For example, don't just state "emails were sent"; describe their content themes, frequency, and targeting strategy. For legal actions, list specific charges, dates, and outcomes.
4.  **Integrated Explanation:** The "value" for each field must contain both the factual data AND a concise explanatory analysis. Format: `"[Factual Data]. Explanation: [Why this is significant, how it functioned, or what it reveals about the stage/scheme]."`
5.  **Fact-Based:** All information must be grounded in the provided source materials or verifiable internet data. Clearly distinguish between confirmed facts, estimates, and logical inferences based on the scheme's modus operandi.
6.  **Comprehensiveness:** The JSON must paint a complete picture. Consider and include details on: the perpetrators' backgrounds and justifications; the technological and communication channels used; the precise "hook" and fabricated narrative; the psychological tactics applied; the financial flows and laundering methods; the victim demographics and vulnerabilities; the failures of specific institutions or regulations; the media narrative arc; the legal and regulatory gaps exposed; and the long-term changes in public awareness, law, and financial practice.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "advance_fee_fraud_reconstruction": {
    "metadata": {
      "scheme_common_name": "[e.g., 'The Spanish Prisoner Letter (20th Century variant)', 'Nigerian 419 Scam', 'Madoff Ponzi Scheme (as an advanced-fee structure for feeder funds)']. The colloquial or media-given name for this specific instance.",
      "official_legal_case_name": "[e.g., 'United States v. John Doe et al.', 'SEC Litigation Release No. 12345']. The formal name of the leading prosecution or regulatory action.",
      "primary_perpetrator_name": "[Full name and known aliases]. The individual centrally responsible for designing and/or operating the scheme. Explanation: Include background notes if relevant (e.g., former professional, organized crime ties).",
      "perpetrator_organization_structure": {
        "core_team_roles": ["e.g., 'Frontman/Communicator', 'Narrative Designer', 'Money Mule Coordinator', 'Document Forger'"]. Explanation: Describes the functional division of labor within the fraud ring.",
        "hierarchical_or_network_model": "e.g., 'Rigid hierarchy with a single boss', 'Loosely affiliated network of cells', 'Single perpetrator with outsourced services'. Explanation: How the criminal enterprise was organized.",
        "known_associates_or_recruits": ["Names or descriptions of key accomplices"]. Explanation: Individuals who played significant operational roles."
      },
      "key_associated_entities": {
        "front_companies": ["List of sham corporate names used"]. Explanation: Legal entities created to receive funds and project legitimacy.",
        "bank_accounts": ["Countries and bank names, if known"]. Explanation: The financial infrastructure used to receive and launder fees.",
        "digital_presence": ["Fake website URLs, phishing domain names, social media profiles"]. Explanation: Online assets used to lend credibility or initiate contact."
      },
      "operational_timeframe": {
        "suspected_inception_year": "YYYY(-MM). Explanation: When the first known fraudulent approach was made or the planning phase concluded.",
        "peak_activity_period": "YYYY-YYYY. Explanation: The period during which the scheme was most aggressively executed and/or recruited the most victims.",
        "public_collapse_year": "YYYY(-MM). Explanation: The moment it became irreversibly public through arrest, regulatory action, or major media exposure.",
        "duration_years": "X. Explanation: The total lifespan, indicating sustainability and evasion capability.",
        "timeline_of_major_fraudulent_offers": ["Chronological list of specific 'deals' or 'opportunities' presented, if documented"]."
      },
      "estimated_global_scale": {
        "currency_primary": "USD/EUR/etc.",
        "total_fees_collected_estimate": "XX million/billion. Explanation: The best estimate of actual upfront payments received from victims.",
        "promised_payout_fictitious_value": "XX billion. Explanation: The aggregate sum of money, goods, or returns falsely promised to victims.",
        "victim_count_estimate": "Approximate number. Explanation: Often difficult to ascertain due to underreporting.",
        "victim_profile_archetype": "e.g., 'Small business owners seeking capital', 'Elderly individuals with savings', 'Greed-driven investors ignoring risk'. Explanation: The common characteristics exploited.",
        "geographic_reach_sourcing": ["Countries where perpetrators operated from"]. Explanation: Often different from victim locations.",
        "geographic_reach_victims": ["Countries where victims were located"]. Explanation: Demonstrates the transnational nature."
      },
      "central_narrative_hook": "A one-sentence summary of the core fabricated story used to justify the advance fee. e.g., 'To release a multimillion-dollar inheritance trapped in a foreign bank, a small tax/fee must be paid.' Explanation: The fundamental lie upon which the scheme is built."
    },
    "stage_I_-_notionally_normal_starting_point": {
      "prevailing_socioeconomic_context": {
        "economic_conditions": "e.g., 'Period of low interest rates driving search for yield', 'Economic downturn creating financial desperation'. Explanation: The broader environment that made the hook plausible.",
        "technological_landscape": "e.g., 'Proliferation of email but low public awareness of phishing', 'Rise of online classifieds but weak verification systems'. Explanation: The tools available to perpetrators and the vulnerabilities they exploited."
      },
      "culturally_accepted_beliefs_exploited": {
        "trust_in_institutions": "e.g., 'Blind faith in official-looking documents', 'Assumption that banks rigorously vet clients'. Explanation: The societal norms about authority and process that were weaponized.",
        "financial_aspirations_myths": "e.g., 'The belief in get-rich-quick opportunities', 'The idea that exclusive deals come through personal connections'. Explanation: The common dreams or biases that overrode skepticism.",
        "knowledge_gaps": "e.g., 'Lack of public understanding of international finance law', 'Unfamiliarity with legitimate business proposal protocols'. Explanation: Specific areas of public ignorance."
      },
      "existing_precautionary_norms": {
        "relevant_laws_pre_fraud": "e.g., 'Mail fraud statutes existed but were domestically focused', 'Banking secrecy laws in Jurisdiction X hindered cross-border investigation'. Explanation: The legal framework that was theoretically protective but practically inadequate.",
        "common_sense_advice": "e.g., 'Proverbs like "If it sounds too good to be true..."', 'Advice from consumer groups to never wire money to strangers'. Explanation: The informal, cultural safeguards that were ignored or circumvented.",
        "industry_best_practices_victim_side": "e.g., 'Investors were advised to conduct due diligence', 'Banks had posters warning about wire fraud'. Explanation: The professional norms that victims failed to apply."
      }
    },
    "stage_II_-_incubation_period": {
      "early_warning_signs_ignored": {
        "victim_complaints_pattern": "e.g., 'Isolated reports to local police were dismissed as civil matters or investor disputes', 'Internet forum posts describing similar approaches were seen as isolated'. Explanation: How early signals failed to coalesce into a recognized pattern.",
        "regulatory_or_bank_anomalies": "e.g., 'Unusual volume of wire transfers to a specific foreign country noted by compliance software but manually overridden', 'Rapid opening and closing of corporate accounts by the same individuals'. Explanation: Technical red flags that were missed or rationalized.",
        "media_coverage_if_any": "e.g., 'One-off article in a niche publication about a 'strange investment offer''. Explanation: Early, limited public exposure that did not gain traction."
      },
      "perpetrator_methodology_refinement": {
        "initial_approach_vectors": "e.g., 'Began with poorly typed mass postal mailings', 'Experimented with fax broadcasts'. Explanation: The crude initial methods.",
        "adaptation_and_improvement": "e.g., 'Shifted to targeted email with improved grammar and forged letterheads', 'Started using voice-over-IP to create fake call center backgrounds'. Explanation: How the scam evolved to appear more credible.",
        "narrative_elaboration": "e.g., 'Developed a complex backstory involving a dying philanthropist', 'Created fake government websites to 'verify' the existence of a fund'. Explanation: The deepening of the fictional world to overwhelm victim skepticism."
      },
      "enabling_factors_accumulation": {
        "technological_enablers": "e.g., 'Introduction of anonymous pre-paid cell phones', 'Launch of a new free webmail service without sender verification'. Explanation: New tools that lowered the cost and risk for perpetrators.",
        "regulatory_gaps_exploited": "e.g., 'Jurisdiction X had no law against possessing fake diplomatic credentials', 'International cooperation treaties had slow, bureaucratic processes'. Explanation: Specific loopholes or weaknesses in the system.",
        "financial_system_vulnerabilities": "e.g., 'Certain offshore banks offered 'no questions asked' account opening', 'Digital payment processors had lax merchant verification for small businesses'. Explanation: Weak points in the global financial network."
      }
    },
    "stage_III_-_precipitating_event": {
      "event_description": "A detailed narrative of the specific incident that triggered collapse. e.g., 'A victim who was a former federal agent recognized the scam and initiated a formal, high-priority investigation', 'A major financial institution, acting as a custodian, demanded an impossible audit after a whistleblower tip', 'A perpetrator was arrested on an unrelated charge and their detailed records were seized'. Explanation: The catalyst that moved the scheme from hidden to exposed.",
      "immediate_trigger_type": "e.g., 'Internal Whistleblower', 'Aggressive Investigative Journalism', 'Law Enforcement Sting Operation', 'Victim with Specialized Knowledge', 'Competitive Pressure within Criminal Network'. Explanation: The source of the precipitating force.",
      "key_actors_in_precipitation": {
        "individual_entity_name": "[e.g., 'Investigative reporter Jane Smith', 'Detective John Doe', 'Whistleblower inside the front company'].",
        "their_role": "What specific action they took that was decisive.",
        "their_motivation": "e.g., 'Professional duty', 'Personal loss', 'Financial reward', 'Ethical conviction'."
      },
      "perpetrator_response_to_precipitation": "e.g., 'Attempted to flee the country', 'Launched a counter-narrative accusing regulators of a witch hunt', 'Frantically tried to return some funds to quiet a key victim'. Explanation: The immediate, defensive actions as control was lost."
    },
    "stage_IV_-_onset": {
      "immediate_consequences_collapse": {
        "public_revelation_channel": "e.g., 'Front-page newspaper headline', 'Regulatory press conference', 'Freezing order published on court website'. Explanation: How the news broke to the wider world.",
        "victim_realization_process": "e.g., 'Victims discovered when promised wire transfers did not arrive', 'A dedicated victim hotline was overwhelmed with calls', 'Account statements suddenly became unavailable'. Explanation: The moment of truth for the defrauded.",
        "financial_market_reaction_if_applicable": "e.g., 'Shares in a related legitimate sector fell due to guilt by association', 'Increased volatility in a specific market'."
      },
      "regulatory_law_enforcement_immediate_actions": {
        "emergency_orders": "e.g., 'Asset freeze injunction against Entity A', 'Cease and desist order served', 'Appointment of a receiver to take control of remaining assets'. Explanation: The first legal steps to staunch the bleeding.",
        "arrests_made": ["Names, dates, and initial charges for key perpetrators apprehended in the immediate aftermath."],
        "public_warnings_issued": "The content and tone of immediate consumer alerts from regulators or police."
      },
      "perpetrator_infrastructure_dismantling": {
        "accounts_frozen": "Number and estimated value.",
        "websites_taken_down": "By whom (e.g., hosting provider, law enforcement).",
        "premises_raided": "Locations and what was seized."
      },
      "media_narrative_initial": "The dominant framing in the first 72 hours of coverage. e.g., 'How a sophisticated scheme fooled everyone', 'The hunt for the mastermind', 'Victims tell their stories of shame and loss'. Explanation: Sets the tone for public perception."
    },
    "stage_V_-_rescue_and_salvage": {
      "victim_crisis_management": {
        "support_mechanisms_established": "e.g., 'Victim compensation fund announced', 'Dedicated psychological counseling hotline set up by a charity', 'Pro bono legal clinics for victims'. Explanation: Ad hoc measures to address the human toll.",
        "asset_recovery_efforts_initial": "e.g., 'Receivers identified and secured X% of funds from a secondary bank account', 'First round of clawback lawsuits filed against early 'winning' investors'. Explanation: The frantic scramble to locate and reclaim lost money."
      },
      "ad_hoc_regulatory_policy_patches": {
        "emergency_guidance_issued": "e.g., 'Financial Conduct Authority issues urgent bulletin reminding firms of their wire transfer verification duties', 'Central Bank advises member banks to scrutinize transactions to Country Y'. Explanation: Quick-fix directives to prevent immediate copycats.",
        "temporary_task_forces": "e.g., 'Joint FBI-SEC 419 Scam Task Force formed', 'Interpol notice circulated to member countries'. Explanation: Organizational Band-Aids."
      },
      "industry_reaction_immediate": {
        "financial_institutions": "e.g., 'Banks temporarily tightened rules for opening corporate accounts', 'Payment processors added new flags for 'inheritance' or 'lottery' related keywords'. Explanation: Defensive changes by private sector intermediaries.",
        "media_self_critique": "e.g., 'Editorials questioning why earlier warnings weren't heeded', 'Interviews with experts on how to spot fraud'. Explanation: The media's role in managing the aftermath."
      },
      "key_legal_milestones_initial": "e.g., 'Perpetrator X pleads not guilty, bail denied', 'First civil class-action lawsuit is filed against Bank Z for negligence'. Explanation: The first steps in the long legal process."
    },
    "stage_VI_-_full_cultural_readjustment": {
      "official_investigations_inquiries": {
        "government_commission_report": "e.g., 'The Senate Permanent Subcommittee on Investigations published a 300-page report titled 'The [Scheme Name] Failure''. Explanation: The formal, high-level post-mortem.",
        "regulatory_agency_after_action_review": "Key findings and admitted failures from the relevant watchdog bodies.",
        "convictions_sentences_final": "A summary of the final legal outcomes for key perpetrators, including prison terms and restitution orders."
      },
      "new_laws_regulations_enacted": {
        "specific_legislation": "e.g., 'The Advance Fee Fraud Prevention Act of 20XX, which mandated clearer disclosures and created a central database of known fraud proposals'. Explanation: The durable legal changes born from the scandal.",
        "international_treaties_cooperation": "e.g., 'Memorandum of Understanding between Countries A and B on rapid sharing of fraud-related financial intelligence'. Explanation: Changes to cross-border protocols.",
        "enhanced_consumer_protection_rules": "e.g., 'Mandatory cooling-off period for high-value wire transfers', 'Banks required to provide explicit warnings for transactions to high-risk jurisdictions'."
      },
      "long_term_industry_practice_changes": {
        "due_diligence_standards": "e.g., 'KYC (Know Your Customer) requirements became more rigorous and digitally enabled', 'Investment advisors now required to document specific warnings about unsolicited offers'. Explanation: Professional norms that hardened.",
        "technological_defenses": "e.g., 'Widespread adoption of DMARC email authentication protocols by corporations', 'Banks implemented real-time AI transaction monitoring for fraud patterns'. Explanation: Technical upgrades spurred by the event."
      },
      "shift_in_public_awareness_culture": {
        "educational_campaigns_permanent": "e.g., 'National 'Scam Awareness Month' becomes an annual fixture', 'The fraud's story is incorporated into high school financial literacy curricula'. Explanation: Institutionalized public education.",
        "lexicon_changes": "e.g., 'The term '419' entered the global lexicon as synonymous with advance-fee fraud', 'The phrase '[Perpetrator's Name]ed' becomes slang for being scammed'. Explanation: Linguistic legacy.",
        "enduring_narrative_in_pop_culture": "e.g., 'The scheme was featured in a popular documentary series', 'It inspired a subplot in a bestselling novel'. Explanation: How the event was memorialized in culture."
      },
      "residual_vulnerabilities_assessment": "An analysis of what gaps or new risks remain despite the readjustment. e.g., 'While email scams are better filtered, fraudulent approaches have migrated fully to encrypted messaging apps and social media platforms, creating new detection challenges'. Explanation: Acknowledging that fraud evolves in response to defenses."
    },
    "analysis_synthesis": {
      "primary_failure_of_foresight": "A concise statement identifying the core cultural or systemic blind spot that allowed the scheme to incubate and succeed. e.g., 'The failure to recognize that technological globalization had outstripped the jurisdictional and investigative reach of domestic financial regulation, creating fertile ground for transnational fictioneering.'",
      "scheme_archetype_classification": "e.g., 'High-volume, low-complexity mass phishing', 'Low-volume, high-complexity 'big con' targeting institutions'. Explanation: Categorizing its place in the fraud taxonomy.",
      "most_effective_psychological_lever": "The specific human bias most successfully exploited. e.g., 'Greed overpowering prudence', 'The desire to help (in fake charity scams)', 'Fear of missing out (FOMO) on a limited opportunity', 'Authority bias from forged official documents'.",
      "legacy_summary": "One paragraph summarizing the long-term impact of this specific scheme on the fight against advance-fee fraud."
    }
  }
}
"""