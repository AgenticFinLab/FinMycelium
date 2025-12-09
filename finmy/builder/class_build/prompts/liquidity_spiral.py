
def liquidity_spiral_prompt(text: str) -> str:
    return """
You are an expert financial systemic risk analyst and market historian specializing in deconstructing and simulating complex market dynamics, particularly Liquidity Spirals. Your task is to reconstruct a complete, detailed, and fact-based narrative of a specified Liquidity Spiral event based on the provided multi-source data (e.g., parsed web content, PDF documents, financial reports, regulatory filings, academic papers, news archives).

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of a Liquidity Spiral. Your output must be a structured JSON that meticulously documents the event's preconditions, triggering mechanisms, key phases of the spiral, intervention efforts, and final outcomes.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Fact-Based Synthesis**: Integrate information from all provided sources. Resolve minor contradictions by prioritizing official data (e.g., central bank reports, exchange records, regulatory post-mortems). Note any significant discrepancies in the `simulation_analysis_notes.data_discrepancies` field.
2.  **Temporal & Causal Logic**: The narrative must follow a strict chronological order, explicitly linking causes and effects. Each phase of the spiral (e.g., initial shock -> forced selling -> price drop -> margin calls -> further selling) must be logically sequenced.
3.  **Financial & Market Logic**: Model the interplay between asset prices, leverage ratios, funding liquidity, and market liquidity with internal consistency. Quantify changes where data allows. Clearly distinguish between *reported* figures and *estimated/modeled* figures.
4.  **Multi-Actor Perspective**: Analyze the event from the perspectives of different key actors (e.g., leveraged funds, dealers, exchanges, regulators) and how their interdependent actions fueled or alleviated the spiral.

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON.

```json
{
  "liquidity_spiral_simulation_report": {
    "metadata": {
      "event_name": "string | The commonly recognized name of the event (e.g., 'The Quant Quake of 2007', 'The UK Gilt Crisis 2022').",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation.",
      "primary_asset_class": "string | The main asset class at the center of the spiral (e.g., 'Equities', 'Government Bonds (Gilts)', 'Mortgage-Backed Securities', 'Corporate Bonds').",
      "core_geographic_market": "string | The primary exchange or market where the spiral unfolded.",
      "data_sources_summary": "array[string] | Brief list of primary data sources used (e.g., ['BIS Quarterly Review Q4 2007', 'Fed Report on Market Liquidity', 'Financial Times Archives Sept 2022', 'LSE Circuit Breaker Logs'])."
    },
    "1_overview": {
      "executive_summary": "string | A concise 3-5 sentence summary of the entire event: the context, the core mechanism of the spiral (e.g., 'Leveraged ETF rebalancing meeting with dealer hedging constraints'), the peak intensity, and the final resolution.",
      "event_period": {
        "precondition_buildup_start": "string (YYYY-MM) | Approximate start of conditions ripe for a spiral (e.g., rising leverage, declining volatility).",
        "spiral_trigger_date": "string (YYYY-MM-DD) | The date of the initial shock or trigger.",
        "spiral_peak_date": "string (YYYY-MM-DD) | The date of maximum market dislocation and price deviation.",
        "market_stabilization_date": "string (YYYY-MM-DD) | The date when prices and liquidity largely normalized.",
        "total_duration_days": "number | Calculated active spiral duration in days."
      }
    },
    "2_preconditions_and_setup": {
      "macro_financial_background": "string | Description of the broader economic and financial conditions preceding the event (e.g., 'Period of low interest rates and compressed volatility leading to reach for yield').",
      "market_structure_factors": {
        "dominant_leverage_type": "string | The primary form of leverage involved (e.g., 'Repo financing', 'Derivative-based (e.g., swaps, futures)', 'ETF creation/redemption leverage').",
        "key_institutional_players": "array[object] | List of major player types and examples. Each object: {'player_type': 'string (e.g., Hedge Fund, Dealer, Pension Fund, ETF)', 'example_names': 'array[string]', 'typical_strategy': 'string'}",
        "liquidity_provision_landscape": "string | State of market-making and dealer balance sheet capacity pre-spiral."
      },
      "vulnerability_metrics_pre_spiral": {
        "average_leverage_ratio_key_players": "string | Estimated leverage (e.g., 'Hedge Fund Avg Debt/Equity: 4x').",
        "market_liquidity_indicators": "string | e.g., 'Bid-Ask spreads on core assets at 5-year lows', 'Depth of order book thinning'.",
        "concentration_of_positions": "string | Description of crowded trades or high ownership concentration in the affected asset."
      }
    },
    "3_trigger_and_spiral_mechanics": {
      "initial_shock": {
        "description": "string | The specific event that started the selling pressure (e.g., 'Surprise inflation print leading to rapid rate hike expectations', 'Default of a major counterparty', 'Sharp correction in a correlated asset').",
        "date": "string (YYYY-MM-DD)",
        "immediate_market_reaction": "string | First-round price move and volatility spike."
      },
      "spiral_phase_1_forced_initial_selling": {
        "who_was_forced_to_sell": "array[string] | Which entities faced the first round of constraints? (e.g., ['Delta-hedging dealers', 'Over-leveraged hedge funds facing mark-to-market losses'])",
        "selling_trigger": "string | The specific mechanism (e.g., 'Margin calls', 'Volatility-targeting fund rebalancing', 'Breach of VaR limits').",
        "estimated_volume_sold_phase1": "string",
        "price_impact_phase1": "string | e.g., 'Asset X price dropped 15% from trigger.'"
      },
      "spiral_phase_2_funding_liquidity_crunch": {
        "funding_channels_affected": "array[string] | e.g., ['Repo rollover became difficult', 'Prime brokers increased haircuts on collateral'].",        "who_faced_funding_pressure": "array[string] | Entities that could not secure usual funding.",
        "liquidity_hoarding_behavior": "boolean | Did banks/dealers start hoarding cash/balance sheet?",
        "impact_on_market_liquidity": "string | e.g., 'Dealer bid-offer spreads widened by 300%, depth vanished.'"
      },
      "spiral_phase_3_secondary_forced_selling": {
        "who_was_forced_next": "array[string] | e.g., ['Entities relying on now-scarce repo funding', 'Funds facing investor redemptions due to poor performance'].",        "trigger_for_this_phase": "string | e.g., 'Collateral value decline triggering additional margin calls (negative feedback loop).'",
        "estimated_volume_sold_phase2": "string",
        "cumulative_price_impact": "string | Peak-to-trough decline from initial trigger."
      },
      "feedback_loops_documented": "array[object] | List identified feedback loops. Each object: {'loop_name': 'string (e.g., Margin Spiral, Loss Spiral)', 'description': 'string', 'key_evidence': 'string'}",
      "was_there_a_fire_sale": "boolean | Did prices fall significantly below fundamental estimates due to forced selling?"
    },
    "4_interventions_and_peak": {
      "private_sector_actions": "array[object] | Actions by market participants to halt the spiral. Each object: {'actor': 'string', 'action': 'string', 'intended_effect': 'string', 'perceived_effectiveness': 'string (High/Medium/Low)'}",
      "public_sector_actions": {
        "central_bank_actions": "array[string] | e.g., ['Launched emergency gilt purchase program (QE)', 'Provided extraordinary liquidity via discount window'].",        "regulatory_exchange_actions": "array[string] | e.g., ['Temporarily suspended short selling', 'Invoked circuit breakers'].",        "government_actions": "array[string] | e.g., ['Announced fiscal backstop', 'Coordinated statement with other central banks']."
      },
      "liquidity_injection_scale": "string | Total value of liquidity provided by central banks during the event.",
      "point_of_maximum_pressure": {
        "date": "string (YYYY-MM-DD)",
        "key_metric_extremes": "string | e.g., '10-Year Gilt yield intraday peak: 5.0%', 'S&P 500 VIX peak: 85'.",        "anecdotes_of_market_dysfunction": "array[string] | e.g., ['ETF traded at 30% discount to NAV', 'No bids for AAA-rated bonds in size']."
      }
    },
    "5_resolution_and_aftermath": {
      "how_spiral_broke": "string | Description of the primary factor that stopped the spiral (e.g., 'Central bank's unconditional buyer-of-last-resort pledge restored confidence', 'Forced selling exhaustion', 'Coordinated dealer capital injection').",
      "price_recovery_trajectory": "string | How quickly and completely did prices recover? (e.g., 'Prices recovered 80% of the loss within 3 months, but remained 10% below pre-spiral levels for a year').",
      "immediate_casualties": {
        "failed_institutions": "array[object] | Institutions that collapsed or were rescued. Each object: {'name': 'string', 'fate': 'string (e.g., Bankruptcy, Forced Merger, Bailout)'}",
        "significant_losses_reported": "array[object] | Major losses announced. Each object: {'entity': 'string', 'estimated_loss': 'string', 'cause': 'string'}"
      },
      "market_structure_changes_post_event": "array[string] | Observable changes (e.g., ['Reduced reliance on certain leverage forms', 'Increased margin requirements for volatile assets', 'New dealer inventory caps'])."
    },
    "6_quantitative_impact_assessment": {
      "market_impact": {
        "peak_price_decline_affected_asset": "string | Percentage decline from pre-trigger to trough.",
        "volatility_index_peak": "string | e.g., 'VIX peaked at 82.7'.",        "aggregate_market_cap_loss": "string | Estimated total loss in the relevant market(s)."
      },
      "institutional_impact": {
        "total_estimated_losses_leveraged_players": "string",
        "number_of_funds_liquidated": "number | Approximate count.",
        "total_value_of_forced_sales": "string | Estimated sum of assets sold under duress."
      },
      "systemic_risk_indicators": {
        "spillover_to_other_assets_markets": "string | Description of contagion.",
        "impact_on_credit_availability": "string | e.g., 'Corporate bond issuance froze for 2 weeks'.",        "threat_to_financial_system_stability_perceived": "string (e.g., 'High - Central Bank declared systemic risk event')."
      }
    },
    "7_analysis_and_lessons": {
      "root_causes_analysis": "array[string] | Fundamental causes (e.g., ['Excessive and opaque leverage in non-bank sector', 'Pro-cyclical risk management models (VaR)', 'Fragmented liquidity provision']).",
      "key_red_flags_missed": "array[string] | Warning signs observable before the spiral (e.g., ['Rising leverage in system, declining market depth', 'Concentration of similar positions']).",
      "effectiveness_of_interventions": "string | Analysis of which public/private actions worked and which didn't.",
      "proposed_regulatory_policy_changes": "array[string] | Changes recommended or enacted post-event (e.g., ['Stress tests for non-bank leverage', 'Central bank standing facilities for broader range of counterparties']).",
      "simulation_confidence_level": "string | High/Medium/Low based on data quality, consistency, and model consensus.",
      "data_discrepancies": "array[string] | Note any major conflicting information from sources.",
      "alternative_scenarios_considered": "string | Brief mention of how the spiral could have been worse/better under different conditions."
    }
  }
}
```

### **INSTRUCTION FOR EXECUTION**
1.  **Thoroughly Analyze** all provided source data pertaining to the requested Liquidity Spiral event (e.g., "The [Specific Event Name]").
2.  **Extract and Synthesize** information to populate every field in the JSON schema above. For quantitative fields lacking precise data, provide reasoned, labeled estimates (e.g., "estimated_") based on available proxies and logical inference. Clearly note estimations in `analysis_and_lessons`.
3.  **Maintain Causal Narrative**: Ensure the report reads as a coherent story, linking the vulnerability of the pre-conditions to the specific trigger, detailing the mechanics of each spiral phase, and explaining the resolution.
4.  **Adhere to Schema**: Output **ONLY** the raw JSON object, beginning with `{` and ending with `}`. Do not use markdown code block syntax in your final output.
```
"""