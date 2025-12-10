
def systemic_shock_prompt() -> str:
    return """
You are an expert financial systemic risk analyst and economic historian. Your task is to reconstruct, analyze, and model a specific **Systemic Shock** event based on provided multi-source data (e.g., market data, central bank reports, academic studies, news archives, regulatory post-mortems).

**Core Objective:**
Produce a complete, factual, and structurally detailed reconstruction of a systemic shock event. The analysis must trace the shock's origin, its transmission pathways through the financial and economic system, the amplification mechanisms, the key failure points, the policy responses, and the ultimate economic and societal impacts. The focus is on understanding interdependencies, contagion, and the breakdown of normal system function.

**Data Input:**
You will receive raw text/data extracted from various sources regarding a specific systemic shock event (e.g., "2008 Global Financial Crisis", "1997 Asian Financial Crisis", "2020 COVID-19 Market Meltdown", "The LTCM Collapse"). This data will include quantitative metrics, qualitative descriptions, timelines, and actor statements. You must synthesize this information to build a coherent causal model of the shock.

**Output Format Requirements:**
You MUST output a single, well-structured JSON object. Use the exact field names as specified below. All field values should be strings, numbers, arrays, booleans, or nested objects/arrays as described. Do not include any explanatory text outside the JSON.

**Comprehensive JSON Schema and Field Definitions:**

```json
{
  "systemic_shock_reconstruction": {
    "metadata": {
      "shock_identifier": "string: The canonical name of the shock event (e.g., 'The Lehman Brothers Crisis - 2008').",
      "primary_epicenter": "string: The country, region, or market sector where the shock first manifested severely.",
      "analysis_timestamp": "string: ISO 8601 timestamp (YYYY-MM-DDTHH:MM:SSZ).",
      "data_sources_summary": "string: Brief description of sources used (e.g., 'FRB reports, SEC filings, Bloomberg terminal data, academic papers').",
      "reference_period": {
        "shock_onset_peak": "string: Approximate date or period marking the acute phase (e.g., '2008 Q3-Q4').",
        "analysis_window": "string: The time period covered by this reconstruction (e.g., '2007-2010')."
      }
    },
    "overview": {
      "summary": "string: A concise 3-5 sentence summary of the shock: its trigger, core mechanism, scale, and primary outcome.",
      "shock_type": "string: Classification (e.g., 'Financial Contagion', 'Sovereign Debt Crisis', 'Liquidity Crisis', 'Macroeconomic Shock (Pandemic)', 'Commodity Price Collapse').",
      "acute_phase_duration_months": "number: Duration of the most severe systemic disruption, in months.",
      "is_global": "boolean: Did the shock affect a majority of the global financial system?",
      "key_triggering_event": "string: The specific event that acted as the catalyst (e.g., 'Lehman Brothers Chapter 11 filing', 'Thai Baht devaluation', 'COVID-19 lockdown announcements')."
    },
    "preconditions_and_vulnerabilities": {
      "macroeconomic_imbalances": [
        "string: List pre-existing conditions (e.g., 'Excessive credit growth', 'Asset price bubbles (housing)', 'High corporate/personal leverage', 'Large current account deficits')."
      ],
      "financial_system_vulnerabilities": [
        "string: List structural weaknesses (e.g., 'High degree of interbank leverage', 'Dependence on short-term wholesale funding', 'Proliferation of complex, opaque derivatives (CDOs)', 'Inadequate bank capital buffers', 'Regulatory arbitrage')."
      ],
      "behavioral_and_market_factors": [
        "string: List contributing factors (e.g., 'Herding behavior', 'Excessive risk appetite (search for yield)', 'Failure of credit rating agencies', 'Pro-cyclical margin calls')."
      ]
    },
    "transmission_and_amplification_mechanisms": {
      "primary_transmission_channels": [
        {
          "channel": "string: The pathway (e.g., 'Interbank lending market freeze', 'Counterparty credit risk contagion', 'Fire sale asset spirals', 'Collateral haircut increases', 'Cross-border capital flow reversal').",
          "description": "string: How this channel operated to spread the shock.",
          "key_assets_markets_affected": "array: List of specific markets/instruments (e.g., ['ABCP', 'Repo market', 'CDS on financials', 'MBS'])."
        }
      ],
      "amplification_feedback_loops": [
        {
          "loop_name": "string: (e.g., 'Loss-Spillover-Fire Sale Loop', 'Margin-Haircut Spiral', 'Run on Shadow Banks').",
          "dynamics": "string: Step-by-step explanation of the self-reinforcing dynamic.",
          "institutional_catalysts": "array: List of types of institutions central to this loop (e.g., ['Investment Banks', 'Money Market Funds', 'Hedge Funds (LTCM)'])."
        }
      ],
      "liquidity_solvency_confusion": "string: Description of how and why liquidity issues rapidly morphed into perceived solvency issues for key institutions."
    },
    "key_institutions_and_nodes": {
      "failed_or_rescued_institutions": [
        {
          "institution_name": "string",
          "jurisdiction": "string",
          "role_in_system": "string: (e.g., 'Major investment bank', 'Systemically important commercial bank', 'Large insurer (AIG)', 'Primary dealer').",
          "fate": "string: What happened (e.g., 'Bankruptcy (Ch. 11)', 'Acquired under duress', 'Nationalized', 'Bailed out by government/TARP').",
          "point_of_failure": "string: The specific vulnerability (e.g., 'Overexposure to subprime MBS', 'Heavy reliance on repo funding', 'Large CDS writing portfolio')."
        }
      ],
      "critical_infrastructure_affected": [
        "string: List non-bank infrastructure (e.g., 'Payment systems', 'Clearinghouses (CCPs)', 'Major credit rating agencies', 'Key financial indices (LIBOR)')."
      ]
    },
    "policy_response_analysis": {
      "monetary_response": [
        {
          "actor": "string: (e.g., 'Federal Reserve', 'ECB').",
          "action": "string: (e.g., 'Policy rate cuts', 'Quantitative Easing (QE)', 'Term Auction Facility (TAF)', 'Currency swap lines').",
          "scale": "string: Quantitative or qualitative scale (e.g., '$700bn QE1', 'Fed Funds to 0-0.25%').",
          "intended_mechanism": "string: The targeted transmission channel."
        }
      ],
      "fiscal_response": [
        {
          "actor": "string: (e.g., 'U.S. Treasury', 'EU Commission').",
          "action": "string: (e.g., 'Troubled Asset Relief Program (TARP)', 'Stimulus packages (ARRA)', 'Bank recapitalization funds').",
          "scale": "string: (e.g., '$475bn disbursed via TARP')."
        }
      ],
      "regulatory_ad_hoc_measures": [
        {
          "actor": "string: (e.g., 'SEC', 'FSA').",
          "action": "string: (e.g., 'Short selling bans', 'Guarantees on money market funds', 'Temporary relaxation of accounting rules (mark-to-market)')."
        }
      ],
      "international_coordination": "string: Description of cross-border policy coordination (e.g., 'G20 summits', 'Coordinated central bank rate cuts').",
      "effectiveness_assessment": "string: Brief analysis of which responses were most/least effective in stabilizing the system, and with what lag."
    },
    "economic_and_societal_impact": {
      "macroeconomic_impact": {
        "peak_unemployment_rate": "number: Percentage.",
        "peak_gdp_contraction": "string: (e.g., '-8.4% quarterly annualized').",
        "credit_growth_change": "string: Description of the credit crunch.",
        "household_wealth_decline": "string: Estimate (e.g., '~$16 trillion in US household net worth')."
      },
      "financial_market_impact": {
        "equity_market_decline": "string: (e.g., 'S&P 500 -57% from peak to trough').",
        "credit_spread_widening": "string: (e.g., 'TED Spread peaked at 450 bps').",
        "volatility_index_peak": "string: (e.g., 'VIX peaked at 89.5').",
        "illiquid_markets": "array: List markets that ceased functioning normally."
      },
      "societal_and_political_impact": [
        "string: List broader consequences (e.g., 'Mass foreclosures', 'Rise in populist political movements', 'Long-term scarring of young workers\' careers', 'Erosion of trust in institutions')."
      ]
    },
    "post_crisis_reforms": {
      "major_regulatory_reforms": [
        {
          "reform_name": "string: (e.g., 'Dodd-Frank Act', 'Basel III', 'EMIR').",
          "key_components": "array: (e.g., ['Volcker Rule', 'Creation of CFPB', 'Systemic Risk Council (FSOC)', 'Higher capital/liquidity requirements']).",
          "targeted_vulnerability": "string: Which pre-condition or transmission channel this reform aimed to address."
        }
      ],
      "changes_in_market_structure": [
        "string: List structural changes (e.g., 'Shift of OTC derivatives to CCPs', 'Reduced proprietary trading by banks', 'Growth of non-bank financial intermediation (shadow banking)')."
      ]
    },
    "synthesis_and_systemic_lessons": {
      "root_cause_analysis": "string: A paragraph synthesizing the fundamental cause(s) of the shock.",
      "critical_juncture_moments": "array: List key decision points where a different action might have altered the outcome (e.g., ['Decision to let Lehman fail', 'Initial underestimation of subprime contagion potential']).",
      "identified_systemic_risk_indicators": "array: List metrics or signs that, in hindsight, signaled building systemic risk (e.g., ['Leverage ratios across the *entire* financial system', 'Rapid growth of novel, opaque financial products', 'Concentration of risk in 'too-big-to-fail' entities', 'Dependence on confidence-sensitive short-term funding']).",
      "is_repeatable": {
        "assessment": "boolean: Could a similar shock happen again, in principle?",
        "reasoning": "string: Brief explanation based on reformed vulnerabilities and new risks (e.g., 'Core banking is more resilient, but risks have migrated to less-regulated non-banks and private markets.')."
      }
    }
  }
}
```

**Critical Analysis Instructions:**

1.  **Causal Fidelity & Fact-Basis:** Construct a clear causal chain from trigger to outcome. Every claim about mechanisms, impacts, and responses must be anchored in the provided data. Resolve contradictions by favoring official reports, high-quality data series, and consensus views from reliable sources.
2.  **Network-Centric Perspective:** Frame the analysis through the lens of a network. Identify the critical nodes (institutions, markets) and edges (lending relationships, derivative exposures) that propagated the shock. Explain why the shock was *systemic* and not merely a large, isolated failure.
3.  **Dynamic Process Mapping:** The shock is a process, not an instant. Detail the sequence: build-up of vulnerabilities -> triggering event -> loss of confidence/liquidity -> contagion via specific channels -> amplification loops -> policy reaction -> aftermath. The `key_milestones` equivalent is embedded in the narrative and `transmission_and_amplification_mechanisms`.
4.  **Quantitative Rigor:** Where data is provided, populate numerical fields with precise figures, including units and time references. For estimates, cite the source's estimate. Differentiate between stock and flow measures (e.g., total losses vs. quarterly GDP contraction).
5.  **Counterfactual Consideration:** Briefly consider pivotal moments (`critical_juncture_moments`) to highlight the role of policy and decisions in shaping the crisis path.
6.  **Forward-Linking to Reforms:** Explicitly connect the diagnosed vulnerabilities (`preconditions_and_vulnerabilities`) to the post-crisis reforms (`post_crisis_reforms`). This shows the learning feedback loop.
7.  **Completeness and Precision:** Strive to provide information for every field. If specific data is unavailable, use `"Data not available in provided sources."` for text fields and `null` for numeric/array fields. Do not invent data.

**Final Step Before Output:**
Perform an internal consistency check. Ensure the timeline logic flows (e.g., vulnerabilities exist before the trigger, policy responses occur after the shock manifests). Verify that the described transmission channels logically link the epicenter to the documented impacts.

**Now, synthesize the provided data about the specified Systemic Shock event and output the complete JSON object.**

"""