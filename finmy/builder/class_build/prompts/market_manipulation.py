
def market_manipulation_prompt(text: str) -> str:
    return """
 You are an expert financial forensic analyst and market surveillance specialist specializing in deconstructing complex market manipulation schemes. Your task is to reconstruct a complete, detailed, and fact-based narrative of a specified market manipulation event (e.g., "Pump and Dump," "Spoofing," "Wash Trading") based on provided multi-source data (parsed web content, regulatory filings, court documents, trading data analysis, news reports).

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of the market manipulation scheme. Your output must be a structured JSON that meticulously documents the event's planning, execution mechanics, market impact, detection, and legal consequences.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Evidence-Based Synthesis**: Integrate information from all provided sources. Prioritize official data sources (e.g., SEC/CFTC orders, criminal indictments, FINRA alerts, exchange disciplinary notices) for factual assertions about trades, communications, and charges. Note significant discrepancies in the `analysis_notes` field.
2.  **Temporal-Causal Logic**: Construct a timeline where market events (price/volume spikes), manipulative actions (orders, communications), and external triggers (news, investigations) are linked in a cause-and-effect chain.
3.  **Trading Logic Consistency**: Model the manipulative trading strategy (e.g., order placement hierarchy in spoofing, wash trade pairing) in a technically coherent manner. Clearly distinguish between *real* market impact and *artificial* activity created by the scheme.
4.  **Multi-Actor Coordination**: If applicable, detail how different actors (traders, promoters, facilitators) interacted to execute the scheme.

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the following schema. Do not include any explanatory text outside the JSON.

```json
{
  "market_manipulation_simulation_report": {
    "metadata": {
      "case_name": "string | The commonly recognized name (e.g., 'Spoofing in Precious Metals Futures by Trader X', 'The XYZ Stock Social Media Pump & Dump').",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation.",
      "data_sources_summary": "array[string] | Brief list of primary data sources used (e.g., ['CFTC Order 12345', 'DOJ Indictment CR-22-001', 'NASDAQ Suspension Notice', 'Twitter data archive']).",
      "primary_jurisdiction": "string | Primary legal/regulatory jurisdiction (e.g., 'U.S. (CFTC/SEC)', 'UK (FCA)', 'Hong Kong SFC').",
      "manipulation_subtype": "string | Specific type (e.g., 'Pump and Dump', 'Layering/Spoofing', 'Wash Trading', 'Quote Stuffing', 'Marking the Close')."
    },
    "1_overview": {
      "executive_summary": "string | A concise 3-5 sentence summary: the asset targeted, the core manipulative technique used, the scale of impact, and the final outcome (e.g., detection, penalty).",
      "active_manipulation_period": {
        "start_date": "string (YYYY-MM or YYYY-MM-DD) | Start of identified manipulative trading/promotional activity.",
        "peak_impact_date": "string (YYYY-MM-DD) | Date of maximum artificial price distortion or volume.",
        "end_date": "string (YYYY-MM-DD) | Date of last manipulative act or regulatory halt.",
        "duration_days": "number | Approximate active duration in days."
      }
    },
    "2_actors_and_entities": {
      "perpetrators": [
        {
          "name": "string | Individual or entity identifier.",
          "role_in_scheme": "string | e.g., 'Mastermind & Head Trader', 'Promoter/Influencer', 'Wash Trade Counterparty'.",
          "control_method": "string | How they executed control (e.g., 'controlled 5 brokerage accounts for spoofing', 'led Telegram group with 10k members').",
          "credibility_source": "string | What gave them influence/access (e.g., 'fake analyst persona', 'registered broker', 'anonymous Twitter account with large following')."
        }
      ],
      "facilitators_and_platforms": [
        {
          "entity": "string | e.g., 'Specific Dark Pool', 'Social Media Platform Y', 'Compliant Broker-Dealer Z'.",
          "role": "string | e.g., 'Provided venue for manipulative orders', 'Amplified false narratives via algorithm', 'Failed to monitor for wash trades'."
        }
      ],
      "target_market_and_victims": {
        "targeted_asset": {
          "name": "string | e.g., 'Acme Corp Stock (ACME)'.",
          "market_cap_category": "string | e.g., 'Micro-cap', 'Small-cap', 'Commodity Futures'.",
          "pre_manipulation_liquidity": "string | Description of normal trading volume/volatility."
        },
        "victim_profile": "string | Description of those harmed (e.g., 'retail investors chasing momentum', 'algorithmic traders reacting to spoof orders', 'counterparties on the opposite side of artificial trades')."
      },
      "regulators_and_enforcers": "array[string] | Agencies that intervened (e.g., ['U.S. Commodity Futures Trading Commission (CFTC)', 'Department of Justice (DOJ)'])."
    },
    "3_manipulation_mechanics": {
      "core_technique_description": "string | Detailed, step-by-step explanation of the manipulative tactic as executed in this case.",
      "setup_and_accumulation_phase": {
        "initial_position": "string | How perpetrators established their core position (e.g., 'quietly accumulated long position in OTC shares', 'entered short futures position before spoofing attack').",
        "narrative_creation": "string | The false or misleading narrative crafted (e.g., 'imminent FDA approval rumor', 'fake technical analysis showing 'guaranteed' breakout')."
      },
      "execution_phase_artificial_inflation": {
        "market_action_components": {
          "order_book_manipulation": "array[string] | Descriptions of order patterns (e.g., ['Large non-bonafide sell orders placed 2% above ask to create false resistance', 'Rapid cancel-replace of buy orders to simulate demand']).",
          "trade_manipulation": "array[string] | Descriptions of trade patterns (e.g., ['Pre-arranged matching trades between controlled accounts at increasing prices', 'Wash trades executed to inflate volume metrics'].)"
        },
        "information_warfare_components": {
          "communication_channels": "array[string] | e.g., ['Discord', 'StockTwits', 'YouTube', 'Direct Messages'].",
          "content_themes": "array[string] | Examples of messages/posts used to incite buying (e.g., ['$ACME is the next Tesla!', 'Short squeeze imminent, get in NOW!'].)"
        },
        "quantified_impact": {
          "price_increase_percentage": "number | Percentage increase from pre-pump to peak.",
          "volume_increase_multiple": "number | Multiple of average daily volume achieved at peak.",
          "market_depth_distortion": "string | Description of how the order book was affected."
        }
      },
      "cashout_and_exit_phase": {
        "liquidation_strategy": "string | How perpetrators sold their position (e.g., 'Sold shares incrementally into retail buying frenzy over 3 days', 'Executed large block sell order triggering price collapse').",
        "attempts_to_conceal": "string | Actions to hide the exit (e.g., 'Continued posting bullish messages while selling', 'Used multiple small orders across different brokers')."
      }
    },
    "4_event_timeline": [
      {
        "date": "string (YYYY-MM-DD) | Approximate date.",
        "event_description": "string | A significant action or occurrence (e.g., 'Perpetrator A begins accumulating position', 'First coordinated pump message posted in Telegram group', 'Trading volume exceeds 500% of average', 'Regulator Y requests trading data from Exchange Z', 'Major sell order by perpetrator executed').",
        "category": "string | 'Setup', 'Narrative Push', 'Market Action (Pump/Spoof)', 'Peak', 'Cashout', 'Detection', 'Enforcement'."
      }
    ],
    "5_detection_and_collapse": {
      "detection_trigger": {
        "primary_cause": "string | What ultimately exposed the scheme (e.g., 'Exchange surveillance algorithms flagged spoofing pattern', 'Whistleblower from within chat group', 'Unusual price & volume activity triggered SEC review', 'Blockchain analysis revealed connected wallets').",
        "key_detection_date": "string (YYYY-MM-DD)"
      },
      "regulatory_mechanical_response": {
        "trading_halts": "string | Were any halts/suspensions imposed? When and by whom?",
        "account_freezes": "string | Were perpetrator accounts frozen? When?"
      },
      "final_state_post_manipulation": {
        "asset_price_trajectory": "string | Description from pre-manipulation -> peak -> post-crash stabilization level.",
        "market_quality_impact": "string | Assessment of lasting damage to the asset's market (e.g., 'permanent loss of liquidity', 'continued elevated volatility')."
      }
    },
    "6_quantification_and_impact": {
      "financial_quantification": {
        "perpetrator_illicit_gain": "string | Estimated total gross profit from the manipulation (e.g., '$4.2 million from stock sales').",
        "estimated_investor_losses": "string | Estimated total losses to defrauded market participants.",
        "artificial_volume_proportion": "string | Estimated percentage of total volume during the period deemed manipulative."
      },
      "legal_and_regulatory_outcome": {
        "charges_filed": "array[string] | e.g., ['Commodities Fraud', 'Wire Fraud', 'Securities Fraud', 'Spoofing (under Dodd-Frank)']. ",
        "settlement_disgorgement_fines": {
          "disgorgement": "string | Amount ordered to be returned (ill-gotten gains).",
          "civil_penalty": "string | Monetary fine imposed.",
          "total": "string"
        },
        "criminal_sentences": "array[object] | For individuals: [{'name': 'string', 'sentence': 'string (e.g., 24 months imprisonment)'}]",
        "entity_resolution": "string | Outcome for any involved firms (e.g., 'Broker-Dealer A fined $1M and required to enhance surveillance')."
      },
      "victim_recovery": {
        "restitution_fund_established": "boolean",
        "recovery_mechanism": "string | e.g., 'Fair Fund distribution by SEC', 'Class action settlement', 'None'.",
        "estimated_recovery_rate_for_losses": "string | If known/estimable."
      },
      "systemic_and_reputational_impact": {
        "regulatory_policy_changes": "array[string] | Any rule changes prompted (e.g., ['Enhanced spoofing detection mandates for exchanges', 'Stricter rules for social media financial influencers'].)",
        "market_integrity_perception": "string | Broader impact on confidence in the affected market segment.",
        "notable_collateral_damage": "array[string] | e.g., ['Legitimate company XYZ faced reputational harm', 'Retail broker W faced lawsuits for failure to supervise']. "
      }
    },
    "7_simulation_analysis_notes": {
      "key_manipulation_signatures": "array[string] | List the specific trading or communication patterns that were the 'smoking guns'.",
      "vulnerabilities_exploited": "array[string] | Systemic weaknesses used (e.g., ['Low liquidity of micro-cap stocks', 'Speed of order cancellation in electronic markets', 'Anonymity of certain social platforms'].)",
      "effectiveness_of_response": "string | Brief analysis of how effective detection and enforcement were (timeliness, proportionality).",
      "data_limitations_or_conflicts": "array[string] | Note any major gaps or conflicts in source data.",
      "simulation_confidence_level": "string | High/Medium/Low based on completeness and reliability of provided data."
    }
  }
}   
    
    """