
def pump_and_dump_prompt() -> str:
    return """  
You are a forensic financial historian and investigative data architect specializing in securities fraud analysis.

**Objective:** To reconstruct a complete, deeply analytical, and factually precise narrative of a specific "pump and dump" scheme by populating a comprehensive, multi-stage JSON model. Your output must synthesize provided user data with internet-retrieved information to create a granular, historically accurate, and sociologically insightful case study that reflects the event's full lifecycle, impact, and legacy.

**Output Format:** A single, extensive, and valid JSON object.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must follow the exact top-level key structure provided: `pump_and_dump` containing `metadata`, `stage_I_-_notionally_normal_starting_point`, `stage_II_-_incubation_period`, `stage_III_-_precipitating_event`, `stage_IV_-_onset`, `stage_V_-_rescue_and_salvage`, `stage_VI_-_full_cultural_readjustment`, and `summary_analysis`.
2.  **Lifecycle Phases:** Populate each Stage (I-VI) meticulously. The stages are based on the "Sequence of Events Associated with a Failure of Foresight" sociological model. Interpret each stage in the context of financial fraud:
    *   **Stage I:** Describe the environment *before* the fraud began—market conditions, regulatory norms, investor psychology, and technological landscape that made the scheme plausible.
    *   **Stage II:** Detail the active but hidden accumulation of fraud—the specific manipulative actions, false narratives, and early warning signs that were missed or ignored by various parties.
    *   **Stage III:** Identify the specific trigger or discovery that caused the scheme to become public or begin its irreversible collapse.
    *   **Stage IV:** Describe the immediate aftermath of the trigger—market panic, price collapse, initial reactions from victims and perpetrators.
    *   **Stage V:** Outline the initial crisis response—regulatory actions, law enforcement steps, temporary measures to protect markets/victims.
    *   **Stage VI:** Analyze the long-term consequences—legal reforms, regulatory changes, shifts in market practices, investor education, and cultural perceptions of risk.
3.  **Granular Fields:** Every field within the JSON must be populated with highly specific, detailed information. Avoid generalizations. Use precise dates, figures, names, quotations (with sources if available), and descriptive analysis. Where exact data is unknown, provide well-reasoned estimates and note them as such (e.g., "estimated_suspected_inception_year").
4.  **Integrated Explanation:** Treat the "Explanation" in the schema as a mandatory guideline. For each field, your value should inherently contain the explanatory detail. The field's key indicates *what* the data point is, and your entered value must elaborate on the *how*, *why*, and *significance*. For example, for `primary_perpetrator_motivation`, do not just write "greed"; write "A complex motivation driven by a need to sustain a lavish lifestyle estimated at $X/month, cover losses from earlier failed ventures in [sector], and maintain a reputation as a financial wizard, which was central to their social and professional identity."
5.  **Fact-Based:** All information must be cross-referenced for accuracy. Prioritize data from official sources (court filings, SEC releases, regulatory reports, reputable news archives). Clearly distinguish between established facts, allegations, and informed analysis.
6.  **Comprehensiveness:** The JSON should be exhaustive. Consider all angles: perpetrators, victims, enablers (e.g., complicit brokers, negligent auditors), market mechanics, communication channels used for the "pump," liquidation strategies for the "dump," legal arguments, and societal impact. The `summary_analysis` section should provide a synthesized, high-level critique.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "pump_and_dump_reconstruction": {
    "metadata": {
      "scheme_common_name": "The most widely recognized name for the scheme, e.g., 'The Wolf of Wall Street Boiler Room' or 'The XYZ Crypto Pump Group'. This is the colloquial, media-friendly title.",
      "official_legal_case_name": "The formal title of the leading legal proceeding, e.g., 'Securities and Exchange Commission v. Stratton Oakmont, Inc., et al., Civil Action No. 96-CV-XXXX (S.D.N.Y.)'. Indicates the primary regulatory or criminal action.",
      "primary_perpetrator_name": "Full name and known aliases of the key architect/ringleader. The individual(s) centrally responsible for designing, orchestrating, and/or operating the core manipulative activities.",
      "key_associated_entities": ["A list of company names, funds, shell corporations, online forums, chat groups (e.g., Discord, Telegram channels), or social media profiles used as direct vehicles for executing the fraud, holding assets, or disseminating misinformation."],
      "asset_class_involved": "The specific type of financial instrument targeted, e.g., 'micro-cap/pink sheet equities', 'low-market-cap cryptocurrency (altcoin)', 'penny stocks', 'special purpose acquisition company (SPAC) warrants', 'non-fungible tokens (NFTs)'. Crucial for understanding market vulnerabilities.",
      "operational_timeframe": {
        "suspected_inception_date": "YYYY-MM-DD (or best estimate). The date the first identifiable preparatory or manipulative act occurred, such as the secret accumulation of the asset (the 'positioning' phase) or the creation of the promoting entity.",
        "core_pump_phase_dates": "YYYY-MM-DD to YYYY-MM-DD. The period during which the most intensive promotional and price-inflation activities were conducted.",
        "dump_phase_dates": "YYYY-MM-DD to YYYY-MM-DD. The period during which the perpetrators systematically sold their holdings into the inflated market.",
        "public_collapse_date": "YYYY-MM-DD. The date the scheme became publicly known, e.g., via regulatory halt, exposé article, or catastrophic price drop triggering widespread alarm.",
        "duration_total_days": "The total lifespan from suspected inception to public collapse."
      },
      "estimated_global_scale": {
        "currency_denomination": "The primary currency for valuations (e.g., USD, BTC).",
        "peak_market_cap_manipulation": "The approximate total market valuation of the targeted asset(s) at the absolute peak of the pump, indicating the scale of the artificial inflation.",
        "perpetrator_proceeds_estimate": "The estimated total gross profits realized by the perpetrators from selling during the dump phase. This is the direct financial gain from the fraud.",
        "victim_losses_estimate": "The approximate total financial loss incurred by defrauded investors. This is often higher than perpetrator proceeds due to transaction costs and broader market panic.",
        "victim_count_estimate": "Approximate number of distinct individual investors or entity accounts that purchased the asset during the pump phase and likely suffered losses.",
        "geographic_reach_of_victims": ["List of countries or regions where a significant concentration of victim investors was located, highlighting the transnational nature of modern schemes."]
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "pre_fraud_market_environment": "Description of the state of the specific asset class and broader markets before the scheme. E.g., 'A retail-driven bull market in speculative tech stocks with high liquidity and low barriers to entry via new trading apps,' or 'The early-stage, largely unregulated cryptocurrency market characterized by extreme volatility and rampant speculation on message boards.'",
      "prevalent_investor_sentiment_and_psychology": "The dominant mindset of the target investor pool. E.g., 'Fear of missing out (FOMO) on rapid gains, combined with distrust of traditional financial institutions and a belief in 'democratized finance',' or 'Search for high-yield opportunities in a zero-interest-rate environment, leading to increased risk appetite among novice investors.'",
      "regulatory_and_legal_backdrop": "The specific laws, regulations, enforcement priorities, and perceived gaps that existed. E.g., 'The SEC's focus on large-cap fraud post-2008, leading to relatively scant surveillance of micro-cap promotions on social media,' or 'Cryptocurrencies existing in a regulatory gray area, with unclear jurisdiction between SEC and CFTC.'",
      "technological_and_communication_landscape": "The platforms and tools that enabled the scheme. E.g., 'The rise of encrypted messaging apps (Telegram), influencer culture on Twitter/YouTube, and zero-commission trading platforms (Robinhood) that facilitated rapid, community-driven trading.'",
      "perpetrator_background_and_initial_position": "The biography, skills, resources, and network of the perpetrator(s) at the start. E.g., 'A former broker with a banned license, deep knowledge of high-pressure sales tactics, and a network of offshore accounts,' or 'An anonymous online influencer with a large following in crypto forums and expertise in creating memes and viral content.'"
    },
    "stage_II_-_incubation_period": {
      "secret_accumulation_phase": "Detailed narrative of how perpetrators built their initial position without detection. Includes methods (e.g., through nominee accounts, dark pool orders), volumes, price range, and duration.",
      "development_of_pump_narrative": "The construction of the false or misleading promotional story. List key themes (e.g., 'revolutionary technology,' 'exclusive government contract,' 'celebrity endorsement'), specific claims made, and fabricated evidence (fake press releases, doctored screenshots, paid 'analyst' reports).",
      "recruitment_and_coordination_mechanics": "How the promotion was organized. Detail the structure of pump groups, compensation for promoters (e.g., pre-allotted coin, cash bounties), communication protocols, and rules for members to create artificial buying pressure at a coordinated time.",
      "channels_of_dissemination": "Exhaustive list of platforms used to spread the narrative: specific subreddits, Twitter hashtags, YouTube channels, Discord servers, TikTok trends, paid stock-touting newsletters, and spam campaigns.",
      "early_warning_signals_ignored": "List red flags that emerged but were overlooked by exchanges, regulators, journalists, or the investing public. E.g., 'Unusual trading volume spikes with no news from company, noted by a few analysts on Twitter but dismissed as hype,' or 'The asset's issuer had a history of regulatory violations, buried in obscure filings.'",
      "progressive_price_inflation": "A data-rich description of the asset's price action during the pump. Include key dates of major promotional pushes, corresponding volume and price spikes, and the role of algorithmic trading or wash trading (fake transactions) in creating the illusion of demand."
    },
    "stage_III_-_precipitating_event": {
      "triggering_event_type": "The category of event that broke the scheme open. E.g., 'Investigative Journalism,' 'Whistleblower Disclosure,' 'Regulatory Trading Halt,' 'Technical Analysis by Skeptics,' 'Internal Collapse (e.g., perpetrator dispute leading to leaks).'",
      "specific_event_description": "A precise account: 'On [Date], financial blogger [Name] published a forensic report titled '[Title],' exposing the fabricated contracts and tracing the promotional network to a known felon. The report went viral on social media.'",
      "immediate_market_reaction_to_trigger": "The first 24-72 hours after the trigger. Include price movement (e.g., '30% drop in first hour'), volume surge, social media panic, and statements (or silence) from the promoting entities.",
      "first_public_responses": "Initial reactions from key figures: perpetrator denials (quote them), exchange announcements about 'reviewing activity,' regulatory 'we are aware' statements, and influential community leaders advising caution or exit."
    },
    "stage_IV_-_onset": {
      "price_collapse_dynamics": "Detailed chronology of the dump and ensuing crash. Map the rapid sell-off by perpetrators, followed by panic selling by retail investors. Note key support levels broken and liquidity drying up.",
      "victim_realization_and_reaction": "Describe the social and emotional fallout: screenshots of losses shared online, anger directed at promoters, formation of victim support groups/class action inquiries, reports to authorities.",
      "perpetrator_actions_during_collapse": "Their behavior as the scheme unraveled: cashing out remaining holdings, shutting down websites/social media, attempting to launder proceeds, fleeing jurisdiction, or making desperate attempts to restart the pump.",
      "immediate_systemic_impact": "Effects beyond direct victims. E.g., 'Increased volatility spilled over into related sector ETFs,' 'The trading platform experienced technical issues due to extreme order volume,' 'Reputational damage to the entire altcoin market.'",
      "initial_law_enforcement_and_regulatory_actions": "The first concrete steps: which agency (FBI, SEC, State Attorney General) opened an investigation, issuance of subpoenas, freezing of specific bank or exchange accounts, arrests if swift."
    },
    "stage_V_-_rescue_and_salvage": {
      "emergency_market_protections": "Actions taken by trading venues or regulators to stabilize the situation: formal trading halts, delisting of the asset, warnings issued to the public about similar schemes.",
      "victim_outreach_and_support_mechanisms": "Establishment of official channels for victim claims, launch of class-action lawsuits by major law firms, setting up of information websites by regulators.",
      "asset_tracing_and_recovery_efforts": "Early forensic work: blockchain analysis to track cryptocurrency flows, court orders to seize domestic assets, and international requests for mutual legal assistance to freeze offshore accounts.",
      "criminal_charges_and_civil_complaints_filed": "List the initial specific charges (e.g., 'wire fraud,' 'securities fraud,' 'conspiracy') and the defendants named in the first major civil or criminal filings.",
      "media_narrative_consolidation": "How the mainstream financial media framed the event in the weeks following—what lessons were being drawn, who was being blamed, and what it symbolized about the current market era."
    },
    "stage_VI_-_full_cultural_readjustment": {
      "long_term_regulatory_reforms": "Specific new rules, legislation, or enforcement initiatives catalyzed by the event. E.g., 'SEC's increased scrutiny of social media stock promotion leading to [Rule Name],' 'CFTC guidance on treating certain crypto assets as commodities,' 'Strengthened 'Know Your Customer' requirements for crypto exchanges.'",
      "changes_in_exchange_and_platform_policies": "How trading platforms adapted: stricter listing requirements for penny stocks or new tokens, improved market surveillance algorithms, clearer warnings to users about volatile assets.",
      "shift_in_investor_education_and_awareness": "New educational campaigns by regulators (SEC's 'Investor.gov' alerts), media literacy efforts focused on financial misinformation, and the rise of watchdog groups and analysts specializing in debunking promotions.",
      "legal_precedents_set": "Outcomes of the key trials: convictions, sentences, disgorgement orders, restitution amounts. Note any novel legal arguments about jurisdiction over internet-based schemes or the classification of new asset types.",
      "lasting_impact_on_market_psychology_and_trust": "The enduring effect on how a generation of investors views certain opportunities. E.g., 'Increased skepticism towards 'community-driven' investment recommendations,' 'Long-term stigma attached to the specific altcoin sector, slowing legitimate project development,' or 'Paradoxically, a reinforced belief among some that such schemes are inevitable and the goal is to 'get in early' on the next one.'",
      "academic_and_policy_analysis": "Key studies, books, or white papers published that use this case as a central example for understanding market manipulation in the digital age."
    },
    "summary_analysis": {
      "key_innovation_or_twist": "What made this scheme notable or particularly effective for its time? E.g., 'One of the first to fully leverage TikTok's short-form video for rapid hype generation among Gen Z investors.'",
      "primary_systemic_failures_exposed": "The top 2-3 institutional, regulatory, or technological weaknesses that the scheme successfully exploited.",
      "effectiveness_of_response_and_recovery": "A critique: How effective were the rescue, legal, and reform efforts? Were victims made reasonably whole? Was the root cause addressed, or did manipulation simply migrate to a new venue?",
      "broader_societal_implications": "What does this case reveal about broader themes like inequality, the democratization of finance, the power of online communities, and the challenge of governing decentralized systems?",
      "analogy_to_historical_precedents": "Comparison to past pump-and-dump eras (e.g., 1920s bucket shops, 1990s boiler rooms). What was timeless about the fraud, and what was uniquely modern?"
    }
  }
}
"""