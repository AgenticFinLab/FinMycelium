
def short_squeeze_prompt(text: str) -> str:
    return """
You are an expert market analyst and financial forensics specialist with deep expertise in market microstructure, behavioral finance, and systemic risk analysis. Your task is to reconstruct a complete, detailed, and fact-based simulation of a specified **Short Squeeze** event based on provided multi-source data (e.g., parsed news, regulatory filings, exchange data, social media analytics, broker announcements).

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of a Short Squeeze event. Your output must be a structured JSON that meticulously documents the pre-conditions, trigger mechanisms, explosive price action, unwind dynamics, and lasting consequences.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Fact & Data Synthesis**: Integrate quantitative (price, volume, short interest) and qualitative (news, social sentiment, corporate actions) data from all sources. Prioritize official data from exchanges, regulatory bodies (SEC, FINRA), and company filings. Note material discrepancies in `analysis_notes`.
2.  **Chronological & Causal Fidelity**: Maintain a strict event timeline. Clearly establish causal links: e.g., how a catalytic event amplified retail buying, leading to covering pressure, then margin calls, then parabolic price moves.
3.  **Multi-Actor Perspective**: Model the interplay and conflicting incentives between key actors: **Short Sellers (institutional/retail)**, **Long Buyers (especially retail catalysts)**, **Market Makers**, **Brokers**, and the **Underlying Company**.
4.  **Liquidity & Market Mechanics Focus**: Explain the role of market mechanics in the squeeze: borrowing costs (hard-to-borrow rates), margin requirements, options gamma exposure, order flow, and settlement (T+2).

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON.

```json
{
  "short_squeeze_simulation_report": {
    "metadata": {
      "event_name": "string | The canonical name for the event (e.g., 'GameStop Short Squeeze of January 2021').",
      "underlying_asset": "string | The ticker symbol and company name (e.g., 'GME - GameStop Corp.').",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation.",
      "primary_exchange": "string | Main trading exchange (e.g., 'NYSE').",
      "core_data_sources": "array[string] | Key sources used (e.g., ['FINRA Short Interest Data', 'SEC Form 13F filings', 'NYSE Trade & Quote data', 'Robinhood blog posts', 'r/WallStreetBets sentiment analysis']).",
      "event_period": {
        "ignition_date": "string (YYYY-MM-DD) | Start of the rapid price ascent phase.",
        "peak_date": "string (YYYY-MM-DD) | Date of absolute intraday or closing price peak.",
        "unwind_initiation_date": "string (YYYY-MM-DD) | Date when price began sustained decline from peak."
      }
    },
    "1_pre_squeeze_background": {
      "company_fundamentals_pre_event": {
        "business_model": "string | Brief description of the company's core business at time of event.",
        "financial_health": "string | Pre-event financial status (e.g., 'struggling, declining revenues, burning cash').",
        "market_cap_pre_event": "string | Approximate market capitalization just before the squeeze ignition."
      },
      "short_seller_thesis": {
        "primary_bearish_narrative": "string | The fundamental rationale for heavy shorting (e.g., 'brick-and-mortar retail is dying', 'unsustainable debt').",
        "key_short_sellers": "array[object] | Known major short entities/funds. Each object: {'name': 'string', 'estimated_short_position': 'string (optional)', 'public_stance': 'string'}."
      },
      "market_technical_setup": {
        "short_interest_ratio": "string | Short Interest as a percentage of float (e.g., '>140%') and/or days to cover (e.g., '~7 days') prior to ignition.",
        "borrow_cost_pre_squeeze": "string | Cost to borrow shares (annualized fee) before the squeeze (e.g., '1-5%').",
        "options_chain_activity": "string | Notable pre-event activity in call options (e.g., 'elevated open interest in out-of-the-money calls')."
      }
    },
    "2_catalyst_and_ignition": {
      "primary_catalysts": "array[object] | Events that sparked coordinated long buying. Each object: {'date': 'string', 'catalyst_type': 'string (e.g., Social Media, Corporate Action, Institutional Long)', 'description': 'string', 'impact_metric': 'string (e.g., 'retail buy volume spiked 300%')' }.",
      "long_side_coordination_mechanism": {
        "platforms_communities": "array[string] | Primary coordination hubs (e.g., ['r/WallStreetBets on Reddit', 'Discord channels', 'Twitter $GME hashtag']).",
        "prevailing_narrative": "string | The bullish/activist narrative driving retail buyers (e.g., 'stick it to the hedge funds', 'deep value turnaround', 'the squeeze is coming')."
      },
      "initial_price_volume_action": {
        "price_increase_phase_1": "string | Price move from start to early acceleration (e.g., '$20 to $40 in 2 days').",
        "volume_anomaly": "string | Trading volume vs. historical average (e.g., '10x average daily volume')."
      }
    },
    "3_the_squeeze_dynamics": {
      "feedback_loop_mechanics": {
        "covering_pressure": "string | Description of how initial price rises forced some shorts to buy back shares, fueling further rises.",
        "margin_call_impact": "string | Role of broker margin calls on short sellers, forcing involuntary covering.",
        "gamma_squeeze": "string | Explanation of how market makers hedging short call options exacerbated buying (if applicable).",
        "fomofomo_cycle": "string | Description of the 'fear of missing out' / 'fear of missing out on covering' dynamic."
      },
      "market_infrastructure_stress": {
        "clearinghouse_broker_actions": "array[object] | Key actions by intermediaries. Each object: {'entity': 'string (e.g., Robinhood, DTCC)', 'date': 'string', 'action': 'string (e.g., 'raised margin requirements', 'restricted buying of shares')', 'stated_reason': 'string' }.",
        "trading_halts": "number | Count of exchange-mandated trading halts during the peak.",
        "settlement_fails": "string | Any reported issues with T+2 settlement (e.g., 'increased fails to deliver')."
      },
      "peak_characteristics": {
        "absolute_price_peak": "string | The highest traded price (intraday) and date.",
        "intraday_volatility_at_peak": "string | Peak intraday price range as a percentage (e.g., 'Price swung from $350 to $120 and back to $300 in one session').",
        "estimated_short_cover_volume_at_peak": "string | Estimated percentage of pre-squeeze short interest that had covered by the peak."
      }
    },
    "4_unwind_and_aftermath": {
      "price_decline_trigger": {
        "primary_factors": "array[string] | Reasons for the reversal (e.g., ['Buying restrictions by major brokers', 'Exhaustion of retail buying power', 'New short entries at peak prices', 'Profit-taking by early long entrants']).",
        "liquidity_crunch_point": "string | Description of the moment when buy-side liquidity dried up."
      },
      "final_state_post_unwind": {
        "price_stabilization_level": "string | Price range where the asset stabilized weeks after the peak (e.g., 'settled around $100-150').",
        "remaining_short_interest": "string | Short interest as % of float after the main unwind (e.g., '~30%').",
        "implied_volatility_change": "string | Change in options-implied volatility from peak to post-event (e.g., 'IV dropped from 500% to 150%')."
      }
    },
    "5_impact_and_consequences": {
      "financial_outcomes_for_actors": {
        "short_seller_losses": "string | Estimated aggregate mark-to-market or realized losses for short sellers (e.g., 'Hedge funds lost an estimated $6B in January').",
        "retail_investor_gains_losses_distribution": "string | Analysis of outcomes for retail traders (e.g., 'Early entrants realized large gains; late entrants buying near peak suffered significant losses').",
        "brokerage_fines_settlements": "array[object] | Regulatory penalties. Each object: {'entity': 'string', 'amount': 'string', 'agency': 'string', 'reason': 'string'}."
      },
      "corporate_impact": {
        "capital_raising_activities": "string | If the company issued new shares during/after the event (e.g., 'Company sold $1B in new equity at elevated prices').",
        "strategic_changes": "string | Any changes in business strategy, board, or management influenced by the event.",
        "long_term_shareholder_base_change": "string | Shift in the composition of shareholders (e.g., 'high retail ownership lock-up')."
      },
      "systemic_and_regulatory_response": {
        "congressional_hearings": "array[string] | Summary of key governmental inquiries.",
        "regulatory_reviews_proposals": "array[string] | Rule changes proposed or implemented (e.g., ['SEC Rule 15c2-11 update', 'Review of Payment for Order Flow', 'Closer scrutiny of social media']).",
        "market_structure_debates": "array[string] | Key issues raised (e.g., ['Gameification of investing', 'Settlement cycle (T+1)', 'Transparency of short positions'])."
      }
    },
    "6_simulation_analysis_notes": {
      "key_pre_event_signals": "array[string] | Identifiable signals that a squeeze was possible (e.g., 'Extreme short interest + high retail call option buying').",
      "liquidity_critical_points": "string | Analysis of when and why market liquidity broke down.",
      "role_of_digital_information_ecosystem": "string | Assessment of how social media and zero-commission trading platforms accelerated and shaped the event.",
      "data_limitations_discrepancies": "array[string] | Note uncertainties (e.g., 'Precise daily short covering volume is estimated', 'Retail net position data is incomplete').",
      "simulation_confidence_level": "string | High/Medium/Low based on data quality and availability of granular transaction data."
    }
  }
}
```

### **INSTRUCTION FOR EXECUTION**
1.  **Analyze Holistically**: Process all provided data for the specified Short Squeeze event (e.g., "GameStop 2021"). Synthesize market data, regulatory reports, news, and social sentiment.
2.  **Populate the Schema**: Fill every JSON field with specific, extracted facts or reasoned estimates. For estimated fields, provide the logic in `simulation_analysis_notes`.
3.  **Model the Feedback Loops**: Explicitly connect the actions of one actor group (e.g., retail buying) to the constraints of another (e.g., short seller margin calls) within the narrative.
4.  **Output Strictly JSON**: Deliver **only** the raw JSON object, beginning with `{` and ending with `}`. Do not enclose it in markdown code blocks or add extra text.


"""