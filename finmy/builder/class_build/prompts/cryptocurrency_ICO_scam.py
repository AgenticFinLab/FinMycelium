def cryptocurrency_ico_scam_prompt() -> str:
    return """
You are a financial forensics historian and narrative reconstruction specialist.

**Objective:** To reconstruct a comprehensive, multi-dimensional, and deeply analytical account of a specified Cryptocurrency/ICO scam event. Your output must function as a definitive case study, meticulously documenting the event's lifecycle from conception to cultural aftermath, capturing technical, financial, social, psychological, and regulatory dimensions.

**Output Format:** A single, extensive JSON object.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must strictly adhere to the provided schema. Use the specified top-level keys (`metadata`, `stage_I_-_...`, etc.). All keys should be in snake_case. If information for a specific field is unavailable or inapplicable, populate it with `null` and consider adding a brief explanatory note in an adjacent `"_note"` field (e.g., `"field": null, "field_note": "Information not publicly disclosed in court filings."`).
2.  **Lifecycle Phases:** Populate each stage (I-VI) by analyzing the event through the lens of the "Failure of Foresight" framework. Each stage is a container for fields describing the conditions, actions, and perceptions dominant during that period. The narrative must flow logically between stages.
3.  **Granular Fields:** Every field must be populated with highly specific, concrete information. Avoid summaries. For example, instead of "marketing was aggressive," specify "marketing tactics included paid celebrity endorsements on Twitter, fabricated 'exclusive' pre-sale lists, and false partnerships announced via Medium blog posts." Use dates, names, technical specifications, monetary figures, and direct quotes where available.
4.  **Integrated Explanation:** The "Explanation" for each field (as seen in the schema outline) is a **mandatory part of the value**. For each field, you must provide the factual data followed by a clear, concise explanation of its significance within the scam's structure or narrative. Format as: `"[Factual Data]. Explanation: [Context and significance of this data point]."`
5.  **Fact-Based:** All information must be derived from the user-provided materials or, if instructed, from verified internet sources (court documents, regulatory filings, reputable news investigations, blockchain analytics reports, victim testimonials). Differentiate between confirmed facts and widespread allegations. Use fields like `"alleged_method"` or `"claimed_technology"` where appropriate.
6.  **Comprehensiveness:** The reconstruction must be exhaustive. Consider all angles: the technological facade (smart contracts, tokenomics), financial engineering (fund flows, wallets), promotional machinery (social media, influencers), legal structuring (entity creation, terms & conditions), victim demographics and psychology, internal perpetrator dynamics, external enablers (exchanges, KYC providers), and the multi-layered response from regulators, law enforcement, and the community.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "cryptocurrency_ico_scam_reconstruction": {
    "metadata": {
      "scheme_common_name": "[The most widely recognized name for the scheme, e.g., 'OneCoin', 'BitConnect', 'Pincoin & iFan Scam']. Explanation: The colloquial or media-given name that best identifies the scam.",
      "official_legal_case_name": "[e.g., 'United States v. Ruja Ignatova et al.', 'SEC v. BitConnect International PLC et al.']. Explanation: The formal title of the leading criminal or regulatory case associated with the scam.",
      "primary_perpetrator_name": "[Full name and known aliases, e.g., 'Ruja Ignatova (a.k.a. 'Cryptoqueen')']. Explanation: The individual centrally responsible for designing and/or operating the scheme, often the public face.",
      "key_associated_entities": ["List of legal entities, e.g., ['OneCoin Ltd.', 'OneLife Network Ltd.', 'One Academy']"]. Explanation: The corporate vehicles used to give the operation a semblance of legitimacy, manage funds, and limit liability.",
      "core_fraud_category": ["Select all that apply from: 'Ponzi/Pyramid Scheme', 'Fake ICO/Token Sale', 'Exit Scam/Rug Pull', 'Fake Exchange', 'Wallet/Theft Hack', 'DeFi Protocol Exploit', 'Phishing/Malware', 'Other']. Explanation: Classification of the primary fraudulent mechanism(s).",
      "operational_timeframe": {
        "suspected_inception_year_month": "YYYY-MM. Explanation: The best estimate of when the first fraudulent activity or planning began.",
        "ico_sale_or_launch_period": "YYYY-MM to YYYY-MM. Explanation: The active period of the token sale or the official launch of the associated platform.",
        "public_collapse_year_month": "YYYY-MM. Explanation: The moment the scam became irreversibly public (e.g., platform shutdown, arrest announcement, failure to process withdrawals).",
        "duration_active_months": "XX. Explanation: The approximate operational lifespan from inception to public collapse.",
        "key_milestone_dates": ["List of specific dates, e.g., ['2019-03-12: Last successful large withdrawal reported', '2019-04-15: Website goes offline']"]. Explanation: Critical dates that marked transitions in the scheme's lifecycle."
      },
      "estimated_global_scale": {
        "primary_denomination_currency": "e.g., USD, BTC, ETH. Explanation: The currency in which the scam primarily raised or denominated funds.",
        "estimated_funds_raised": "e.g., '4.0 billion USD'. Explanation: The best available estimate of total funds collected from victims, converted to a stable fiat equivalent.",
        "victim_count_estimate_range": "e.g., '3,000,000 - 4,500,000'. Explanation: The estimated range of individual investors or participants defrauded.",
        "geographic_reach_primary": ["List of countries, e.g., ['India', 'Vietnam', 'United Kingdom', 'Germany']"]. Explanation: Jurisdictions with the highest concentration of victim investments.",
        "geographic_reach_operational": ["List of countries, e.g., ['Bulgaria (headquarters)', 'Dubai (promotional events)', 'Hong Kong (shell companies)']"]. Explanation: Jurisdictions where key operational, promotional, or legal activities were based."
      },
      "core_technological_components": {
        "blockchain_claimed": "e.g., 'Proprietary blockchain named \'OneChain\''. Explanation: The blockchain technology the scam claimed to utilize.",
        "blockchain_actual": "e.g., 'No functional blockchain existed; a centralized SQL database was used'. Explanation: The actual technological backend, as revealed by investigations.",
        "token_standard_claimed": "e.g., 'ERC-20 on Ethereum'. Explanation: The claimed token standard.",
        "smart_contract_address_verified": "e.g., ['0x1234...abcd']. Explanation: On-chain addresses of any smart contracts used, if applicable and verified.",
        "wallet_addresses_linked": ["List of addresses, e.g., ['0x5678...ef01', '1A1zP1...']"]. Explanation: Cryptocurrency wallet addresses identified by investigators as controlled by perpetrators for fund aggregation."
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "broader_market_context": {
        "crypto_market_sentiment": "e.g., 'Bull market euphoria following the 2017 Bitcoin price peak, with widespread retail FOMO (Fear Of Missing Out)'. Explanation: The dominant investor psychology and market conditions that created a fertile ground for the scam.",
        "regulatory_environment": "e.g., 'ICO regulatory grey area; SEC had issued warnings but few enforcement actions against non-US entities'. Explanation: The state of cryptocurrency/ICO regulation and enforcement at the scheme's inception.",
        "prevailing_narratives": "e.g., 'Financial inclusion', 'Banking the unbanked', 'Democratization of finance', '10x-100x returns'. Explanation: The culturally accepted and heavily marketed promises that the scam later co-opted."
      },
      "scheme_specific_facade": {
        "stated_vision_and_mission": "e.g., 'To create the world's leading educational cryptocurrency, making blockchain accessible to everyone.'. Explanation: The official, publicly stated noble purpose of the project.",
        "claimed_innovation_or_usecase": "e.g., 'A token backed by mining packages that produce new coins via a proprietary, energy-efficient algorithm.'. Explanation: The specific technological or business model innovation that was marketed as the source of value.",
        "official_whitepaper_status": "e.g., 'A 30-page whitepaper published, heavy on marketing jargon but lacking technical specifications and algorithm details.'. Explanation: The nature and credibility of the foundational technical document.",
        "team_representation": "e.g., 'Website featured profiles of 'team members' with stock photos and fabricated credentials; claimed advisors from major tech firms who later denied involvement.'. Explanation: How the team was presented to establish credibility.",
        "legal_and_corporate_front": "e.g., 'Registered as a limited liability company in a jurisdiction with lax corporate disclosure laws; published generic, non-audited 'financial reports.''. Explanation: The structures created to simulate a legitimate business entity."
      }
    },
    "stage_II_-_incubation_period": {
      "accumulating_anomalies_technical": {
        "code_and_chain_analysis_red_flags": "e.g., 'Independent developers who reviewed the published smart contract code noted it contained a 'master minter' function allowing unlimited token creation by a single address.'. Explanation: Technical warnings that were overlooked or suppressed by the community.",
        "blockchain_explorer_discrepancies": "e.g., 'Transactions shown on the project's proprietary 'block explorer' could not be verified on any public blockchain explorer.'. Explanation: Discrepancies between the scam's claimed on-chain activity and verifiable reality.",
        "withdrawal_processing_issues": "e.g., 'Early reports on community forums of delayed withdrawals, initially dismissed as 'banking processing' or 'KYC delays'.'. Explanation: Early operational failures that were explained away."
      },
      "accumulating_anomalies_financial": {
        "token_economics_contradictions": "e.g., 'The promised daily ROI of 1% required exponential new investor inflow that was mathematically unsustainable.'. Explanation: Flaws in the promised financial model that indicated a Ponzi structure.",
        "fund_transparency_absence": "e.g., 'No proof-of-reserves ever provided; requests to see the 'mining farm' were denied citing 'security concerns'.'. Explanation: The lack of verifiable evidence for the claimed revenue-generating assets.",
        "unexplained_wallet_movements": "e.g., 'Blockchain analysts later identified that 95% of raised ETH was transferred to mixers or personal wallets, not to claimed development or liquidity pools.'. Explanation: Suspicious fund flows that occurred during the operational phase."
      },
      "social_and_community_dynamics": {
        "critic_suppression": "e.g., 'Critical posts on Telegram and Bitcointalk were immediately deleted by admins; critics were labeled 'FUDders' and banned.'. Explanation: Tactics used to create an echo chamber and suppress dissent.",
        "cultivation_of_true_believers": "e.g., 'A multi-tiered affiliate system rewarded promoters not just for sales, but for publicly defending the project and attacking skeptics.'. Explanation: Mechanisms that incentivized participants to become active defenders of the scheme.",
        "use_of_social_proof": "e.g., 'Staged events in large venues with paid audiences, photoshopped images of 'partnership' meetings, fake positive news articles on paid-for 'media' sites.'. Explanation: Fabricated evidence of success and legitimacy used to attract more victims."
      }
    },
    "stage_III_-_precipitating_event": {
      "trigger_event_description": "e.g., 'On January 16, 2018, the platform announced an 'unscheduled maintenance' and halted all withdrawals indefinitely.'. Explanation: The specific, undeniable event that shattered the facade of normalcy.",
      "immediate_public_reaction": "e.g., 'Panic erupted on social media; the official Telegram group was flooded with questions and then disabled by admins.'. Explanation: The first wave of public realization and communication breakdown.",
      "perpetrator_response_initial": "e.g., 'Founder released a video claiming a 'coordinated attack by whales' and promised withdrawals would resume in 7 days, which never happened.'. Explanation: The first, often deceptive, official response from the operators to the crisis.",
      "key_investigative_revelation": "e.g., 'On the same day, a major crypto news outlet published an investigation revealing the founder's prior conviction for financial fraud.'. Explanation: A concurrent external revelation that accelerated the collapse of trust."
    },
    "stage_IV_-_onset": {
      "immediate_technical_collapse": {
        "platform_status": "e.g., 'Website taken offline permanently 48 hours after the initial announcement; all social media accounts deactivated.'. Explanation: The final technical shutdown.",
        "funds_frozen_or_drained": "e.g., 'Blockchain tracking shows the remaining Ethereum in the project's main wallet was swept into a mixer within 24 hours of the website going dark.'. Explanation: The final movement of victims' funds."
      },
      "victim_realization_and_distress": {
        "community_channels_activity": "e.g., 'Victims formed new Telegram and Reddit groups to share information, grief, and attempts at organizing legal action; widespread expressions of financial ruin.'. Explanation: The emergent, self-organized victim community in the immediate aftermath.",
        "reported_personal_impacts": "e.g., 'Testimonials surfaced of individuals losing life savings, taking loans to invest, and suffering severe psychological distress.'. Explanation: The direct human consequences that became apparent."
      },
      "initial_regulatory_and_media_response": {
        "first_regulatory_warnings_issued": "e.g., 'The [Country] Financial Conduct Authority issued a public warning stating the entity was not authorized to operate.'. Explanation: The first official regulatory statements post-collapse.",
        "first_major_media_coverage": "e.g., 'Mainstream financial news networks (e.g., CNBC, Bloomberg) ran segments labeling it a 'major crypto scam'.'. Explanation: The point at which the story broke into mainstream consciousness."
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "law_enforcement_actions_initial": {
        "first_arrests_or_raids": "e.g., 'In Month YYYY, authorities in [Country] raided a known promotional office and arrested three mid-level promoters on suspicion of fraud.'. Explanation: The first tangible legal actions against individuals associated with the scam.",
        "asset_freezes_or_seizures": "e.g., 'A court in [Country] froze bank accounts and seized several luxury vehicles linked to the primary entity.'. Explanation: Initial attempts to recover and preserve assets."
      },
      "victim_self_organization": {
        "primary_online_forum_established": "e.g., 'The subreddit r/[ScamName]Victims became the central hub for information sharing, with over 10,000 members.'. Explanation: The key platform for victim coordination.",
        "class_action_lawsuits_filed": ["List of early lawsuits, e.g., ['Smith et al. v. [Scam Entity] LLC, filed in US District Court for the Southern District of New York']"]. Explanation: Legal actions initiated by victim groups.",
        "crowdsourced_investigation": "e.g., 'Victims pooled transaction IDs and wallet addresses to create a shared ledger of the scam's footprint for investigators.'. Explanation: Collaborative efforts by victims to document the fraud."
      },
      "perpetrator_fate_initial": {
        "known_whereabouts": "e.g., 'Primary founder's last known location was [Airport] in [Country] in [Month YYYY]; believed to have fled to a non-extradition country.'. Explanation: The status and location of key perpetrators immediately post-collapse.",
        "public_statements_if_any": "e.g., 'No further public statements were made by the core team; all known associates went silent.'. Explanation: Any final communications from the perpetrators."
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "legal_and_regulatory_aftermath": {
        "major_judgements_and_sentences": ["e.g., 'In YYYY, [Perpetrator Name] was sentenced to 10 years in prison for wire fraud and securities fraud by a US court.'"]. Explanation: The final outcomes of key criminal and civil cases.",
        "total_assets_recovered_estimate": "e.g., 'Less than 5% of the estimated $4 billion raised has been recovered and is subject to a lengthy restitution process.'. Explanation: The overall success (or failure) of financial recovery efforts.",
        "new_regulations_inspired": "e.g., 'The scam was cited in the [Country]'s 'Crypto Assets Bill 2023' as a key example justifying strict licensing requirements for all digital asset promoters.'. Explanation: Lasting impacts on the legal and regulatory landscape."
      },
      "industry_and_community_impact": {
        "changes_in_investor_due_diligence": "e.g., 'The 'DYOR' (Do Your Own Research) mantra evolved to include specific checks: verifying team member LinkedIn histories, auditing smart contracts, and demanding multisig treasury wallets.'. Explanation: Permanent shifts in how the crypto community assesses new projects.",
        "impact_on_legitimate_ico_and_defi_sectors": "e.g., 'Investor appetite for ICOs dried up significantly, with capital flowing instead towards regulated vehicles like IEOs (Initial Exchange Offerings) and later, DeFi yield farming.'. Explanation: How the scam altered the trajectory of related, legitimate sectors.",
        "narrative_shifts": "e.g., 'The 'educational crypto' narrative became heavily tainted. Scrutiny turned towards multi-level marketing (MLM) models in crypto.'. Explanation: Lasting changes in the types of stories and business models the community is willing to trust."
      },
      "academic_and_analytical_legacy": {
        "case_studies_published": ["e.g., ['The Anatomy of the [Scam Name] Ponzi Scheme' - Journal of Financial Crime, 2022]"]. Explanation: Scholarly work analyzing the event.",
        "common_references_in_warnings": "e.g., 'The name of the scam is now routinely used by regulators and educators as a canonical example of a non-technical, pure Ponzi scheme in the crypto space.'. Explanation: The scam's place in the permanent lexicon of financial fraud examples."
      }
    }
  }
}
"""