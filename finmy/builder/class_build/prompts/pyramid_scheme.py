
def pyramid_scheme_prompt() -> str:
    return """
You are a financial historian and forensic analyst specializing in deconstructing complex frauds.

**Objective:** Reconstruct a specified pyramid scheme event in exhaustive, multi-dimensional detail by synthesizing user-provided materials and/or retrieved internet information. Your output must form a definitive, deeply researched narrative of the scheme's entire lifecycle, structures, impacts, and aftermath, structured as a comprehensive JSON document.

**Output Format:** A single, extensive JSON object that serves as a complete case study.

**Instructions for JSON Construction:**
1.  **Base Structure:** Root key is `"pyramid_scheme"`. The object must be organized into the following top-level sections: `metadata`, `scheme_mechanics_and_operations`, `participant_ecology`, `stage_I_-_notionally_normal_starting_point`, `stage_II_-_incubation_period`, `stage_III_-_precipitating_event`, `stage_IV_-_onset`, `stage_V_-_rescue_and_salvage`, `stage_VI_-_full_cultural_readjustment`, `long_term_legacy_and_analysis`. Each section contains nested objects for granularity.
2.  **Lifecycle Phases:** Populate the six stages (I-VI) by mapping the factual chronology of the event onto the sociological framework of failure. For each stage, detail the specific conditions, actions, perceptions, and discrepancies that defined it. Treat these stages as the narrative spine of the event.
3.  **Granular Fields:** Every field, from the highest section to the deepest nested property, must be populated with specific, concrete data. Avoid generalizations. Use precise figures, dates, names, direct quotes (attributed), legal citations, and detailed descriptions. Where exact data is unavailable, provide best estimates labeled as such (e.g., "estimated_"). Do not leave fields empty; use "Data not confirmed" or "Information not widely documented" where necessary.
4.  **Integrated Explanation:** Each field's value must itself be an explanatory narrative. The value should not be just a name or number but a detailed fact with context. For example, a perpetrator's name should be accompanied by their role and background; a legal charge should include the relevant statute and potential penalty. The "Explanation" in the schema outline is a directive for you, not a field to output.
5.  **Fact-Based:** Strictly adhere to verified information from sources. Distinguish between confirmed facts, widespread reports, allegations, and theories. Corroborate key details across multiple points in the JSON (e.g., a regulatory failure in Stage II should align with the legal response in Stage V).
6.  **Comprehensiveness:** The JSON must paint a complete picture. Cover: origins and inspiration; precise recruitment methods and rhetoric; financial flows and ledger specifics (real and fabricated); technological tools used (websites, payment systems); demographic and psychological profiles of victims/perpetrators; internal communications evidence; regulatory interactions pre-collapse; moment-by-moment collapse dynamics; legal proceedings for all major actors; asset recovery specifics; media narrative evolution; changes to laws and regulations; academic and cultural references; and comparative analysis to other schemes.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "pyramid_scheme_reconstruction": {
    "metadata": {
      "scheme_common_name": "[The most widely recognized name for the scheme, e.g., 'Bernie Madoff Investment Scandal'. Include aliases and local language names.]",
      "official_legal_case_name": "[The formal title of the leading prosecution or regulatory action, e.g., 'Securities and Exchange Commission v. Bernard L. Madoff Investment Securities LLC'. Include case numbers and jurisdictions.]",
      "primary_perpetrator_name": "[Full name, aliases, and title(s) of the key architect, e.g., 'Bernard Lawrence Madoff'. Detail their public persona versus private actions.]",
      "key_associated_entities": ["List of legal entities used: corporate names, LLCs, funds, charities, front companies. Specify jurisdiction of incorporation and stated business purpose for each."],
      "operational_timeframe": {
        "suspected_inception_year": "YYYY(-MM). The estimated year(-month) the core fraudulent activity began, based on forensic analysis or later testimony.",
        "public_collapse_year": "YYYY(-MM-DD). The precise date or month the scheme became publicly known and halted operations (e.g., arrest date, regulatory freeze, public announcement).",
        "duration_years": "X years, Y months. The calculated operational lifespan from suspected inception to public collapse.",
        "key_milestones_timeline": ["Chronological list of major operational expansions, product launches, geographic entries, or significant internal events."]
      },
      "estimated_global_scale": {
        "currency": "Primary currency for figures (e.g., USD).",
        "amount_at_collapse": "XX.XX billion. The approximate nominal value of investor claims, promised liabilities, or missing funds as filed in bankruptcy or by the receiver.",
        "victim_count_estimate": "Approximate number of direct investor-creditors, with breakdown if available (e.g., individuals: ~XX,000, institutions: ~XX).",
        "geographic_reach": ["List of primary countries and regions with significant victim clusters or operational presence, ranked by exposure."],
        "known_promised_returns": "Specific annual or monthly return rates advertised to investors (e.g., '10-12% annually, consistently')."
      },
      "categorization_tags": ["Multi-level marketing (if hybrid)", "Ponzi scheme (if using new investments to pay old)", "Cryptocurrency-based", "High-yield investment program (HYIP)", "Gifting circle", "etc."]
    },
    "scheme_mechanics_and_operations": {
      "recruitment_structure": {
        "hierarchy_model": "[Detailed description: e.g., 'Binary forced matrix', 'Unilevel with breakaways', 'Simple investor-referral tiers'. Include diagram description if complex.]",
        "compensation_plan_details": "[Exact commission, bonus, and override structure. How much did recruiting a new member at various levels pay? Were there fast-start bonuses, car bonuses, leadership pools?]",
        "required_buy-in": "[Minimum investment or product purchase required to join, with tiers. Was it framed as an 'investment', 'donation', 'product kit', or 'membership fee'?]"
      },
      "product_or_service_facade": {
        "description": "[What tangible or intangible product/service was ostensibly sold? e.g., 'Self-improvement courses', 'Cryptocurrency trading bots', 'Health supplements', 'None - pure investment contract'.]",
        "actual_role": "[Was it overpriced, worthless, or non-existent? Was it a mere token to disguise the recruitment scheme? Detail the disconnect between cost and value.]",
        "inventory_loading_evidence": "[Evidence that participants were encouraged to buy more product than they could sell to qualify for bonuses.]"
      },
      "financial_architecture": {
        "bank_accounts_jurisdictions": ["List of banks and countries used for holding funds. Were there attempts to use offshore havens?"],
        "payment_methods_accepted": "[e.g., Wire transfers, checks, credit cards, cryptocurrency (specify types), cash.]",
        "fund_flow_diagram_description": "[Narrative of how money moved: from new investors to old investors, to perpetrator's accounts, to operational expenses, to luxury assets.]",
        "record_keeping_fraud": "[Description of falsified documents: fabricated account statements, trading confirmations, audit reports, website backend data.]"
      },
      "technological_infrastructure": {
        "primary_websites_portals": ["URLs and purposes (e.g., member backoffice, public marketing)."],
        "software_tools_used": "[Custom-built platforms, off-the-shelf MLM software, trading platform simulators.]",
        "communication_channels": "[Primary methods for member coordination: private social media groups (Facebook, Telegram), in-person rallies, conference call systems.]"
      }
    },
    "participant_ecology": {
      "perpetrators_core_ring": [
        {
          "name": "[Name and title]",
          "role": "[e.g., Founder/Architect, CFO/Money Launderer, Lead Promoter/Spokesperson, Legal Counsel (complicit), Technology Lead]",
          "background": "[Relevant prior career, education, credentials (legitimate or falsified).]",
          "ultimate_fate": "[Legal sentence, fines, restitution orders, current status.]"
        }
      ],
      "prominent_recruiters_influencers": [
        {
          "name": "[Top recruiter/'ambassador' name]",
          "recruitment_network_size_estimate": "[Number of downline members they directly/indirectly brought in.]",
          "public_profile": "[Were they a social media influencer, community leader, celebrity endorser?]",
          "legal_status": "[Were they charged as co-conspirators or sued civilly? Outcome.]"
        }
      ],
      "victim_demographics_profile": {
        "common_traits": "[e.g., 'Retirees seeking yield in low-interest environment', 'immigrant communities with strong intra-community trust', 'young tech enthusiasts attracted to crypto narratives', 'members of specific religious or social groups'.]",
        "psychological_appeals": "[Key emotional triggers: greed/fear of missing out (FOMO), desire for community/belonging, trust in authority figures, financial desperation.]",
        "recruitment_venues": "[Where were they targeted? Social media (specific platforms), church groups, investment seminars, family gatherings, workplace.]"
      },
      "external_enablers_questionable": [
        {
          "entity": "[e.g., Specific bank that ignored red flags, law firm that provided opinion letters, auditor that gave clean reports, payment processor.]",
          "nature_of_involvement": "[What service did they provide, and what warnings did they allegedly ignore?]",
          "post_collapse_accountability": "[Were they sued, fined, or investigated? Outcome.]"
        }
      ]
    },
    "stage_I_-_notionally_normal_starting_point": {
      "prevailing_economic_sentiment": "[Macro-economic conditions: e.g., 'Period of historically low interest rates pushing investors toward alternative yields', 'Rapidly rising asset (e.g., crypto) prices creating get-rich-quick mentality'.]",
      "relevant_regulatory_landscape": "[Description of laws and regulatory bodies ostensibly overseeing the activity. Were there gaps or ambiguities? e.g., 'Cryptocurrency offerings existed in a regulatory gray zone regarding securities classification.']",
      "cultural_social_norms_exploited": "[Deep-seated beliefs that the scheme mirrored or perverted: e.g., 'Trust in community and kinship networks', 'American Dream narrative of entrepreneurial wealth', 'Faith in mathematical and algorithmic certainty'.]",
      "perpetrator_initial_credibility_sources": "[What legitimate achievements, associations, or credentials did the perpetrator have or fabricate to gain initial trust? e.g., 'Former board member of reputable exchange', 'Falsified Ivy League degree', 'Endorsement from a respected but deceived figure'.]"
    },
    "stage_II_-_incubation_period": {
      "accumulating_anomalies_warnings_ignored": [
        {
          "warning_source": "[e.g., 'Financial analyst Harry Markopolos', 'Whistleblowing employee', 'Competitor due diligence', 'Skeptical journalist']",
          "date_era": "Approximate time.",
          "specific_concern_raised": "[The precise mathematical, logical, or operational inconsistency identified.]",
          "reason_for_dismissal": "[Why was it ignored? e.g., 'Regulatory resource constraints', 'Perpetrator's prestige and reputation', 'Lack of jurisdictional clarity', 'Victims' unwillingness to believe'.]"
        }
      ],
      "internal_dissonance_within_scheme": {
        "operational_strains": "[Signs of stress as growth slowed: delays in payout processing, changes to withdrawal rules, increased pressure on recruits.]",
        "fabrication_intensity": "[Increasing complexity of lies needed to maintain facade: more detailed fake reports, more elaborate excuses for lack of transparency.]"
      },
      "regulatory_interactions_pre_collapse": [
        {
          "agency": "[e.g., SEC, FCA, FINRA, state securities regulator]",
          "date": "YYYY-MM",
          "nature_of_inquiry": "[e.g., Routine examination, specific investor complaint, media inquiry.]",
          "scheme_response": "[How did the scheme satisfy or deflect the regulator? e.g., 'Provided falsified audit reports', 'Argued it was not a security but a product sale'.]",
          "outcome": "[Was the case closed? Was a minor settlement reached without admitting guilt?]"
        }
      ]
    },
    "stage_III_-_precipitating_event": {
      "trigger_event_description": "[The specific, identifiable event that broke the cycle: e.g., 'A coordinated wave of redemption requests from major investors triggered by the Lehman Brothers collapse', 'A key payment processor froze accounts due to banking partner concerns', 'A major investigative media piece was published', 'A whistleblower filed a definitive complaint with law enforcement.']",
      "immediate_catalyst_context": "[Why did this happen *then*? Link to external macroeconomic shock, loss of a major recruiter, internal liquidity crunch.]",
      "first_public_acknowledgment": "[Who said what and when? e.g., 'On December 10, 2008, Madoff told his sons the business was a fraud; they reported to authorities the next day.', 'A post on the scheme's official Telegram channel announced a 'temporary pause' on withdrawals.']",
      "perpetrator_immediate_actions": "[Did they confess, flee, attempt to secure funds, or blame others?]"
    },
    "stage_IV_-_onset": {
      "collapse_dynamics_sequence": ["Chronological hour-by-hour or day-by-day account of the first week: freezing of websites, seizure of assets by authorities, public statements from regulators, panic in member forums."],
      "immediate_financial_loss_realization": "[The moment victims understood money was gone. Description of failed login attempts, bounced checks, locked forums.]",
      "social_and_community_impact": ["Reports of suicides, familial breakdowns, community shaming and blame, violent threats between participants."],
      "initial_law_enforcement_actions": ["Arrests made, assets frozen by court order, offices raided - with specific dates and agencies."],
      "media_storm_character": "[Tone and focus of initial media coverage: sensationalist, sympathetic to victims, investigative, blaming regulators?]"
    },
    "stage_V_-_rescue_and_salvage": {
      "appointment_of_legal_oversight": {
        "receiver_trustee_name": "[Name of court-appointed individual/firm.]",
        "mandate": "[Goals: asset recovery, victim identification, claims processing, litigation against enablers.]"
      },
      "asset_tracing_recovery_efforts": {
        "major_assets_seized": ["List: real estate (addresses), vehicles (makes/models), artwork, jewelry, bank account balances, cryptocurrency wallets."],
        "clawback_litigation_strategy": "[Were profits from early investors ('net winners') sued to redistribute funds? Describe key cases.]",
        "estimated_recovery_rate_current": "X% of total claimed losses. Updated figure if available."
      },
      "victim_compensation_process": {
        "claims_filing_process": "[How victims registered their claims: online portal, mailed forms, deadlines.]",
        "fund_distribution_waves": "[Description of interim and final payouts made to date, amounts distributed.]",
        "victim_advocacy_groups": ["Names and roles of groups formed to represent victim interests."]
      },
      "criminal_justice_proceedings_initial": {
        "pleas_entered": "[Who pled guilty and to what charges?]",
        "key_initial_sentencings": "[Sentences for the first wave of defendants, highlighting the primary perpetrator's sentence.]"
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "official_inquiries_reports": [
        {
          "authoring_body": "[e.g., US Senate Subcommittee, National Regulator, Inspector General]",
          "report_title_publication_date": "[Full title and date.]",
          "key_findings_on_failure": "[List of systemic failures identified: regulatory silos, lack of expertise, deference to prestige.]",
          "recommendations_made": ["Specific proposed changes to law, regulation, or procedure."]
        }
      ],
      "legislative_regulatory_changes": [
        {
          "new_law_regulation_name": "[e.g., 'Dodd-Frank Wall Street Reform Act (specific sections)', 'SEC Rule XYZ-amended'.]",
          "jurisdiction": "[Country/State]",
          "direct_inspiration_link": "[How was this change a direct response to this scheme's mechanics?]"
        }
      ],
      "industry_practice_shifts": "[Changes in due diligence by banks, auditors, and legitimate MLM companies. New red flags added to training manuals.]",
      "academic_and_media_incorporation": "[References: business school case studies, documentary films, books, podcast series that cemented the scheme in public memory.]",
      "long_term_societal_perception": "[How did this event permanently alter public discourse? e.g., 'Increased skepticism towards consistent high returns', 'Heightened awareness of affinity fraud', 'Meme-ification of the perpetrator's name as a symbol of fraud'.]"
    },
    "long_term_legacy_and_analysis": {
      "historical_comparisons": "[Similarities and differences to classic schemes (Ponzi, Madoff) and why this case is distinct.]",
      "technological_innovation_aspect": "[Did it pioneer a new method of fraud (e.g., use of social media algorithms, crypto)?]",
      "unresolved_questions_conspiracies": "[Persistent theories: hidden funds offshore, unidentified co-conspirators, alleged intelligence agency links.]",
      "enduring_impact_on_victim_community": "[Qualitative description of the community's status years later: ongoing trauma, resilience stories, permanent financial damage.]"
    }
  }
}
    """