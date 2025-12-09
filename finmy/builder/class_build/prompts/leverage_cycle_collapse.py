
def leverage_cycle_collapse_prompt(text: str) -> str:
    return """
    You are an expert financial analyst, forensic investigator, and macroeconomist specializing in deconstructing systemic financial crises, with deep expertise in leverage cycles, margin financing, and counterparty risk. Your task is to reconstruct a complete, detailed, and fact-based simulation of a specified **Leverage Cycle Collapse** event (e.g., the Archegos Capital Management collapse of 2021) based on provided multi-source data (e.g., parsed web content, PDF documents, regulatory filings, court documents, financial news, analyst reports).

### **CORE OBJECTIVE**
Generate a comprehensive, logical, and evidence-driven simulation of the entire lifecycle of the leverage cycle, from its buildup to its explosive collapse. Your output must be a structured JSON that meticulously documents the economic drivers, key actors, leverage mechanics, triggering events, unwind dynamics, and systemic aftermath.

### **DATA PROCESSING & LOGIC CONSTRAINTS**
1.  **Fact-Based Synthesis**: Integrate all provided sources. Prioritize official regulatory findings (SEC, CFTC reports), exchange data, and legal filings. Note significant discrepancies in `analysis_notes`.
2.  **Temporal & Causal Logic**: Maintain a strict chronological narrative. Explicitly model the cause-and-effect chain: favorable conditions -> increased leverage -> asset inflation -> trigger -> margin calls -> forced selling -> price collapse -> counterparty losses.
3.  **Financial & Accounting Logic**: Accurately model leverage mechanics (e.g., derivative exposure vs. notional value, margin calculations, loan-to-value ratios). Distinguish between *notional exposure*, *economic interest*, and *cash equity*.
4.  **Systemic Interconnectedness**: Map the network of key players: the leveraged entity (e.g., family office, hedge fund), its prime brokers/lenders, other market participants, and the broader market for the underlying assets.

### **REQUIRED OUTPUT STRUCTURE: JSON SCHEMA**
Your output MUST be a valid JSON object conforming to the schema below. Do not include any explanatory text outside the JSON.

```json
{
  "leverage_cycle_collapse_simulation_report": {
    "metadata": {
      "event_name": "string | The commonly recognized name of the event (e.g., 'Archegos Capital Management Collapse').",
      "central_entity": "string | The primary highly-leveraged entity at the heart of the collapse (e.g., 'Archegos Capital Management').",
      "simulation_date": "string (ISO 8601) | Date of this analysis generation.",
      "data_sources_summary": "array[string] | Brief list of primary data sources used (e.g., ['SEC Complaint 21-cv-XXXX', 'Credit Suisse Report on Archegos', 'Bloomberg Terminal Data Mar 2021']).",
      "primary_asset_class": "string | The main asset class involved (e.g., 'Equity Swaps', 'Treasury Bonds', 'Mortgage-Backed Securities').",
      "geographic_epicenter": "string | Primary financial center where the collapse unfolded (e.g., 'New York, USA')."
    },
    "1_overview": {
      "executive_summary": "string | A concise 3-5 sentence summary: the entity's strategy, how leverage amplified it, the trigger, the nature of the collapse, and the immediate fallout.",
      "cycle_period": {
        "leverage_buildup_start": "string (YYYY-MM) | Approximate start of aggressive leverage accumulation.",
        "peak_leverage_date": "string (YYYY-MM-DD) | Date just before the triggering event.",
        "collapse_unwind_period": "string (YYYY-MM-DD to YYYY-MM-DD) | The acute phase of forced selling and price discovery.",
        "resolution_date": "string (YYYY-MM-DD) | Date of entity's default, liquidation filing, or regulatory resolution."
      }
    },
    "2_actors_and_structure": {
      "primary_leveraged_entity": {
        "name": "string | Legal name of the central entity.",
        "legal_structure": "string | e.g., 'Family Office', 'Hedge Fund', 'Investment Bank Proprietary Desk'.",
        "key_individuals": "array[object] | Key decision-makers. Each object: {'name': 'string', 'title_role': 'string', 'background': 'string'}",
        "investment_mandate_strategy": "string | Stated or de facto investment strategy (e.g., 'Long/short equity, concentrated positions, using total return swaps')."
      },
      "key_counterparties_lenders": {
        "prime_brokers": "array[object] | Major prime brokers providing leverage. Each object: {'firm_name': 'string', 'exposure_at_peak_usd': 'string', 'role': 'string (e.g., 'Lead swap counterparty', 'Margin lender')'}",
        "other_lenders_financiers": "array[string] | Other sources of funding."
      },
      "investor_profile": {
        "entity_ownership": "string | Who owned/controlled the leveraged entity (e.g., 'Single individual/family', 'Institutional investors').",
        "indirect_exposure": "string | Description of parties indirectly exposed (e.g., 'Funds investing in the prime brokers', 'Shareholders of the held stocks')."
      }
    },
    "3_leverage_mechanics_and_buildup": {
      "leverage_instruments_used": "array[object] | Detailed list of financial instruments used to gain exposure. Each object: {'instrument': 'string (e.g., 'Total Return Swap', 'Contract for Difference', 'Repo Loan', 'Futures')', 'key_terms': 'string (e.g., '5x initial margin', '85% loan-to-value')', 'purpose': 'string'}",
      "leverage_metrics_at_peak": {
        "estimated_gross_notional_exposure": "string | Total market value of all controlled assets (cash + borrowed).",
        "estimated_cash_equity": "string | Entity's own capital at risk.",
        "implied_leverage_ratio": "number | Gross Notional Exposure / Cash Equity.",
        "concentration_metrics": "string | Description of top holdings (e.g., '>50% of exposure in 5 stocks')."
      },
      "market_conditions_enabling_buildup": {
        "low_volatility_period": "boolean | Was a low-VIX environment a factor?",
        "easy_funding_conditions": "string | Description of credit/margin availability.",
        "competitive_prime_brokerage": "string | Did broker competition lead to lax margin terms?"
      }
    },
    "4_trigger_and_collapse_mechanics": {
      "precipitating_event": {
        "description": "string | The specific market move or news that started the unwind (e.g., 'Sharp decline in a key concentrated holding (ViaconCBS)').",
        "date": "string (YYYY-MM-DD)",
        "initial_margin_call_amount": "string | First material margin call issued."
      },
      "unwind_dynamics": {
        "margin_call_sequence": "string | Narrative of how margin calls from counterparties escalated.",
        "liquidation_process": "string | How positions were sold (e.g., 'Block trades by prime brokers, sold into open market over several days').",
        "fire_sale_impact": {
          "price_decline_in_held_assets": "string | Percentage drop in key assets during unwind.",
          "market_contagion_description": "string | Did selling pressure spill to related assets/sectors?"
        }
      },
      "counterparty_risk_materialization": {
        "loss_allocation_among_brokers": "array[object] | Summary of losses per major counterparty. Each object: {'firm_name': 'string', 'estimated_loss_usd': 'string', 'recovery_estimate': 'string'}",
        "default_chain_description": "string | Did any counterparty face solvency issues?"
      }
    },
    "5_final_state_and_immediate_aftermath": {
      "state_of_collapsed_entity": {
        "equity_wiped_out": "boolean | Was the entity's capital completely erased?",
        "residual_assets": "string | Any remaining assets post-liquidation.",
        "legal_status": "string (e.g., 'Liquidated', 'In Chapter 11', 'Settled with regulators')."
      },
      "financial_summary": {
        "total_losses_to_counterparties": "string | Sum of losses incurred by all lenders/prime brokers.",
        "peak_notional_exposure": "string | Reiteration of gross exposure at peak for context.",
        "final_cash_equity_loss": "string | Total loss of the entity's own capital."
      },
      "investor_outcome": {
        "entity_investors_fate": "string | Outcome for direct investors in the entity (if any).",
        "retail_investor_impact": "string | Impact on ordinary investors (e.g., via mutual funds holding the stocks)."
      }
    },
    "6_systemic_analysis_and_broader_impacts": {
      "regulatory_and_legal_response": {
        "agencies_involved": "array[string] | e.g., ['SEC', 'FINRA', 'FSA'].",  
        "key_findings": "array[string] | Main regulatory conclusions (e.g., 'Inadequate margin risk management by prime brokers', 'Lack of family office reporting').",
        "fines_settlements": "string | Summary of penalties imposed."
      },
      "market_structure_changes": {
        "prime_brokerage_policy_shifts": "array[string] | Changes in industry practices (e.g., 'Tighter margin terms for swaps', 'More frequent exposure reporting').",
        "regulatory_reforms_proposed": "array[string] | New rules or legislation considered."
      },
      "broader_economic_impacts": {
        "sector_performance_impact": "string | Performance of the related sector post-collapse.",
        "credit_availability_impact": "string | Did funding conditions tighten for similar strategies?",
        "reputation_damage": "string | Reputational impact on involved banks/actors."
      }
    },
    "7_simulation_analysis_notes": {
      "key_warning_signs_missed": "array[string] | List critical red flags overlooked by entity or counterparties (e.g., 'Extreme concentration', 'Opaque offshore structure', 'Lack of direct SEC oversight').",
      "sustainability_analysis": "string | Why the leverage structure was inherently unstable under stress.",
      "counterparty_risk_management_failures": "array[string] | Specific failures in risk management by lenders.",
      "data_discrepancies": "array[string] | Note any major conflicting information from sources.",
      "simulation_confidence_level": "string | High/Medium/Low based on data quality and consistency."
    }
  }
}

"""