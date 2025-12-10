
def liquidity_spiral_prompt() -> str:
    return """
You are an expert quantitative financial analyst and systemic risk specialist. Your task is to comprehensively analyze and reconstruct a specified **Liquidity Spiral** event based on provided multi-source data (e.g., market data, regulatory reports, academic papers, news articles, post-mortem analyses).

**Core Objective:**
Produce a complete, factual, and quantitatively detailed reconstruction of a liquidity spiral event. Your analysis must trace the self-reinforcing feedback loop from its triggers, through the core mechanisms of forced selling and price-impact, to its terminal point and aftermath. The output should serve as a forensic case study on systemic vulnerability.

**Data Input:**
You will receive raw text/data extracted from various sources regarding a specific market event characterized as a liquidity spiral (e.g., "March 2020 Treasury Market Liquidity Spiral", "UK Gilts Crisis September 2022", "Quant Quake / LTCM 1998"). The data may include price series, commentary on leverage, details on key entities, and regulatory findings. You must synthesize this information to build a coherent, evidence-based model of the spiral.

**Output Format Requirements:**
You MUST output a single, well-structured JSON object. Use the exact field names as specified below. All field values should be strings, numbers, arrays, booleans, or nested objects as described. Do not include any explanatory text outside the JSON.

**Comprehensive JSON Schema and Field Definitions:**

```json
{
  "liquidity_spiral_reconstruction": {
    "metadata": {
      "event_identifier": "string: The common name for the liquidity spiral event (e.g., 'UK Liability-Driven Investment (LDI) Crisis, Sep 2022').",
      "primary_market": "string: The core financial market where the spiral occurred (e.g., 'US Treasury Market', 'UK Gilt Market').",
      "primary_asset_class": "string: The asset class at the epicenter (e.g., 'Sovereign Bonds', 'Equities', 'Mortgage-Backed Securities').",
      "data_sources_summary": "string: Brief description of the types of sources used (e.g., 'Central Bank reports, hedge fund letters, exchange data, financial news')."
    },
    "overview": {
      "summary": "string: A concise 3-5 sentence summary of the entire spiral: the context, the core feedback mechanism, the climax, and the resolution/outcome.",
      "spiral_type": "string: Specific classification (e.g., 'Leverage-Induced Fire Sale Spiral', 'Margin Spiral', 'Volatility Spiral', 'Collateral Spiral').",
      "catalyst_asset(s)": "array: List of the specific financial instruments whose initial price decline triggered the spiral (e.g., ['30-Year UK Gilts'], ['Long-dated US Treasuries']).",
      "total_duration_days": "number: Approximate operational duration from initial catalyst to stabilization in days.",
      "was_systemically_important": "boolean: Indicates if the spiral posed a risk to the broader financial system, requiring intervention."
    },
    "key_entities_and_roles": {
      "forced_sellers": [
        {
          "entity_type": "string (e.g., 'Leveraged Hedge Fund', 'Liability-Driven Investment (LDI) Fund', 'Volatility-Targeting Fund', 'Margin-Called Retail Traders')",
          "examples": "array: Names or descriptions of prominent entities in this category, if publicly known.",
          "leverage_mechanism": "string: Description of how leverage was applied (e.g., 'Repo financing', 'Futures margin', 'Dynamic options hedging', 'Portfolio leverage').",
          "trigger_condition": "string: The specific rule or constraint that forced selling (e.g., 'Margin call at 85% collateral value', 'Volatility target breach', 'Regulatory capital ratio breach')."
        }
      ],
      "liquidity_providers": {
        "withdrawing_entities": [
          {
            "entity_type": "string (e.g., 'Market Makers', 'Principal Trading Firms', 'Banks')",
            "withdrawal_reason": "string: Why liquidity provision dried up (e.g., 'Risk limits breached', 'Increased volatility haircuts', 'Balance sheet constraints')."
          }
        ],
        "intervening_entities": [
          {
            "entity_name": "string (e.g., 'Bank of England', 'Federal Reserve')",
            "intervention_type": "string (e.g., 'Asset purchase facility', 'Liquidity injection', 'Temporary rule change')"
          }
        ]
      },
      "amplifying_agents": [
        {
          "agent_type": "string (e.g., 'Trend-following CTA funds', 'Delta-hedging options dealers', 'Algorithmic selling programs')",
          "amplification_mechanism": "string: How this agent's behavior reinforced the price move (e.g., 'Mechanical selling in response to price trend', 'Selling underlying to hedge put options after price drop')."
        }
      ]
    },
    "spiral_mechanism_dynamics": {
      "initial_catalyst": {
        "date": "string: Approximate start date (YYYY-MM-DD).",
        "event": "string: The macroeconomic or market event that caused the first price shock (e.g., 'Unexpectedly high inflation print', 'Central bank hawkish policy surprise', 'Counterparty default').",
        "magnitude_of_initial_shock": "string: Description or quantification of the initial price move (e.g., '30Y Gilt yield rose 50bps in 2 days')."
      },
      "feedback_loop_steps": [
        {
          "step_order": "number: The sequence number in the loop (1, 2, 3...).",
          "description": "string: A clear, causal description of one step in the reinforcing cycle. The final step should logically connect back to the first, closing the loop. (e.g., ['1. Asset prices fall.', '2. Leveraged entities face mark-to-market losses and declining collateral value.', '3. This triggers margin calls or breaches risk limits (VaR).', '4. To meet margin/deleverage, entities are forced to sell assets.', '5. Aggressive selling into illiquid markets further depresses prices.', '--> Loop back to Step 1.'])."
        }
      ],
      "liquidity_metrics_deterioration": {
        "bid_ask_spread_increase": "string: Qualitative or quantitative change (e.g., 'Increased by a factor of 5-10x', 'Widened dramatically').",
        "market_depth_change": "string: Description of the change in order book depth (e.g., 'Depth on top 3 price levels vanished').",
        "impact_per_trade": "string: Description of how much a typical sale moved the price (e.g., 'Price impact of trades increased significantly')."
      }
    },
    "quantitative_analysis": {
      "price_and_volume": {
        "peak_to_trough_price_decline": "number: Percentage decline in the price of the catalyst asset from pre-spiral peak to spiral trough.",
        "peak_volume_multiplier": "number: How many times higher trading volume was at peak stress vs. normal (e.g., 3 for 3x normal).",
        "velocity_of_decline": "string: Description of the pace (e.g., 'Majority of price drop occurred within 48 hours')."
      },
      "leverage_and_margin": {
        "estimated_aggregate_leverage_pre_spiral": "string: Estimate of leverage ratio (e.g., '5:1', 'High') for the key forced seller category.",
        "margin_call_volume": "string: Estimated total value of margin calls issued or funds required to post collateral (e.g., '£X billion in additional collateral calls').",
        "haircut_increase": "string: Description of how lenders increased margin requirements (haircuts) during the spiral (e.g., 'Haircuts on gilt collateral doubled from 1% to 2%+')."
      },
      "fire_sale_discount": {
        "estimated_discount_to_fair_value": "string: Estimate of how far prices fell below fundamental/model-based value at the trough (e.g., 'Traded at a 20-30% discount to theoretical value').",
        "price_reversal_post_stabilization": "string: The percentage price recovery after the spiral was broken, indicating the overshoot (e.g., 'Prices retraced 80% of the spiral move within a week')."
      }
    },
    "key_milestones": [
      {
        "date": "string: Approximate date and time if possible (YYYY-MM-DD or YYYY-MM-DD HH:MM).",
        "event": "string: Description of the milestone.",
        "significance": "string: Why this was a turning point in the spiral's progression (e.g., 'Initial rate shock', 'First major fund announces deleveraging', 'Liquidity disappears from futures market', 'Central bank intervention announced')."
      }
    ],
    "termination_and_stabilization": {
      "breaking_the_spiral": {
        "primary_breaker": "string: What action or event broke the feedback loop (e.g., 'Central bank asset purchases provided a price floor and liquidity', 'Forced sellers completed deleveraging', 'Volatility mean-reverted, triggering buying programs').",
        "stabilization_date": "string: Approximate date when prices stopped declining and volatility subsided (YYYY-MM-DD)."
      },
      "state_at_stabilization": {
        "market_functioning": "string: Description of market conditions post-spiral (e.g., 'Liquidity gradually returning but fragile', 'Functioning normally with elevated volatility').",
        "remaining_systemic_stress": "string: Description of any residual risks or imbalances (e.g., 'Some entities remained highly vulnerable', 'Collateral pipelines still impaired')."
      }
    },
    "aftermath_and_impact": {
      "direct_consequences": {
        "entities_failed_or_rescued": [
          {
            "entity_name": "string",
            "outcome": "string (e.g., 'Liquidated', 'Bailed out by parent', 'Required emergency funding from central bank')"
          }
        ],
        "estimated_total_losses": "string: Estimated sum of losses incurred by forced sellers and other market participants (e.g., '£XX billion in fund losses').",
        "collateral_damage_assets": "array: List of other unrelated asset classes that experienced stress due to spillover effects."
      },
      "regulatory_and_policy_response": [
        {
          "actor": "string (e.g., 'Prudential Regulation Authority (PRA)', 'Financial Stability Board (FSB)')",
          "action": "string (e.g., 'Review of leverage in LDI funds', 'Strengthened stress testing requirements for dealers', 'Permanent standing repo facility established')",
          "purpose": "string: The stated goal of the response (e.g., 'To increase resilience of the system to future liquidity shocks')."
        }
      ],
      "systemic_lessons_and_impacts": {
        "revealed_vulnerabilities": "array: List of structural flaws the spiral exposed (e.g., ['Pro-cyclicality of margin rules', 'Hidden concentration of leveraged positions', 'Fragility of market making under stress', 'Interconnectedness of seemingly separate entities through common risk factors']).",
        "changes_in_market_practices": "array: List of how market behavior evolved post-event (e.g., ['Funds now hold larger liquidity buffers', 'Increased use of stress scenario analysis', 'More conservative margin assumptions by prime brokers'])."
      }
    },
    "synthesis_and_red_flags": {
      "pre_conditions_identified": "array: List of necessary conditions that were present before the spiral (e.g., ['High aggregate leverage in a specific strategy', 'Crowded positioning in one asset', 'Low absolute market liquidity', 'Dependence on continuous market access for funding']).",
      "real_time_indicators": "array: List of metrics or signals that could have served as early warnings (e.g., ['Sharp increase in futures open interest alongside price decline', 'Rising implied volatility without clear news', 'Abnormal repo market activity', 'Widening of basis between cash and derivative markets']).",
      "comparison_to_theoretical_model": "string: Brief analysis of how this empirical event aligns with or deviates from academic models of liquidity spirals (e.g., 'Closely followed the Brunnermeier & Pedersen (2009) leverage spiral framework')."
    }
  }
}
```

**Critical Analysis Instructions:**

1.  **Fact & Data-Driven:** All conclusions, especially quantitative ones (`peak_to_trough_price_decline`, `fire_sale_discount`), must be anchored in the provided source data. Cite the evidence base for estimates. If data is conflicting, state the range or the most reliable estimate and note the discrepancy.
2.  **Mechanism-First Narrative:** The `feedback_loop_steps` must be the analytical core. Articulate a clear, causal chain that demonstrates the *self-reinforcing* nature. Avoid simple chronological listing; focus on the *interactions* between price, leverage, and liquidity.
3.  **Quantitative Emphasis:** Strive to populate numerical fields with specific estimates. Use phrases like "estimated to be", "reportedly", if precision is not absolute. Avoid using `"N/A"` unless information is genuinely unavailable.
4.  **Distinguish Actors & Motivations:** Clearly differentiate the behaviors and constraints of `forced_sellers`, `liquidity_providers`, and `amplifying_agents`. Their interaction *is* the spiral.
5.  **Identify the Loop Breaker:** Analyze why the spiral stopped. Was it exhaustion of sellers, a policy intervention that changed incentives, or a valuation floor being reached? This is a crucial part of the story.
6.  **Focus on Systemic Links:** Explain how stress was transmitted. Did it spread to other markets? Why? Through what channels (collateral, correlated positions, panic)?
7.  **Completeness:** Answer the implicit questions: What broke? How did it break? What were the costs? What did we learn? Ensure the JSON structure is fully addressed.

**Final Step Before Output:**
Perform a logical consistency check. Ensure the `feedback_loop_steps` form a closed loop. Verify that the `key_milestones` align with the `total_duration_days` and the phases of the spiral (catalyst, acceleration, climax, stabilization).

**Now, synthesize the provided data about the specified liquidity spiral event and output the complete JSON object.**
"""