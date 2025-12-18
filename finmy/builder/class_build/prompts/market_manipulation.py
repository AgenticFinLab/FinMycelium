
def market_manipulation_prompt() -> str:
    return """
You are a financial forensics historian and data reconstruction specialist.

**Objective:** To reconstruct a comprehensive, multi-dimensional, and forensically detailed account of a specific market manipulation event. Your output must function as a definitive, data-rich historical record, capturing the event's complete lifecycle, mechanics, actors, impacts, and the subsequent societal and regulatory evolution.

**Output Format:** A single, extensive, and meticulously populated JSON object. Do not add any commentary outside the JSON.

**Instructions for JSON Construction:**
1.  **Base Structure:** Use the exact top-level keys and nested structure provided below. Do not omit any sections or fields. Populate every field. If specific information is unavailable from your source material, use `"Information not specified in source"` as the value, but strive for completeness.
2.  **Lifecycle Phases:** The event must be analyzed through the six-stage sociological framework of a "Failure of Foresight" (provided). Each stage (`stage_I` to `stage_VI`) must be populated with granular data that maps events, conditions, and perceptions to that specific phase.
3.  **Granular Fields:** Every field must be filled with specific, concrete details. Avoid summaries. Use dates, names, monetary figures, specific regulatory rule numbers, exact quotes from communications (if available), detailed descriptions of tactics, and precise sequences of actions.
4.  **Integrated Explanation:** For each field, the *value* itself should contain both the factual data *and* its explanatory context or significance. Treat the value as a self-contained, explanatory data point. Do not create separate "explanation" sub-fields.
5.  **Fact-Based:** All information must be grounded in the provided source materials or verifiable public records. Do not fabricate or infer details without basis. The JSON is a reconstruction of reality, not a speculative exercise.
6.  **Comprehensiveness:** The final JSON must be exhaustive. It should enable a reader to understand the technical execution of the manipulation, the human and systemic failures that allowed it, the immediate chaos of its collapse, the legal aftermath, and the lasting changes to market structure and culture.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "market_manipulation_reconstruction": {
    "metadata": {
      "scheme_common_name": "e.g., 'The 2010 Flash Crash Spoofing by Navinder Sarao'. The colloquial name used in media and industry discourse to identify the event.",
      "official_legal_case_name": "e.g., 'CFTC v. Navinder Singh Sarao, et al.'. The formal title of the primary regulatory or criminal case filed against the perpetrators.",
      "primary_perpetrator_name": "e.g., 'Navinder Singh Sarao'. The individual identified as the central actor in designing and/or executing the manipulative strategy.",
      "perpetrator_background": "e.g., 'A UK-based solo trader operating from his home in Hounslow, with no formal affiliation to a major bank, previously worked at minor trading firms. Largely an outsider to the traditional banking establishment.' Context on who the perpetrator was, their professional history, and their position within the financial ecosystem.",
      "key_associated_entities": ["e.g., 'Nav Sarao Futures Limited PLC', 'ICAP PLC (as broker)'"]. The legal entities, shell companies, brokerages, or funds directly used as vehicles to conduct the manipulative trades.",
      "core_manipulative_technique": "e.g., 'Spoofing and Layering in the E-mini S&P 500 futures market'. A precise label for the specific illegal method employed, which is a subset of the broad 'market manipulation' category.",
      "operational_timeframe": {
        "suspected_inception_date": "e.g., '2009-06-08'. The earliest documented date (YYYY-MM-DD, or YYYY-MM if day unknown) the specific manipulative pattern began.",
        "public_collapse_date": "e.g., '2015-04-21'. The date the scheme was publicly exposed via regulatory charges or major news break.",
        "duration_active": "e.g., '5 years, 10 months'. The calculated span from inception to exposure/collapse.",
        "period_of_most_intense_activity": "e.g., '2012-2014'. The timeframe where the activity was most frequent and/or of largest scale."
      },
      "market_instrument_targeted": "e.g., 'CME E-mini S&P 500 Futures (Contract Symbol: ES)'. The exact financial product (stock, bond, future, option, etc.) whose price or liquidity was the target of manipulation.",
      "trading_venue": "e.g., 'Chicago Mercantile Exchange (CME) Globex electronic platform'. The specific exchange or trading platform where the activity occurred.",
      "estimated_global_scale": {
        "currency": "e.g., 'USD'.",
        "direct_profit_to_perpetrator": "e.g., '$70 million'. The estimated financial gain illicitly achieved by the perpetrator(s).",
        "market_dislocation_impact": "e.g., 'Contributed to a ~9% intraday drop (approx. $1 trillion in market cap evaporation) in the US equity market on May 6, 2010'. A description of the direct market impact, including price moves, liquidity disappearance, or volatility spikes.",
        "victim_class": "e.g., 'Other market participants trading against the spoofed orders, including high-frequency traders and institutional algorithms; indirect harm to all investors during the Flash Crash.' The types of entities that suffered direct financial loss or indirect harm.",
        "geographic_reach_of_impact": ["e.g., 'United States', 'Global equity and futures markets'"]. The jurisdictions and markets that felt measurable effects."
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "prevailing_market_structure": "e.g., 'Post-2008, markets were increasingly electronic and fragmented, with high-frequency trading (HFT) providing the majority of liquidity. The CME Globex platform operated with a central limit order book and time-priority matching.' A detailed description of the technological, regulatory, and cultural norms of the targeted market before the manipulation began.",
      "accepted_beliefs_about_orders": "e.g., 'Market participants and regulators largely believed that large orders in the limit order book represented genuine trading intent and were a reliable signal of supply/demand. The concept of 'good faith' in order placement was an implicit cultural norm.' The shared assumptions about how market actors *should* and *would* behave.",
      "explicit_regulatory_framework": "e.g., 'The Commodity Exchange Act prohibited fraud and manipulation, but 'spoofing' was not yet explicitly defined in statute (pre-Dodd-Frank). Surveillance focused on traditional collusion and insider trading, not on sub-second pattern analysis of single actors.' The laws, rules, and surveillance capabilities in place at the time.",
      "technological_capabilities_of_perpetrator": "e.g., 'Access to direct market data feeds, custom-built trading software allowing rapid order entry/cancellation, and a high-speed internet connection. Technology was commercially available but used with malicious intent.' The tools that made the manipulation possible.",
      "perceived_motivational_landscape": "e.g., 'The dominant narrative was that HFT firms competed on speed and information to provide liquidity. The idea of a 'lone wolf' trader intentionally injecting false signals to trigger cascades was not a mainstream concern.' What the financial community believed were the primary drivers of market activity and misbehavior."
    },
    "stage_II_-_incubation_period": {
      "early_anomalies_ignored": ["e.g., 'Unusual, repetitive patterns of large order placements and immediate cancellations in the ES order book observed by some exchange staff but flagged as 'glitches' or 'aggressive HFT'.", "Market maker complaints about 'phantom liquidity' that disappeared when they tried to trade.' Specific, documented events or patterns that were noticed but rationalized away or not escalated."],
      "regulatory_or_surveillance_gaps_exploited": "e.g., 'CME's real-time surveillance systems were not designed to automatically detect the specific multi-layered, rapid-fire spoofing pattern across multiple price levels. Alerts were based on simpler parameters like total message volume.' The precise weaknesses in systems or processes that the manipulator learned to exploit consistently.",
      "perpetrator_learning_and_refinement": "e.g., 'Sarao manually tested his strategy starting in 2009, observing market reactions. By 2010, he had automated the 'layering' algorithm to place and cancel up to hundreds of orders per second, optimizing the size and price levels to appear credible.' How the manipulator evolved their tactics over time, becoming more effective and brazen.",
      "enabling_factors": {
        "broker_complicity_or_negligence": "e.g., 'His brokers, including a trader at ICAP, were aware of his extremely high cancellation rates (over 99% on some days) and his dominant presence in the market but failed to conduct adequate due diligence or report suspicious activity.'",
        "technological_arms_race": "e.g., 'The broader market's obsession with microsecond speed created a 'noise' backdrop in which his manipulative messages could hide. Regulatory tech lagged behind trading tech.'",
        "cultural_normalization_of_aggressive_tactics": "e.g., 'The boundary between aggressive legitimate trading (e.g., 'fleeting orders') and illegal spoofing was blurred, creating ambiguity that perpetrators could hide behind.'"
      },
      "internal_rationalization_by_perpetrator": "e.g., 'Sarao reportedly claimed he was just 'providing liquidity' and that his tactics were common practice, a form of 'fighting fire with fire' against other HFTs.' The perpetrator's own beliefs or justifications for their actions during this period."
    },
    "stage_III_-_precipitating_event": {
      "trigger_event_description": "e.g., 'The joint CFTC-SEC forensic investigation into the May 6, 2010 Flash Crash, which began immediately after the event, eventually traced a significant portion of the selling pressure that day to Sarao's spoofing activity.' The specific investigation, whistleblower tip, market crash, internal audit, or journalistic expose that forced the latent risk into full view.",
      "key_evidence_uncovered": "e.g., 'Analysis of audit trail data (ITCH/OUCH feeds) from CME revealed that a single trader account (Sarao's) was responsible for over 20% of the total sell-side order messages in the ES market during the crash, with an order-to-trade ratio exceeding 200:1.' The concrete, damning piece(s) of evidence that directly linked the activity to manipulation.",
      "moment_of_recognition_by_authorities": "e.g., 'In early 2015, CFTC data scientists isolated the unique 'layering' pattern algorithmically and matched it to Sarao's account, transforming a years-long background investigation into a concrete enforcement action.' When and how regulators internally concluded they had identified deliberate manipulation.",
      "first_public_action": "e.g., 'The simultaneous freezing of Sarao's trading accounts by the CME and the filing of a civil complaint by the CFTC on April 21, 2015, followed swiftly by his arrest in the UK on a US extradition request.' The first regulatory order, trading halt, or public announcement that exposed the scheme."
    },
    "stage_IV_-_onset": {
      "immediate_market_reaction": "e.g., 'Limited direct market impact on the announcement date, as the activity had already ceased. However, the news reignited public and political debate about HFT and market stability.' How the market and related securities reacted upon the public revelation.",
      "legal_and_regulatory_onslaught": ["e.g., 'CFTC civil complaint filed April 21, 2015.', 'US Department of Justice criminal indictment (wire fraud, commodities fraud, spoofing) unsealed April 22, 2015.', 'UK Financial Conduct Authority (FCA) parallel action.', 'ICE Futures U.S. (NYSE) also brought disciplinary action.' A chronological list of the initial legal and regulatory actions taken within days or weeks."],
      "perpetrator_response": "e.g., 'Sarao was arrested at his home in the UK. He initially fought extradition, then agreed to be extradited to the US in 2016, where he pleaded guilty to one count of wire fraud and one count of spoofing in November 2016.' The perpetrator's immediate actions (fleeing, confessing, fighting charges, etc.).",
      "victim_reaction_and_claims": "e.g., 'Other traders and firms who suffered losses during the Flash Crash began exploring potential civil claims against Sarao. A class-action lawsuit was later filed by investors seeking to recover losses attributed to his manipulation.' The initial responses from those directly harmed.",
      "media_and_public_narrative": "e.g., 'Headlines focused on the 'Hound of Hounslow' as a lone trader who 'crashed the market'. The narrative solidified the Flash Crash as a manipulable event rather than a purely technical glitch.' The dominant themes in initial news coverage and public discourse."
    },
    "stage_V_-_rescue_and_salvage": {
      "asset_seizure_and_recovery": "e.g., 'US and UK authorities immediately seized approximately $70 million from Sarao's trading and bank accounts. These funds were held for potential restitution to victims.' Actions taken to secure illicit gains and preserve assets for victims.",
      "emergency_regulatory_patches": "e.g., 'Exchanges like CME and ICE accelerated the implementation of more sophisticated 'spoofing detection' algorithms in their real-time surveillance systems and enhanced their rulebooks on disruptive trading practices.' Temporary or immediate changes to market rules, surveillance, or systems to prevent an identical repeat.",
      "plea_negotiations_and_settlements": "e.g., 'Sarao's 2016 plea agreement involved cooperation with authorities, forfeiture of nearly all his trading profits, and a sentencing recommendation well below the maximum. He was ultimately sentenced to time served (1 year in UK prison) and home detention.' The process of resolving the primary legal cases against the main perpetrator(s).",
      "victim_compensation_mechanisms_established": "e.g., 'The CFTC and DOJ established a process to use the forfeited funds for victim restitution, though identifying and quantifying losses for individual traders harmed by spoofing proved complex.' How authorities attempted to make victims whole."
    },
    "stage_VI_-_full_cultural_readjustment": {
      "landmark_legal_precedents": "e.g., 'United States v. Navinder Singh Sarao became one of the first major criminal convictions and sentencings under the explicit 'spoofing' prohibition (CEA Section 4c(a)(5)(C)) added by Dodd-Frank. It established that spoofing could be prosecuted as a criminal wire fraud.' The lasting legal principles established by the case.",
      "regulatory_rule_changes": "e.g., 'Regulators globally (CFTC, SEC, FCA, etc.) adopted more prescriptive rules against disruptive trading, including explicit spoofing bans, mandatory minimum order-resting times for some orders, and requirements for firms to implement robust surveillance of their own traders.' New laws, regulations, or exchange rules enacted in direct response.",
      "surveillance_technology_evolution": "e.g., 'The development and adoption of AI/ML-based market surveillance tools by exchanges and regulators designed to detect complex cross-product spoofing and layering patterns in real-time, moving beyond simple message volume thresholds.'",
      "industry_best_practice_shifts": "e.g., 'Broker-dealers implemented stricter pre-trade risk controls and post-trade surveillance for all clients, particularly high-message-rate traders. Compliance departments grew in size and technical sophistication.' Changes in how financial firms internally policed activity.",
      "academic_and_theoretical_impact": "e.g., 'The event became a seminal case study in finance and law schools on market microstructure fragility, the ethics of algorithmic trading, and the challenges of regulating financial technology.' How the event influenced scholarly research and economic theory.",
      "persisting_vulnerabilities_acknowledged": "e.g., 'Post-mortem analyses acknowledged that while single-actor spoofing in a centralized futures market is now harder, manipulation risks have migrated to decentralized markets (crypto), cross-asset strategies, and more sophisticated 'pooled' tactics by multiple actors.' An honest assessment of what problems the event did *not* solve.",
      "public_and_political_legacy": "e.g., 'The Sarao case permanently linked the 2010 Flash Crash to intentional manipulation in the public consciousness, fueling lasting distrust in electronic markets and providing political impetus for continued regulatory scrutiny of HFT.' The enduring narrative and its effects on policy debates."
    },
    "forensic_appendices": {
      "detailed_mechanics_of_the_scheme": "e.g., 'Step 1: Place a large sell order (e.g., 200 lots) at a price just above the current best ask to create an illusion of impending selling pressure. Step 2: Rapidly place a series of smaller buy orders (the 'layers') at incrementally lower prices down the order book... Step 3: Once the market price moved down due to the false signal, cancel the large initial sell order and execute buys at the now-lowered price, profiting from the artificial move.' A minute-by-minute, order-by-order technical description of the manipulative algorithm or process.",
      "technology_stack_used": {
        "software": "e.g., 'Custom C++ application interfacing with the CME iLink API, with a graphical user interface for manual override. The algorithm was triggered based on market depth and momentum indicators.'",
        "hardware": "e.g., 'Colocated servers at the CME data center in Aurora, Illinois, to minimize latency.'",
        "connectivity": "e.g., 'Dedicated high-speed fiber line.'"
      },
      "key_communications_evidence": ["e.g., 'Chat log from 2012: Perpetrator to broker: '...my stuff shouldn't be in the mainstream...if people knew how I did it they would sh** themselves.'", "Email to exchange: 'I am just a small trader providing liquidity...'." Excerpts from emails, chats, recorded calls, or internal documents that reveal intent or knowledge."],
      "chronology_of_significant_trading_days": {
        "YYYY-MM-DD": "e.g., '2010-05-06 (Flash Crash Day): Sarao's algorithm was active and contributed to the downward cascade. His profit for the day was approximately $900,000.'"
      }
    }
  }
}
    """