
def liquidity_spiral_prompt() -> str:
    return """
You are a Financial Historian and Systemic Risk Analyst specializing in the forensic reconstruction of market crises.

**Objective:** To deconstruct a specific "Liquidity Spiral" event in exhaustive, granular detail. Your task is to synthesize information from provided documents or credible internet sources to build a comprehensive, fact-based narrative that captures the event's genesis, mechanics, escalation, aftermath, and lasting impact, structured according to a sociological failure model.

**Output Format:** A single, extensive JSON object.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must have a root key `"liquidity_spiral"`. The primary substructures are `"metadata"` and the six lifecycle stages (`stage_I` through `stage_VI`).
2.  **Lifecycle Phases:** Populate each stage according to the "Sequence of Events Associated with a Failure of Foresight" model. Treat each stage as a container for the conditions, actors, actions, and misperceptions characteristic of that phase.
3.  **Granular Fields:** Every field must be populated with specific, detailed data. Avoid summaries; instead, list concrete facts, figures, names, dates, and direct quotes from regulations or market participants. Use nested objects and arrays to capture complexity (e.g., `key_actors: { regulators: [], leveraged_entities: [], market_makers: [] }`).
4.  **Integrated Explanation:** For **every** field, include an `"explanation"` key **within the same nested object**. This explanation must directly justify why this specific data point is relevant to the field and the stage. Do not create a separate "explanations" section. The value should be an integrated description.
5.  **Fact-Based:** All data must be sourced from the provided context or verifiable public records. If precise data is unavailable, estimate with qualifiers ("estimated", "approximately") and state the basis for the estimate in the explanation. Do not invent facts.
6.  **Comprehensiveness:** The JSON must be exhaustive. Consider all dimensions: macroeconomic preconditions, regulatory frameworks, market microstructure (e.g., margin rules, derivative linkages), key institution balance sheets, behavioral biases, narrative shifts, technological failures, official response timelines, legal outcomes, and long-term changes to theory and practice.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "liquidity_spiral_reconstruction": {
    "metadata": {
      "event_common_name": {
        "value": "[e.g., 'The Quant Meltdown of August 2007', 'The UK Gilts Crisis of September 2022 (LDI Spiral)']",
        "explanation": "The colloquial or widely used name in financial media and academia for this specific liquidity spiral instance."
      },
      "academic_case_references": {
        "value": ["List key papers, e.g., 'Brunnermeier & Pedersen, 2009, Market Liquidity and Funding Liquidity'", "Barth & Kahn, 2023, 'The LDI Crisis: A Primer'"],
        "explanation": "Scholarly articles or seminal texts that formally analyze this event, establishing its place in financial literature."
      },
      "core_mechanical_trigger": {
        "value": "[e.g., 'Forced deleveraging due to margin calls on highly correlated quantitative equity market-neutral strategies', 'Collateral calls on liability-driven investment (LDI) derivatives following a rapid rise in UK government bond yields']",
        "explanation": "The precise financial mechanism that initiated the first round of forced selling, distinguishing it from a fundamental price decline."
      },
      "primary_asset_class_and_instruments": {
        "value": {
          "asset_class": "[e.g., 'Equities', 'Sovereign Bonds (Gilts)', 'Corporate Bonds', 'Mortgage-Backed Securities']",
          "specific_instruments": ["e.g., 'S&P 500 futures', '30-year UK Treasury futures', 'CDX investment-grade index']",
          "related_derivatives": ["e.g., 'Interest rate swaps', 'Total return swaps', 'Volatility futures (VIX)'"]
        },
        "explanation": "Identifies the financial instruments at the epicenter of the spiral. The 'related_derivatives' field is crucial for understanding leverage and cross-market contagion."
      },
      "key_leveraged_entities": {
        "value": {
          "entity_types_involved": ["e.g., 'Quantitative Hedge Funds', 'Liability-Driven Investment (LDI) Funds', 'Risk Parity Funds', 'Leveraged ETFs', 'Prime Brokerage Desks'"],
          "representative_firms": ["e.g., 'Renaissance Technologies, AQR, Barclays' LDI desk'"],
          "typical_leverage_ratio_pre_event": "[e.g., '8:1 average for market-neutral quants', 'LDI funds with >100x economic exposure via derivatives']",
          "funding_source": "[e.g., 'Prime broker margin loans', 'Repo market', 'Collateralized swaps']"
        },
        "explanation": "Details the types of institutions whose leveraged positions were the fuel for the spiral, including their scale of leverage and fragile funding structures."
      },
      "operational_timeframe": {
        "value": {
          "macro_stress_onset": "YYYY-MM-DD. The date when underlying market stress (e.g., volatility spike, rate rise) began.",
          "spiral_acceleration_start": "YYYY-MM-DD. The date when the first wave of forced, concentrated selling was observed.",
          "peak_liquidity_dislocation": "YYYY-MM-DD. The date(s) with the widest bid-ask spreads, highest volatility, and/or failed auctions.",
          "official_intervention_start": "YYYY-MM-DD. The date of first significant central bank or regulator statement/action.",
          "market_normalization_start": "YYYY-MM-DD. The date when liquidity metrics returned to near pre-spiral levels."
        },
        "explanation": "A timeline of critical phases, not just inception/collapse. 'Market normalization' may differ from the end of official support."
      },
      "geographic_and_market_epicenter": {
        "value": {
          "primary_market": "[e.g., 'US Equity Futures Market', 'UK Gilt Market']",
          "primary_exchanges_venues": ["e.g., 'CME Globex', 'NYSE Arca', 'Broker-dealer OTC desks'"],
          "contagion_paths": ["e.g., 'US equities -> European equities -> Asian equities', 'Long-dated gilts -> UK corporate bonds -> Sterling credit derivatives'"]
        },
        "explanation": "Defines the ground zero of the crisis and the channels through which illiquidity spread to other asset classes and regions."
      },
      "estimated_magnitude": {
        "value": {
          "peak_asset_price_decline": "[e.g., 'Target asset class fell X% in Y days during the spiral phase']",
          "liquidity_cost_metric": "[e.g., 'Bid-ask spreads widened by a factor of 10', 'Market depth on top 10 books fell by 75%']",
          "value_of_forced_sales_estimated": "[e.g., 'Estimated $X billion in forced liquidations in the first week']",
          "related_counterparty_losses": "[e.g., 'Prime brokers reported $Y billion in trading losses', 'Pension fund deficit increased by £Z billion']"
        },
        "explanation": "Quantifies the market impact in terms of price, liquidity, volume, and realized losses to key participants."
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "macroeconomic_backdrop": {
        "value": {
          "growth_inflation_regime": "[e.g., 'The Great Moderation', 'Post-GFC low-inflation, low-rate environment']",
          "central_bank_policy_stance": "[e.g., 'Fed funds target rate: X%', 'Bank of England quantitative easing program ongoing']",
          "prevailing_market_narrative": "[e.g., 'Secular stagnation', 'There is no alternative (TINA) to equities']"
        },
        "explanation": "Describes the broad economic conditions and narratives that created a perception of stability and encouraged risk-taking."
      },
      "regulatory_and_supervisory_framework": {
        "value": {
          "relevant_capital_liquidity_rules": ["e.g., 'Basel II/III framework', 'SEC net capital rule 15c3-1', 'Volcker Rule exemptions']"],
          "perceived_regulatory_gaps": ["e.g., 'Limited oversight of hedge fund leverage', 'LDI derivative exposure not captured by bank stress tests']"],
          "official_sector_risk_assessments": ["Quotes from central bank financial stability reports in the preceding year, highlighting or downplaying relevant risks."]
        },
        "explanation": "Captures the formal rules and informal supervisory focus that defined the 'rules of the game' and shaped hazard perception."
      },
      "market_structure_and_technology": {
        "value": {
          "dominant_trading_paradigm": "[e.g., 'Rise of electronic market-making and high-frequency trading', 'Dominance of OTC derivatives for institutional hedging']",
          "risk_management_models": ["e.g., 'Widespread use of Value-at-Risk (VaR) with short lookback periods', 'Assumption of constant liquidity in stress scenarios']"],
          "data_and_monitoring_limitations": "[e.g., 'Lack of real-time, consolidated position data across hedge funds and prime brokers']"
        },
        "explanation": "Highlights the technological and methodological norms that influenced how actors measured and managed risk, often embedding latent vulnerabilities."
      },
      "cultural_beliefs_and_incentives": {
        "value": {
          "investor_psychology": "[e.g., 'Reach for yield', 'Faith in central bank put', 'Momentum-driven flows']",
          "compensation_structures": "[e.g., 'Hedge fund manager bonuses based on annual returns, not long-term risk', 'Asset manager fees based on AUM, encouraging leverage']"],
          "intellectual_orthodoxy": "[e.g., 'Efficient Market Hypothesis dominance', 'Belief in the diversification benefits of risk parity']"
        },
        "explanation": "Describes the soft, behavioral factors: the shared beliefs, reward systems, and academic theories that justified prevailing strategies."
      }
    },
    "stage_II_-_incubation_period": {
      "accumulation_of_anomalies": {
        "value": {
          "gradual_build_up_of_leverage": "[Detail the slow increase in aggregate leverage in the system, e.g., 'Hedge fund gross leverage ratio rose from 5x to 8x over 18 months', 'Pension fund allocations to LDI strategies grew from £400bn to £1.5tn in a decade']",
          "concentration_and_correlation": "[e.g., 'Crowding into the same 'value' factor trade', 'Over 80% of UK defined benefit pensions using similar LDI hedging structures']",
          "deterioration_of_underlying_liquidity": "[e.g., 'Declining average dealer inventory', 'Rising frequency of 'flash' volatility spikes']"
        },
        "explanation": "Specific metrics and trends that indicated rising systemic fragility but were rationalized, ignored, or not collectively understood."
      },
      "early_warning_signals_ignored": {
        "value": {
          "isolated_stress_events": ["e.g., 'The 'Volmageddon' spike in VIX ETN products in Feb 2018', 'Previous, smaller gilt yield spikes in 2020 that tested LDI collateral buffers']"],
          "internal_risk_management_flags": "[Quotes or reports from internal risk officers at involved firms that were overridden, e.g., 'VaR limits breached but temporarily raised']",
          "academic_or_contrarian_warnings": ["Citations of pre-crisis papers or commentators who identified the specific vulnerability, e.g., 'Paper X in 2015 warned of liquidity mismatch in LDI funds'"]"
        },
        "explanation": "Points to specific events or analyses that, in hindsight, clearly signaled danger but were dismissed as anomalies or 'noise'."
      },
      "feedback_loop_preconditions": {
        "value": {
          "margin_and_collateral_practices": "[e.g., 'Pro-cyclical margin models used by CCPs and prime brokers', 'Daily mark-to-market collateral calls on LDI swaps']",
          "redemption_terms": "[e.g., 'Quarterly redemption with notice periods for hedge funds, creating a potential run dynamic']",
          "information_asymmetries": "[e.g., 'Lack of transparency on aggregate hedge fund positioning', 'Pension trustees' limited understanding of derivative leverage']"
        },
        "explanation": "Details the specific institutional rules and practices that were in place and would inevitably amplify an initial shock into a spiral."
      }
    },
    "stage_III_-_precipitating_event": {
      "triggering_shock": {
        "value": {
          "nature_of_shock": "[e.g., 'A sharp, unexpected rise in core inflation print', 'The failure of a major mid-sized bank', 'A sovereign credit rating downgrade']",
          "date_and_initial_market_reaction": "YYYY-MM-DD: [e.g., '10-year yield jumped 35 basis points, its largest one-day move in a decade']",
          "immediate_catalyst_for_first_forced_sales": "[e.g., 'Margin calls issued to leveraged volatility sellers', 'LDI funds received £X billion in collateral calls from swap counterparts']"
        },
        "explanation": "The discrete event that moved the system from a state of latent stress to active crisis, provoking the first mandatory liquidations."
      },
      "breakdown_of_initial_hedges": {
        "value": {
          "expected_diversification_failure": "[e.g., 'Correlations between asset classes moved to 1', 'Government bonds, traditionally a safe haven, sold off alongside equities']",
          "liquidity_of_hedging_instruments": "[e.g., 'Options markets became too expensive or illiquid to re-hedge', 'The futures basis widened dramatically, making rolling hedges costly']"
        },
        "explanation": "Describes how the standard risk mitigation strategies failed precisely when needed, exacerbating the panic."
      },
      "shift_in_market_narrative": {
        "value": {
          "new_dominant_narrative": "[e.g., 'From 'transitory inflation' to 'inflation regime change'', 'From 'central bank support' to 'quantitative tightening (QT) accident'']",
          "key_media_headlines": ["Reproduce impactful headlines from major financial news outlets at the time."],
          "public_statements_from_authorities": ["Initial, often calming, statements from regulators or central banks that may have been ineffective."]
        },
        "explanation": "Captures the rapid change in collective interpretation, moving from complacency to recognition of a new, dangerous reality."
      }
    },
    "stage_IV_-_onset": {
      "mechanics_of_the_spiral_unfolding": {
        "value": {
          "round_1_sales": "[Detail who sold what, and why they were forced to: e.g., 'Fund A liquidated $Bbn in equities to meet a 10% margin hike from Prime Broker C']",
          "price_impact_and_volatility": "[e.g., 'The selling pressure caused a 5% intraday drop, triggering VaR-based stop-losses across the street']",
          "round_2_sales": "[e.g., 'The volatility spike triggered redemptions from retail volatility products, forcing their managers to sell futures']",
          "funding_liquidity_constriction": "[e.g., 'Prime brokers widened financing terms for all clients, reducing available leverage and forcing further deleveraging']"
        },
        "explanation": "A blow-by-blow account of the self-reinforcing cycle: price drop -> margin/redemption call -> forced sale -> further price drop."
      },
      "market_dysfunction_metrics": {
        "value": {
          "liquidity_disappearance": "[e.g., 'Top-of-book depth on key futures contracts fell by over 90%', 'The number of active market makers halved']",
          "dislocation_indicators": "[e.g., 'ETF premiums/discounts to NAV exceeded 5%', 'Cash-futures basis trades became unprofitable, breaking down arbitrage linkages']",
          "failed_auctions_or_trading_halts": ["List specific instances, e.g., 'The 30-year gilt futures market experienced a 'flash' move exceeding 10 standard deviations']"]
        },
        "explanation": "Quantitative and qualitative evidence that the normal price discovery and trading mechanisms broke down."
      },
      "key_institutional_failures_or_distress": {
        "value": {
          "entities_facing_existential_threat": ["Names of specific funds, dealers, or endowments that were at risk of collapse."],
          "counterparty_risk_concerns": "[e.g., 'Rumors swirled about the stability of major prime broker Y', 'Clearinghouse margin calls threatened to drain bank capital']",
          "operational_failures": "[e.g., 'Margin call systems were overwhelmed, leading to delays and uncertainty', 'Client portals crashed, preventing position management']"
        },
        "explanation": "Highlights the points of maximum stress within the financial network, where the spiral risked causing insolvencies."
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "first_responders_and_actions": {
        "value": {
          "central_bank_actions": ["e.g., 'Bank of England announced a temporary and targeted Gilt Market Operation on [Date], committing to buy up to £Zbn per day'"],
          "regulatory_forbearance_or_guidance": ["e.g., 'PRA issued a letter encouraging banks to be flexible with LDI clients on collateral calls']"],
          "private_sector_coordination": ["e.g., 'A consortium of banks provided a bridge loan to a distressed fund to allow orderly wind-down']"]
        },
        "explanation": "The immediate, often ad-hoc, interventions taken by authorities and market participants to halt the spiral and prevent contagion."
      },
      "liquidity_provision_mechanics": {
        "value": {
          "terms_of_facilities": "[e.g., 'The BoE facility accepted a wider range of collateral, including index-linked gilts, and charged a penalty rate']",
          "uptake_and_impact": "[e.g., '£Xbn was drawn in the first 3 days; gilt yields immediately fell by Y basis points']",
          "signaling_effect": "[e.g., 'The mere announcement restored confidence, and much of the facility went unused']"
        },
        "explanation": "Details how the emergency liquidity was provided and the mechanics through which it calmed markets."
      },
      "immediate_post_spiral_landscape": {
        "value": {
          "market_state_after_intervention": "[e.g., 'Volatility remained elevated but orderly trading resumed', 'Liquidity metrics recovered to 50% of pre-crisis levels within a week']",
          "casualties": ["List of funds that were liquidated, merged, or suffered fatal losses."],
          "launch_of_inquiries": ["Announcements of official investigations, e.g., 'The UK Treasury Committee launched an inquiry into LDI on [Date]']"]
        },
        "explanation": "Describes the stabilized but wounded market environment and the initial political and regulatory fallout."
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "official_investigations_and_reports": {
        "value": {
          "key_government_or_regulatory_reports": ["e.g., 'Bank of England Financial Stability Report, December 2022: Special Feature on LDI'", 'SEC Market Structure Advisory Committee findings']"],
          "primary_conclusions_on_causes": ["List the root causes as identified by official bodies, e.g., '1. Inadequate stress testing of leverage...'"],
          "assignation_of_responsibility": "[e.g., 'The report criticized fund managers for poor governance and regulators for supervisory blind spots']"
        },
        "explanation": "Summarizes the formal post-mortem analysis conducted by authorities, which forms the basis for new norms."
      },
      "permanent_changes_to_regulation_and_supervision": {
        "value": {
          "new_rules_or_guidance": ["e.g., 'PRA Supervisory Statement SSX/23 on resilience of LDI funds', 'IOSCO recommendations on margining pro-cyclicality']"],
          "enhanced_monitoring_requirements": ["e.g., 'Expanded PF Form for hedge fund position reporting', 'Central bank direct monitoring of non-bank leverage']"],
          "changes_to_market_infrastructure": ["e.g., 'CCPs revised margin models to include longer stress periods', 'Introduction of daily stress testing for LDI funds']"]
        },
        "explanation": "The concrete, enduring changes to the formal regulatory framework intended to prevent a repeat."
      },
      "evolution_of_market_practice_and_risk_management": {
        "value": {
          "changes_in_investor_behavior": "[e.g., 'Pension funds now demand higher liquidity buffers from LDI managers', 'Hedge funds reduce gross leverage and diversify prime brokerage relationships']"],
          "advancements_in_risk_models": "[e.g., 'Widespread adoption of Expected Shortfall over VaR', 'Integration of liquidity-adjusted risk metrics (LaVaR)']",
          "theoretical_development": "[e.g., 'Academic literature on 'leverage cycles' and 'fire sale externalities' entered mainstream finance textbooks']"
        },
        "explanation": "Captures the organic changes in how market participants manage risk, reflecting a deeper, internalized learning."
      },
      "legacy_and_incorporation_into_financial_lore": {
        "value": {
          "event_as_a_reference_point": "[e.g., 'Now referred to as 'an LDI-style event' when discussing liquidity in derivative hedging', 'The 'Quant Quake' of 2007 is a standard case study in master's finance programs']",
          "lasting_impact_on_policy_philosophy": "[e.g., 'Solidified the view that central banks must act as 'market makers of last resort' beyond the banking sector', 'Increased focus on the shadow banking system']"
        },
        "explanation": "Describes how the event became embedded in the culture, language, and fundamental assumptions of finance and financial policy."
      }
    }
  }
}

"""