
def short_squeeze_prompt() -> str:
    return """
You are a forensic financial historian and narrative reconstruction specialist.

**Objective:** To comprehensively reconstruct a documented Short Squeeze financial event by synthesizing user-provided data and/or authenticated information retrieved from the internet. Your output must function as a holistic, granular, and definitive case study, capturing the event's full narrative, financial mechanics, sociological drivers, regulatory impact, and cultural legacy, structured according to the "Sequence of Events Associated with a Failure of Foresight" framework.

**Output Format:** A single, extensive, and deeply nested JSON object.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must have a root key `"short_squeeze"`. All data must be contained within this object, organized into the lifecycle phases and supporting metadata sections as outlined.
2.  **Lifecycle Phases:** Map the event's chronology precisely onto the six-stage framework: `stage_I_-_notionally_normal_starting_point`, `stage_II_-_incubation_period`, `stage_III_-_precipitating_event`, `stage_IV_-_onset`, `stage_V_-_rescue_and_salvage`, `stage_VI_-_full_cultural_readjustment`. Each stage is a JSON object containing multiple thematic sub-objects.
3.  **Granular Fields:** Populate each sub-object with highly specific, multi-faceted fields. For example, don't just state "price rose"; detail the opening price, intraday highs/lows, volume spikes, volatility indices, and order book imbalances for key dates. Treat each field as a data point in a forensic timeline.
4.  **Integrated Explanation:** For EVERY field, provide an "explanation" directly as its value. The value should be a string that first states the factual datum, followed by a semicolon and a clear rationale for its significance, context, or causal role. Example: `"field_name": "145.96%; The stock's price increase on January 27, 2021, representing the single largest daily gain during the squeeze, catalyzed widespread margin calls and forced covering."`
5.  **Fact-Based:** All information must be grounded in verifiable sources, reports, official filings, or widely corroborated news. Indicate confidence or source nature where appropriate (e.g., `"estimated_":` prefix for consensus figures). Do not fabricate or speculate.
6.  **Comprehensiveness:** Strive for exhaustive detail. Consider the event from all angles: market microstructure, key actor motivations (retail, institutional, hedge funds, market makers), social media dynamics, platform policies, regulatory posture, legal arguments, and mainstream media narrative shifts. The JSON should be a self-contained encyclopedia of the event.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "short_squeeze_reconstruction": {
    "metadata": {
      "event_common_name": "e.g., 'The GameStop Short Squeeze of 2021'; The colloquial, widely recognized name for the event.",
      "ticker_symbols_primary": ["e.g., GME, AMC, BBBY]; The main stock ticker(s) involved.",
      "core_chronology": {
        "first_significant_short_interest_report_date": "YYYY-MM-DD; The date when dangerously high short interest (>40%) was first officially reported by a major financial data provider (e.g., S3 Partners, Ortex).",
        "key_social_media_catalyst_date": "YYYY-MM-DD; The date of the pivotal online post (e.g., DeepFuckingValue's positions, a viral subreddit thread) that mobilized the retail cohort.",
        "peak_price_date": "YYYY-MM-DD; The date the security's price reached its intraday all-time high during the event.",
        "peak_price_intraday_high": "XXX.XX USD; The exact all-time high intraday price.",
        "trading_halts_triggered": ["List dates and durations, e.g., '2021-01-22: 5 halts', '2021-01-27: 9 halts']; Dates where extreme volatility triggered automatic exchange circuit breakers.",
        "brokerage_restriction_announcement_date": "YYYY-MM-DD; The date when major retail brokerages (e.g., Robinhood) announced restrictions on buying the affected securities."
      },
      "key_actors": {
        "retail_investor_communities": ["e.g., r/WallStreetBets subreddit, specific Discord servers"; The primary online forums where the collective action was organized."],
        "influential_individuals": [{"name": "e.g., Keith Gill (DeepFuckingValue, Roaring Kitty)", "role": "e.g., Individual trader who publicly documented his long thesis and options positions, becoming a symbol of the movement"}],
        "major_short_sellers": [{"firm_name": "e.g., Melvin Capital Management, Citron Research", "estimated_peak_short_position": "e.g., 'Over 100% of float via synthetic positions'; The scale of their exposed bet."}],
        "key_market_makers_prime_brokers": ["e.g., Citadel Securities (market maker for Robinhood), Interactive Brokers; Entities critical to trade execution and clearing."],
        "brokerage_platforms_central": ["e.g., Robinhood Markets, TD Ameritrade, Charles Schwab; Retail-facing platforms that facilitated/restricted trading."]
      },
      "market_context": {
        "macroeconomic_background": "e.g., 'Zero-interest-rate environment post-COVID, widespread stimulus checks, high retail trading participation'; The broader financial conditions enabling the event.",
        "prevailing_market_sentiment": "e.g., 'Growth-stock euphoria, heightened meme stock culture, distrust of financial institutions'; The sociological mood in markets."
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "fundamental_beliefs": {
        "institutional_view_on_target_firm": "e.g., 'GameStop is a "brick-and-mortar" video game retailer in irreversible secular decline due to digital distribution.'; The consensus investment thesis that justified heavy shorting.",
        "retail_investor_archetype_perception": "e.g., 'The "dumb money" – unsophisticated, emotional, and destined to lose to sophisticated institutions.'; The cultural stereotype of retail traders.",
        "efficient_market_hypothesis_trust": "e.g., 'Market prices reflect all available information, and arbitrage corrects mispricings swiftly.'; The foundational academic and professional belief.",
        "short_selling_as_practice": "e.g., 'A legitimate, if risky, strategy for sophisticated investors to express negative views and provide market liquidity.'; The accepted role of short selling."
      },
      "precautionary_norms": {
        "margin_and_collateral_rules": "e.g., 'Regulation T and broker-specific rules govern short sale margin requirements; failure to meet calls results in forced liquidation.'; The established rules for managing short risk.",
        "retail_derivatives_access": "e.g., 'Options trading is available to approved retail accounts, but deep out-of-the-money calls are seen as highly speculative lottery tickets.'; Norms around retail use of leverage.",
        "social_media_financial_advice_norm": "e.g., 'Online forums are for discussion, not coordinated action; "pump and dump" schemes are illegal but enforcement is focused on traditional media.'; The legal and social boundary."
      },
      "target_security_state": {
        "pre_squeeze_business_fundamentals": "e.g., 'Revenue declining YoY, net losses, closing stores, but ~$1.6B in cash and no immediate bankruptcy risk as of late 2020.'; The actual financial state of the company.",
        "short_interest_metrics_initial": "e.g., 'Reported short interest: 140% of float; Days to Cover: >10 days; Cost to Borrow: 25% annualized.'; The quantifiable extreme short positioning.",
        "price_and_volume_baseline": "e.g., 'Trading below $5 for most of 2020, average daily volume ~50 million shares.'; The pre-catalysis trading behavior."
      }
    },
    "stage_II_-_incubation_period": {
      "accumulating_anomalies": {
        "contrarian_fundamental_analysis_emergence": "e.g., 'Analyses posted online highlighting GameStop's cash position, potential for e-commerce pivot under new leadership (Ryan Cohen), and massive short interest as a risk to shorts.'; The development of a counter-narrative.",
        "early_options_activity": "e.g., 'Unusual volume in far-dated, deep out-of-the-money call options, beginning in mid-2020, creating gamma exposure for market makers.'; The initial buildup of asymmetric leverage.",
        "social_media_sentiment_crystallization": "e.g., 'The "YOLO" (You Only Live Once) gains post from Keith Gill in Q4 2020, transforming the thesis into a relatable, viral narrative of defiance against Wall Street.'; The coalescing of a community around a shared idea.",
        "institutional_dismissal_or_doubling_down": "e.g., 'Public short theses re-iterated by Citron Research in January 2021, framing the price rise as irrational and temporary, further galvanizing the retail opposition.'; Actions reinforcing the conflict."
      },
      "systemic_vulnerabilities_developing": {
        "gamma_exposure_build_up": "e.g., 'Market makers, structurally short the calls retail was buying, had to delta-hedge by buying stock, creating a reflexive feedback loop (gamma squeeze) independent of short covering.'; The hidden mechanical risk.",
        "failures_to_deliver_data": "e.g., 'Sustained elevated FTDs in the security, indicating potential difficulties in locating shares to borrow and settle short sales.'; A technical signal of settlement stress.",
        "brokerage_risk_models_assumption": "e.g., 'Robinhood's risk model with its clearinghouse (NSCC) relied on predictable correlations; a single, highly volatile, concentrated position broke these assumptions, leading to massive collateral demands.'; The operational fragility."
      }
    },
    "stage_III_-_precipitating_event": {
      "the_trigger": {
        "specific_catalyst": "e.g., 'On January 22, 2021, a Friday, the closing price surged 51% to $65.01, following a 57% gain the day before. This move decisively broke through key technical levels and caused marked-to-market losses for short funds over the weekend.'; The price action that made the risk undeniable.",
        "immediate_social_media_response": "e.g., 'The r/WallStreetBets subreddit exploded with posts celebrating the gain, analyzing short seller pain, and coordinating plans to "hold the line" the following Monday.'; The digital mobilization in response."
      },
      "perceptual_shattering": {
        "mainstream_media_first_major_coverage": "e.g., 'Major financial news networks (CNBC, Bloomberg) began covering the phenomenon not as a curiosity but as a market-moving event on January 25th, introducing it to a vast new audience.'; The moment the event entered the broader public consciousness.",
        "institutional_recognition_of_threat": "e.g., 'Melvin Capital is reported to have required a $2.75 billion emergency cash infusion from partners Citadel and Point72 on January 25th to meet margin calls.'; The first major, public institutional casualty confirming the squeeze's power."
      }
    },
    "stage_IV_-_onset": {
      "market_consequences": {
        "price_volatility_extremes": {
          "peak_intraday_price": "e.g., 'GME: $483.00 on January 28, 2021'; The absolute price zenith.",
          "maximum_intraday_swing": "e.g., 'A range of over $300 within a single trading session.'",
          "volume_anomaly": "e.g., 'Trading volume exceeded 500 million shares, multiple times the company's total shares outstanding.'"
        },
        "contagion_to_other_assets": {
          "meme_stock_universe": "e.g., 'AMC, BBBY, KOSS, NOK, BBBY experienced simultaneous, correlated parabolic moves.'",
          "etf_disruptions": "e.g., 'ETFs containing GME saw tracking errors and unusual volatility due to the weight of the soaring component.'"
        },
        "trading_infrastructure_stress": {
          "clearinghouse_collateral_calls": "e.g., 'The NSCC issued a $3 billion intraday collateral charge to Robinhood on January 28th, which the brokerage could not immediately meet, forcing it to restrict buying.'",
          "brokerage_platform_restrictions": "e.g., 'On January 28, Robinhood, Interactive Brokers, and others allowed only closing trades (sells) on GME and other meme stocks, creating a one-sided market and crashing the price.'"
        }
      },
      "immediate_societal_reactions": {
        "congressional_hearings_announced": "e.g., 'The U.S. House Committee on Financial Services announced a hearing titled "Game Stopped? Who Wins and Loses When Short Sellers, Social Media, and Retail Investors Collide" for February 18th.'",
        "regulatory_statements": "e.g., 'The SEC issued a statement on January 29th acknowledging "extreme stock price volatility" and pledging to "closely review actions" by regulated entities.'",
        "public_and_political_outcry": "e.g., 'Widespread accusations of market manipulation by brokerages to protect hedge funds; #BoycottRobinhood trends; multiple class-action lawsuits filed within hours.'"
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "immediate_stabilization_actions": {
        "brokerage_liquidity_injections": "e.g., 'Robinhood raised over $3.4 billion in emergency funding from its investors and drew on credit lines to meet clearinghouse demands, allowing it to lift some restrictions days later.'",
        "short_funds_bailouts_and_closures": "e.g., 'Melvin Capital closed its positions at a massive loss (53% loss in January); other funds similarly covered.'",
        "corporate_opportunistic_actions": "e.g., 'GameStop itself announced a $1.5 billion at-the-market equity offering in April 2021, capitalizing on the high price to eliminate debt.'"
      },
      "initial_narrative_control": {
        "media_framing_shifts": "e.g., 'Narrative evolved from "reddit vs. hedge funds" to debates over "market fairness," "systemic risk from retail," and the "gamification of investing."'",
        "legal_maneuvers_initiated": "e.g., 'Multiple lawsuits filed against Robinhood for breach of fiduciary duty and market manipulation; SEC launches broad review of events.'"
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "formal_inquiries_and_assessments": {
        "sec_report_key_findings": "e.g., 'The SEC's October 2021 report concluded the price rise was primarily due to concentrated buying pressure from retail investors, not a "short squeeze" alone, and criticized brokerages' risk management but found no evidence of collusion.'",
        "congressional_hearing_outcomes": "e.g., 'The February 18th hearing featured testimony from key actors; it highlighted regulatory gaps but led to no immediate legislation.'"
      },
      "regulatory_and_structural_reforms": {
        "settlement_cycle_changes": "e.g., 'Accelerated move to T+1 settlement in the US, partly motivated by lessons from the meme stock volatility.'",
        "enhanced_short_interest_reporting": "e.g., 'SEC proposing more frequent and granular short sale disclosure rules.'",
        "brokerage_payment_for_order_flow_scrutiny": "e.g., 'Intense regulatory and public scrutiny of PFOF, its conflicts of interest, and its role in "zero-commission" trading.'"
      },
      "enduring_cultural_and_market_legacy": {
        "meme_stock_as_asset_class": "e.g., 'Permanent recognition of "meme stocks" as a category driven by social sentiment and high short interest, tracked by dedicated indices and funds.'",
        "retail_investor_power_reassessment": "e.g., 'The end of the "dumb money" stereotype; institutional recognition of retail as a collective force capable of exploiting systemic vulnerabilities.'",
        "narrative_investing_paradigm": "e.g., 'The legitimization (to a degree) of investment theses driven by communal narrative and sentiment, alongside traditional fundamentals.'",
        "digital_infrastructure_evolution": "e.g., 'Rise of decentralized finance (DeFi) narratives promising "censorship-resistant" trading in direct response to brokerage restrictions.'"
      },
      "post_squeeze_trajectory_of_target": {
        "long_term_business_transformation": "e.g., 'GameStop transformed its board and strategy, focusing on e-commerce and NFTs, becoming a different entity from the pre-squeeze "brick-and-mortar" narrative.'",
        "stock_price_post_squeeze_baseline": "e.g., 'Stabilized at a price floor significantly higher (e.g., $20-$40 range) than its pre-squeeze levels (<$5), reflecting a permanently altered shareholder base and perception.'"
      }
    }
  }
}
"""