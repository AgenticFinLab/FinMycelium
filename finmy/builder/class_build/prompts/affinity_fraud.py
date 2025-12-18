def affinity_fraud_prompt() -> str:
    return """
You are a forensic financial historian and narrative reconstruction specialist, specializing in deconstructing complex affinity fraud schemes into their constituent chronological, sociological, and systemic components.

**Objective:** To meticulously reconstruct a specified or researched affinity fraud event by populating a comprehensive, multi-layered JSON schema. This schema must function as a holistic case study, capturing not only the factual timeline but also the psychological, cultural, and regulatory ecosystem that enabled the fraud to germinate, thrive, and ultimately collapse.

**Output Format:** A single, extensive JSON object, structured according to the detailed schema provided.

**Instructions for JSON Construction:**
1.  **Base Structure:** Strictly adhere to the top-level keys provided (`metadata`, `stage_I_-_notionally_normal_starting_point`, `stage_II_-_incubation_period`, `stage_III_-_precipitating_event`, `stage_IV_-_onset`, `stage_V_-_rescue_and_salvage`, `stage_VI_-_full_cultural_readjustment`). Each stage is a container for multiple detailed objects.
2.  **Lifecycle Phases:** Populate each stage with the granular field objects described below. Treat each stage as a chapter in a narrative, where fields provide the specific scenes, characters, and dialogues. The progression from Stage I to VI must tell a coherent story of societal and institutional failure.
3.  **Granular Fields:** For every field object within a stage, provide rich, specific, and concrete data. Avoid summaries; instead, provide discrete data points, illustrative examples, direct quotes (where available), named individuals, specific dates, and detailed mechanisms.
4.  **Integrated Explanation:** For each field, the value must be a string that seamlessly integrates the factual data *and* its explanatory significance. The format should be: `"[Specific factual data, names, amounts, quotes, etc.]. Explanation: [This explains *why* this fact is significant in the context of the stage and the overall fraud, e.g., how it built trust, exploited a norm, revealed a weakness, or triggered a response.]"`
5.  **Fact-Based:** All information must be derived from the user-provided materials or, if instructed to research, from credible, verifiable sources (court documents, regulatory filings, authoritative news reports, academic analyses). Do not invent or speculate. If crucial information for a field is unavailable, state "Information not specified in provided materials" and explain its relevance in the context.
6.  **Comprehensiveness:** The goal is to create the most detailed possible portrait of the event. Use all provided fields. The `metadata` section sets the factual scene. Stages I-VI deconstruct the process. Consider financial mechanics, social dynamics, legal frameworks, media narratives, and aftermath.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "affinity_fraud_reconstruction": {
    "metadata": {
      "scheme_common_name": "[e.g., 'The [Religious Group] Investment Fund Scandal']. The colloquial or media-given name for the fraud.",
      "official_legal_case_name": "[e.g., 'U.S. Securities and Exchange Commission v. [Entity Name], Civil Action No. XX-XXXX']. The formal title from the primary litigation.",
      "primary_perpetrator_name": "[Full Name]. The central individual responsible for designing and/or operating the scheme. Explanation: Often a charismatic insider of the targeted community.",
      "perpetrator_background": "[Occupation, prior reputation, family ties, and role within the targeted community]. Explanation: Establishes credibility and access.",
      "key_associated_entities": ["[Entity 1 LLC]", "[Entity 2 Trust]", "[Fictitious Fund Name]"]. Explanation: The legal or sham vehicles used to channel funds and create legitimacy.",
      "targeted_affinity_group": {
        "primary_identity_marker": "[e.g., 'Ethnic Diaspora', 'Specific Religious Congregation', 'Retiree Community', 'Immigrant Group']. Explanation: The core shared characteristic exploited.",
        "group_characteristics": "[Description of group size, cohesion, socioeconomic profile, shared values]. Explanation: Highlights why the group was vulnerable.",
        "geographic_concentration": "[Primary cities, neighborhoods, or countries]. Explanation: Shows the physical and social network used for dissemination."
      },
      "operational_timeframe": {
        "suspected_inception_year": "YYYY(-MM). The estimated start of active solicitation or fraudulent accounting.",
        "public_collapse_year": "YYYY(-MM). The date of regulatory action, public confession, or media exposé.",
        "duration_years": "X. The operational lifespan.",
        "key_milestones": ["YYYY-MM: First major investor group recruited", "YYYY-MM: First internal whistleblower concern", "YYYY-MM: Peak of fund inflows"]. Explanation: Critical internal timeline points."
      },
      "estimated_global_scale": {
        "currency": "USD",
        "amount_at_collapse": "XX billion/million. The best estimate of principal lost or fictitious assets reported.",
        "victim_count_estimate": "Number. Can be a range (e.g., '500-1000').",
        "geographic_reach": ["Country A", "Country B"]. Explanation: Demonstrates transnational exploitation of diaspora networks if applicable.",
        "notable_victim_profiles": "[e.g., 'Widows, small business owners, church leaders']. Explanation: Humanizes the impact and shows targeting within the group."
      },
      "fraud_mechanism_classification": {
        "primary_type": "[e.g., 'Ponzi Scheme', 'Fictitious Investment Fund', 'Real Estate Scam', 'Pyramid Scheme']. Explanation: The core financial deception.",
        "promised_return_characteristics": "[e.g., 'Guaranteed 15% annual returns, 'Risk-free', 'Halal-compliant profits']. Explanation: The lure that overrode skepticism.",
        "use_of_affinity_trust": "[Description of how community ties were leveraged, e.g., 'Testimonials from respected elders at community gatherings', 'Marketing through group newsletters']. Explanation: The specific social engineering tactic."
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "pre_fraud_community_norms": {
        "trust_level": "[Description of the inherent trust within the group, e.g., 'Handshake deals common', 'Religious authority highly respected', 'Strong preference for in-group business']. Explanation: The cultural capital the fraudster would plunder.",
        "financial_sophistication": "[General level of understanding of complex investments, access to mainstream financial advice]. Explanation: A potential vulnerability gap."
      },
      "pre_fraud_regulatory_environment": {
        "applicable_regulations": "[e.g., 'Securities Act of 1933', 'Local usury laws']. Explanation: The laws nominally in place to prevent such fraud.",
        "perceived_enforcement_gaps": "[e.g., 'Regulatory oversight of private religious investment clubs was minimal', 'Cross-jurisdictional complexity hindered supervision']. Explanation: The real or perceived space where the fraud could operate.",
        "community_attitude_toward_regulation": "[e.g., 'Distrust of government and banks', 'Belief that community self-policing was sufficient']. Explanation: A cultural norm that could be exploited to discourage external verification."
      },
      "perpetrators_initial_positioning": {
        "reputation_prior_to_fraud": "[e.g., 'Well-known philanthropist within the community', 'Successful local businessman', 'Kinship ties to prominent families']. Explanation: The social proof that served as initial credentialing.",
        "initial_relationship_to_victims": "[e.g., 'Fellow congregant', 'Family friend', 'Community leader']. Explanation: The pre-existing bond that lowered defenses."
      }
    },
    "stage_II_-_incubation_period": {
      "fraud_mechanism_establishment": {
        "creation_of_fictional_narrative": "[Detailed description of the investment story, e.g., 'Claims of exclusive access to pre-IPO shares of tech companies', 'Fictitious overseas commodity trading']. Explanation: The fabricated 'engine' of returns.",
        "operational_complexity_or_secrecy": "[Measures to obscure reality, e.g., 'Fabricated account statements mailed from a PO box', 'Refusal to provide online access', 'Use of technical jargon']. Explanation: Deliberate barriers to transparency.",
        "early_investor_recruitment_strategy": "[How the first victims were enrolled, e.g., 'Soft launch among perpetrator's immediate family and closest friends', 'Pilot program within a single house of worship']. Explanation: The seed phase that used the strongest trust bonds."
      },
      "exploitation_of_affinity_characteristics": {
        "leveraging_shared_identity": "[Specific examples, e.g., 'Appeals to religious duty to support community enterprises', 'Language-specific marketing materials', 'Exploiting cultural norms against questioning elders']. Explanation: The manipulation of group identity to suppress doubt.",
        "social_pressure_and_fear_of_exclusion": "[Description of dynamics, e.g., 'Early investors became evangelists, creating peer pressure to join', 'Implied that non-participants were not truly loyal to the community']. Explanation: How the scheme became self-reinforcing within the social network.",
        "co-option_of_community_institutions": "[e.g., 'Donations to group charities to appear benevolent', 'Holding meetings in community centers or places of worship']. Explanation: Using group infrastructure to lend an aura of legitimacy."
      },
      "warning_signs_and_near_misses": {
        "internal_questioning": "[Specific instances where individuals raised concerns, e.g., 'YYYY-MM: An accountant member questioned the lack of audited statements but was reassured privately']. Explanation: Suppressed signals of failure.",
        "external_red_flags": "[e.g., 'The 'fund' was not registered with the SEC as required', 'A financial journalist made an inquiry that was deflected']. Explanation: External signals that were ignored or not widely communicated within the group.",
        "rationalizations_within_community": "[The narratives used to dismiss concerns, e.g., 'The government doesn't understand our ways', 'His success is a blessing from God']. Explanation: The cultural immune system being turned against itself."
      }
    },
    "stage_III_-_precipitating_event": {
      "trigger_category": "[e.g., 'Macroeconomic Shock', 'Internal Cash Flow Crisis', 'External Investigation', 'Whistleblower Action', 'Media Exposé']. Explanation: The type of event that broke the cycle.",
      "specific_trigger_event": {
        "date": "YYYY-MM-DD (as specific as possible).",
        "description": "[Concrete, detailed description, e.g., 'A major investor, representing 30% of inflows, submitted a redemption request for $XX million due to personal financial troubles, which the scheme could not fulfill', 'The state securities regulator served a subpoena after a tip from an estranged family member', 'A national newspaper published a front-page article based on leaked internal documents']. Explanation: The precise catalyst.",
        "immediate_perpetrator_response": "[e.g., 'Attempted to stall with excuses about wire transfer delays', 'Confessed to a small inner circle in a panic', 'Fled the country']. Explanation: The first crack in the facade."
      },
      "initial_failure_containment": {
        "attempts_to_suppress": "[e.g., 'Threatened the whistleblower with legal action for defamation', 'Called a community meeting to deny the 'rumors'', 'Issued a forged bank statement']. Explanation: Efforts to maintain the illusion as the precipitating event unfolded.",
        "breakdown_of_secrecy": "[How information leaked beyond control, e.g., 'The regulator's inquiry became public record', 'The media report was shared widely on social media within the community']. Explanation: The point of no return for public awareness."
      }
    },
    "stage_IV_-_onset": {
      "public_collapse": {
        "date_of_public_revelation": "YYYY-MM-DD.",
        "method_of_revelation": "[e.g., 'Regulatory press conference', 'Perpetrator's confession letter to investors', 'Freeze order issued by a court']. Explanation: How the wider victim pool learned the truth.",
        "immediate_public_reaction": "[Description of the community's shock, e.g., 'Stunned disbelief at the community center', 'Frenzied phone calls among victims', 'Angry confrontations at the perpetrator's home']. Explanation: The emotional and social rupture."
      },
      "financial_and_social_consequences": {
        "immediate_financial_loss_realization": "[Description of the moment victims understood their loss was total, e.g., 'Account statements revealed as forgeries', 'Bank accounts frozen and empty']. Explanation: The concrete financial devastation.",
        "social_fallout_within_community": "[e.g., 'Deep divisions between early and late investors', 'Loss of trust in communal leadership', 'Stigmatization of victims as 'greedy'']. Explanation: The secondary, social trauma.",
        "notable_personal_tragedies": "[Specific, documented cases, e.g., 'One victim lost their life savings for retirement', 'A community charity was bankrupted']. Explanation: Humanizing the scale of the disaster."
      },
      "initial_institutional_response": {
        "law_enforcement_actions": "[e.g., 'FBI raided the headquarters on [Date]', 'Perpetrator arrested at their home on charges of wire fraud']. Explanation: The first formal legal response.",
        "regulatory_actions": "[e.g., 'SEC obtained an emergency asset freeze', 'State securities commissioner issued a cease-and-desist order']. Explanation: The first formal regulatory response.",
        "civil_actions_filed": "[e.g., 'Class-action lawsuit filed by firm [Law Firm Name] on behalf of investors on [Date]']. Explanation: The first steps toward civil recovery."
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "immediate_victim_support": {
        "community_led_efforts": "[e.g., 'Setting up a volunteer help desk to catalog claims', 'Organizing pro bono legal clinics']. Explanation: Grassroots, ad-hoc responses.",
        "government_or_NGO_assistance": "[e.g., 'State attorney general established a victim hotline', 'A non-profit provided financial counseling']. Explanation: Organized external support mechanisms."
      },
      "asset_recovery_initial_phase": {
        "appointed_authority": "[e.g., 'Chapter 11 Bankruptcy Trustee', 'SEC-appointed Receiver']. Explanation: The legal entity tasked with recovery.",
        "initial_asset_discoveries": "[e.g., 'Receiver identified a mortgaged mansion, luxury cars, and a small amount of cash in bank accounts', 'Most funds were traced to earlier investors in classic Ponzi fashion']. Explanation: The often-sobering reality of recoverable assets.",
        "challenges_encountered": "[e.g., 'Complex international wire trails', 'Assets hidden in family members' names', 'Lack of coherent financial records']. Explanation: Obstacles to recovery."
      },
      "criminal_justice_initial_steps": {
        "charges_filed": "['Wire Fraud', 'Securities Fraud', 'Money Laundering', 'Conspiracy']. Explanation: The specific legal accusations.",
        "key_judicial_events": ["YYYY-MM-DD: Initial appearance and plea entered", "YYYY-MM-DD: Bail hearing outcome"]. Explanation: Early procedural milestones.",
        "perpetrator_status": "[e.g., 'In custody awaiting trial', 'Released on bail with electronic monitoring']. Explanation: The immediate status of the accused."
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "formal_investigations_and_inquiries": {
        "government_commission_reports": "[e.g., 'The [State] Senate Committee on Finance issued a report titled '...' blaming lax oversight', 'The GAO published a study on affinity fraud vulnerabilities']. Explanation: High-level official analyses.",
        "internal_community_reviews": "[e.g., 'The [Religious] Diocese conducted an internal audit and issued new guidelines for financial solicitations']. Explanation: The group's own reckoning."
      },
      "long_term_legal_and_regulatory_outcomes": {
        "criminal_sentencing": "[e.g., 'Primary perpetrator sentenced to XX years in federal prison, ordered to pay $XX in restitution', 'Co-conspirators received lesser sentences']. Explanation: The final penal resolution.",
        "civil_settlements_and_judgments": "[e.g., 'Receiver distributed $XX million, representing 15 cents on the dollar, to approved claimants', 'Auxiliary parties (banks, auditors) settled for $X million']. Explanation: The financial restitution outcome.",
        "new_regulations_or_policies": "[e.g., 'State passed a law requiring enhanced disclosures for investments marketed within tight-knit communities', 'Regulator launched a multilingual investor education campaign']. Explanation: Systemic changes intended to prevent recurrence."
      },
      "enduring_sociological_impact": {
        "long_term_community_dynamics": "[e.g., 'Permanent erosion of informal trust within the community, a shift toward formal contracts', 'A generation became deeply skeptical of any 'too good to be true' community offer']. Explanation: The lasting change in social fabric.",
        "legacy_in_public_discourse": "[e.g., 'The case is cited in law school courses on securities fraud and sociology texts on trust', 'The scheme's name became a byword for betrayal within that specific diaspora']. Explanation: How the event is remembered and referenced.",
        "lessons_absorbed_vs_ignored": "[Critical analysis of what was truly learned, e.g., 'While regulations tightened, the fundamental vulnerability of exploiting tight social bonds remains', 'The case highlighted the critical need for financial literacy programs delivered in culturally competent ways']. Explanation: A meta-analysis of the readjustment's depth and limitations."
      }
    }
  }
}
"""