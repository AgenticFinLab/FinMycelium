def forex_binary_options_fraud_prompt() -> str:
    return """
You are an expert financial forensic analyst specializing in online trading fraud. Your task is to comprehensively analyze and reconstruct a specified Forex (Foreign Exchange) or Binary Options fraud scheme based on provided multi-source data (e.g., victim testimonials, regulatory warnings, platform web archives, legal indictments, financial transaction records).

**Core Objective:**
Produce a complete, factual, and logically structured reconstruction of the fraudulent trading scheme. Detail its lifecycle from platform establishment or solicitation to termination, with emphasis on the technological facade, deceptive marketing, trade manipulation, fund misappropriation, and the differential impact on various stakeholders.

**Data Input:**
You will receive raw text/data extracted from various sources regarding a specific Forex/Binary Options fraud event (e.g., "iOption scheme", "AnyOption fraudulent platform"). This data may be fragmented, redundant, or contain inconsistencies. You must synthesize, cross-reference, and resolve discrepancies to build a coherent narrative grounded in the most reliable facts. Pay special attention to technical claims about trading platforms, specific trade practices, and withdrawal obstruction patterns.

**Output Format Requirements:**
You MUST output a single, well-structured JSON object. Use the exact field names as specified below. All field values should be strings, numbers, arrays, booleans, or nested objects as described. Do not include any explanatory text outside the JSON.

**Comprehensive JSON Schema and Field Definitions for Forex/Binary Options Fraud:**

```json
{
  "event_reconstruction": {
    "metadata": {
      "event_identifier": "string: The common name of the fraud scheme or platform (e.g., 'XYZ Forex Investment Scam', 'ABC Binary Options Fraud').",
      "primary_jurisdiction": "string: Country/region where the scheme was primarily legally registered or operated from.",
      "target_jurisdictions": "array: List of countries/regions where investors were primarily targeted and recruited.",
      "analysis_timestamp": "string: ISO 8601 timestamp of when this analysis is generated (YYYY-MM-DDTHH:MM:SSZ).",
      "data_sources_summary": "string: Brief description of the types of sources used (e.g., 'FCA warning notices, victim forum posts, leaked internal emails, software analysis reports')."
    },
    "overview": {
      "summary": "string: A concise 3-5 sentence summary of the fraudulent scheme, its claimed business, actual operation, and final outcome.",
      "fraud_type": "string: Specific classification. Must be one of: ['Manipulated Trading Platform Fraud', 'Fake Broker/Unregulated Platform', 'Signal Seller Scam', 'Investment Managed Account Fraud', 'Hybrid Ponzi with Trading Facade']. Describe briefly if 'Other'.",
      "trading_instruments": "array: List of financial instruments offered (e.g., ['Forex currency pairs (EUR/USD)', 'Binary Options on stocks', 'CFDs on commodities']).",
      "total_duration_months": "number: Approximate operational duration from first known solicitation to platform shutdown/regulatory action in months.",
      "is_cross_border": "boolean: True if the scheme involved operators, servers, or banking in different countries from the investors."
    },
    "perpetrators": {
      "primary_individuals": [
        {
          "name": "string",
          "role": "string (e.g., Platform CEO, Head of Sales, Lead Developer, Master Trader (Fake)', 'Payment Processor')",
          "background": "string: Relevant claimed background (e.g., 'purported Wall Street veteran') vs. actual known background.",
          "legal_status_at_terminal": "string: Status at event termination (e.g., 'Charged by SEC', 'At large', 'Cooperating witness')."
        }
      ],
      "primary_entities": [
        {
          "entity_name": "string (e.g., brokerage name, software company name)",
          "registration_location": "string: Jurisdiction of legal registration (often offshore).",
          "claimed_regulatory_licenses": "array: List of regulators the entity falsely claimed to be licensed by (e.g., ['FCA (UK)', 'CySEC (Cyprus)', 'ASIC (Australia)']).",
          "actual_regulatory_status": "string: The actual regulatory status (e.g., 'Unregulated', 'Clone firm', 'License revoked during operation').",
          "stated_business": "string: The claimed legitimate business (e.g., 'regulated online forex brokerage', 'financial technology provider').",
          "actual_fraudulent_operation": "string: The actual fraudulent operation (e.g., 'operating a manipulated trading platform against clients', 'misappropriating all deposits')."
        }
      ]
    },
    "mechanism_and_operations": {
      "platform_and_technology": {
        "platform_type": "string: e.g., 'Web-based platform', 'Proprietary desktop software', 'Mobile App', 'MT4/MT5 White Label'.",
        "claims_of_technology": "array: False technological claims made (e.g., ['AI-powered trading algorithm', 'Low-latency direct market access (DMA)', 'Professional charting tools with insider signals']).",
        "evidence_of_manipulation": "array: Evidence that the platform was fraudulent (e.g., ['Trades not routed to real market', 'Price feed manipulation', 'Slippage always against client', 'Impossible loss conditions in binary options', 'Withdrawal button malfunctioning'].)"
      },
      "investment_vehicle": "string: How funds were collected (e.g., 'Direct deposit to trading account on platform', 'Payment for trading software license', 'Investment into a pooled managed account').",
      "marketing_and_propaganda_channels": "array: List of channels used (e.g., ['Social Media ads (Facebook, Instagram)', 'YouTube fake success testimonials', 'Celebrity/influencer endorsements', 'Fake news article websites', 'High-pressure phone sales (boiler rooms)', 'Online trading webinars'].)",
      "key_propaganda_narratives": "array: List of false claims used to lure investors (e.g., ['Guaranteed 85% win rate', 'Risk-free trials', 'Make $1000 per day with no experience', 'Recover previous losses with our system', 'Exclusive access to bank-level signals'].)",
      "investor_acquisition_process": "string: Step-by-step description of how a victim was typically recruited, onboarded, and initially 'hooked' (e.g., 'Cold call -> free seminar -> pressured software purchase -> first small winning trade encouraged larger deposit').",
      "promised_return_structure": "string: Detailed terms of promised returns (e.g., '80-90% payout on successful binary options trades', 'Monthly returns of 5-20% from managed forex accounts').",
      "promised_use_of_funds": "string: Where perpetrators claimed investor money would be used (e.g., 'Leveraged margin trading on interbank forex market', 'Hedging strategies in binary options', 'Funding the development of AI trading software')."
    },
    "financial_analysis": {
      "scale_and_scope": {
        "estimated_total_victims": "number: Best estimate of total number of victim investors/traders.",
        "estimated_total_fiat_inflow": "number: Estimated total deposits/cash collected from victims (in primary currency).",
        "currency": "string: Primary currency of inflow estimate (e.g., 'USD', 'EUR', 'CNY').",
        "average_deposit_per_victim": "number: Rough average of initial/lifetime deposit.",
        "geographic_spread_of_victims": "array: List of countries/regions with significant victim presence."
      },
      "actual_use_of_funds": {
        "for_platform_facade_operations": "string: Portion used to maintain the illusion (server costs, fake office rent, sales staff commissions, marketing ads).",
        "for_fake_winnings_payouts": "string: Portion used to pay 'profits' to early victims (often small, strategic payouts to encourage more investment or verify withdrawals work).",
        "for_personal_enrichment": "string: Portion misappropriated by perpetrators (luxury assets, personal expenses, shell company transfers).",
        "for_actual_trading_losses": "string: Portion, if any, actually traded on real markets but lost (if it was a poorly managed scheme rather than pure fraud from start).",
        "evidence_of_misappropriation": "string: Specific evidence of fund diversion (e.g., 'Transferred directly to personal accounts of CEO in Cyprus', 'Used to purchase luxury real estate in Dubai')."
      },
      "fraud_dynamics": {
        "withdrawal_obstruction_pattern": "array: Describe methods used to block withdrawals (e.g., ['Impose impossible bonus rollover terms', 'Demand additional 'tax' payments', 'Claim technical errors', 'Become unresponsive'].)",
        "account_churning_evidence": "boolean: True if there is evidence that sales staff/IBs encouraged excessive trading to generate fees/commissions, depleting accounts.",
        "pressure_for_additional_deposits": "string: Description of tactics used to get victims to deposit more after initial losses (e.g., '‘Margin call’ threats requiring more funds to ‘save’ the position', 'Offering ‘recovery’ plans with more money')."
      }
    },
    "key_milestones": [
      {
        "date": "string: Approximate date (YYYY-MM or YYYY).",
        "event": "string: Description of the milestone.",
        "significance": "string: Why this was a turning point (e.g., 'Platform website launch', 'First major regulatory warning issued', 'Widespread complaints about withdrawal failures begin', 'Key payment processor cut ties', 'Domain seizure by authorities')."
      }
    ],
    "termination": {
      "trigger_event": "string: The immediate cause of collapse (e.g., 'Coordinated international law enforcement action (e.g., Operation Siren)', 'Massive DDoS attack followed by disappearance', 'Major media investigative report exposing the fraud', 'Core banking partner froze accounts').",
      "termination_date": "string: Approximate date of platform collapse/cessation of operations (YYYY-MM).",
      "state_at_termination": {
        "platform_status": "string: (e.g., 'Website offline/404', 'Trading halted but website up', 'Displaying 'under maintenance' message', 'Frozen by court order').",
        "customer_access": "string: Could victims access their accounts? (e.g., 'No access', 'Read-only access', 'Access but all balances显示为零').",
        "remaining_active_victims": "number: Estimated number of victims with active accounts or pending withdrawals at termination."
      }
    },
    "aftermath_and_impact": {
      "legal_and_regulatory_action": [
        {
          "actor": "string (e.g., 'CFTC (US)', 'FCA (UK)', 'Europol', 'Federal Police (Germany)')",
          "action": "string (e.g., 'Criminal indictment filed', 'Civil enforcement action', 'Cease and Desist order', 'Asset freezing order', 'Arrest warrants issued')",
          "target": "string: Whom the action was against (individual or entity).",
          "date": "string: Approximate date (YYYY-MM).",
          "status": "string: Current status of the action (e.g., 'Pending', 'Conviction obtained', 'Settled with fines')."
        }
      ],
      "perpetrator_outcomes": "string: Summary of legal and personal outcomes for main perpetrators (sentences, fines, asset forfeiture, extradition status).",
      "victim_outcomes": {
        "total_estimated_net_loss": "number: Estimated total victim net loss (Total Deposits - Any Withdrawals/Profits paid out).",
        "asset_recovery_estimate": "string: Estimated percentage or amount potentially recoverable through seizures, compensation funds, or lawsuits (e.g., '<5%', 'Approximately $2M identified for potential restitution').",
        "victim_demographics": "string: Description of major victim groups (e.g., 'Retail investors with no trading experience', 'Small business owners', 'Individuals seeking to recover from previous investment losses').",
        "psychological_social_impact": "string: Brief description of broader impacts (e.g., 'Victim suicides reported', 'Families lost life savings', 'Erosion of trust in online trading advertisements')."
      },
      "systemic_impacts": [
        "string: List broader impacts (e.g., 'Tighter regulations on binary options advertising in the EU', 'Increased scrutiny on MT4/5 white label providers', 'Public awareness campaigns launched by financial regulators')."
      ]
    },
    "synthesis_and_red_flags": {
      "identified_red_flags": "array: List of clear warning signs evident in hindsight specific to trading fraud (e.g., ['Promises of guaranteed high returns with low risk', 'Unregulated or offshore-registered entity', 'Pressure to deposit quickly with bonuses', 'Withdrawal delays and excuses', 'Proprietary platform with no independent verification', 'Salespeople focused on deposits, not trading strategy'].)",
      "comparison_to_classic_trading_fraud": "string: Brief analysis of how this scheme fits common patterns of forex/binary options fraud (e.g., 'Classic fake brokerage model with price manipulation', 'Hybrid: Initial signal service scam evolved into a Ponzi scheme to pay early subscribers')."
    }
  }
}
```

**Critical Analysis Instructions for Forex/Binary Options Fraud:**

1.  **Fact-Based & Source-Anchored:** Every data point must be traceable to provided sources. Resolve conflicts by prioritizing official regulatory documents, court filings, and credible investigative reports over marketing materials or unverified claims.
2.  **Technical Facade Focus:** Pay particular attention to the `platform_and_technology` and `fraud_dynamics` sections. Explain *how* the fraud was executed technically (manipulated software, fake trades) and operationally (withdrawal blocking).
3.  **Narrative of Deception:** Connect the marketing lure (`key_propaganda_narratives`) to the fraudulent mechanism (`evidence_of_manipulation`). Show how the initial experience (often a small win) was engineered to build false trust.
4.  **Quantitative Emphasis:** Provide numerical estimates even if approximate. For `total_estimated_net_loss`, distinguish gross deposits from net loss by considering any payouts made as part of the scheme.
5.  **Role-Centric Impact:** Clearly detail impacts on different actors: masterminds, sales staff (who may also be victims or perpetrators), early vs. late victims, and payment processors.
6.  **Full Chain Exposition:** The output must explicitly connect: The **lure** (fake success, regulatory lies), the **mechanism** (fake platform, manipulated trades), the **sustainment** (strategic payouts, pressure for more deposits, withdrawal obstruction), the **collapse trigger**, and the **consequences**.
7.  **Completeness:** Strive to fill every field. If information is absolutely unavailable, use the value `"Information not available in provided sources."` for string fields and `null` or `0` for numeric/array fields as appropriate. Do not invent data.

**Final Step Before Output:**
Perform an internal consistency check. Ensure the timeline aligns, the fraud type description matches the mechanisms described, and the scale of financials is plausible within the narrative. Verify that `estimated_total_fiat_inflow` is logically larger than or equal to `victim_outcomes.total_estimated_net_loss`.

**Now, synthesize the provided data about the specified Forex or Binary Options fraud event and output the complete JSON object.**

"""