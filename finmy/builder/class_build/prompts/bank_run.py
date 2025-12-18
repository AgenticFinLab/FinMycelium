

def bank_run_prompt() -> str:
    return """
You are a financial historian and forensic analyst specializing in systemic risk and institutional failure.

**Objective:** To reconstruct a comprehensive, granular, and analytically profound narrative of a specified `bank_run` event by integrating user-provided data and/or retrieved information. The output must be a single, extensive JSON object that functions as a multi-dimensional case study, capturing not only the sequential timeline but also the underlying economic, regulatory, psychological, and sociological dimensions.

**Output Format:** A single, extensive JSON object adhering strictly to the schema provided. No preamble, no concluding text.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must have a root key `"bank_run_reconstruction"`. The primary substructure follows the six-stage "Sequence of Events Associated with a Failure of Foresight" model, supplemented by a detailed `metadata` section and an `integrated_analysis` section for cross-cutting themes.
2.  **Lifecycle Phases:** Populate each of the six stages (`stage_I` to `stage_VI`) with granular, fact-based fields. Each field within a stage should represent a specific, documented event, condition, actor's decision, market datum, or communicative act relevant to that phase.
3.  **Granular Fields:** Every field must be populated with specific, concrete information. Avoid generic statements. Use precise dates, monetary figures, percentages, document names (e.g., SEC filings, internal memos), direct quotes from key figures, social media metrics, and specific policy titles. Where exact data is unavailable, provide the best-estimate and note the uncertainty (e.g., "estimated_between_X_and_Y").
4.  **Integrated Explanation:** Each field's value must contain its own explanation. The format should be: `"[Specific factual data or description]. Explanation: [A concise sentence explaining the significance, cause, or consequence of this data point within the context of the bank run's progression.]"`
5.  **Fact-Based:** All information must be sourced from the provided materials or credible, verifiable public records. Do not fabricate or infer details without an evidential basis. If critical information for a suggested field is missing, you may omit that specific field or note its absence.
6.  **Comprehensiveness:** The JSON should be exhaustive. Consider all angles: the institution's specific profile, the macroeconomic backdrop, depositor demographics and behavior, regulatory posture, media dynamics, technological channels (e.g., digital banking accelerating withdrawals), risk management failures, funding composition, asset-liability mismatch details, interbank exposures, official communication (and miscommunication), legal actions, and long-term policy impacts.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "bank_run_reconstruction": {
    "metadata": {
      "event_common_name": "[e.g., 'The Collapse of Silicon Valley Bank (SVB)']. The colloquial name for the crisis.",
      "primary_institution_name": "[Full legal name of the bank that suffered the run, e.g., 'Silicon Valley Bank, a division of SVB Financial Group'].",
      "institution_primary_jurisdiction": "[Country and state of primary regulator, e.g., 'United States, California (OCC)']. Explanation: Identifies the key regulatory authority overseeing the bank.",
      "key_associated_entities": ["List of critical subsidiaries, parent companies, or linked entities (e.g., 'SVB Capital', 'SVB Securities') involved or affected."],
      "crisis_timeframe": {
        "precipitating_event_date": "YYYY-MM-DD. The date of the specific event that triggered widespread panic.",
        "peak_withdrawal_dates": "YYYY-MM-DD to YYYY-MM-DD. The core days of intense withdrawal activity.",
        "regulatory_intervention_date": "YYYY-MM-DD. The date regulators seized control or announced a systemic risk exception.",
        "resolution_announcement_date": "YYYY-MM-DD. The date a final resolution (sale, liquidation, guarantee) was announced."
      },
      "scale_and_impact": {
        "total_deposits_pre_crisis": "XX.XX billion (Currency). The total deposit base as of the last quarterly report before the run. Explanation: Establishes the bank's size and the potential exposure.",
        "deposits_above_insurance_limit": "XX% or XX billion. The proportion/value of deposits exceeding the national deposit insurance guarantee (e.g., FDIC's $250k). Explanation: Highlights vulnerability as uninsured depositors have greater incentive to flee.",
        "withdrawals_during_run": "XX.XX billion over X days. The quantified outflow. Explanation: Demonstrates the velocity and magnitude of the loss of confidence.",
        "ultimate_resolution_cost": "Estimated cost to deposit insurance fund or taxpayer, if applicable.",
        "systemic_contagion_indicators": ["List of other institutions that experienced significant stock declines, deposit outflows, or required rescue in immediate aftermath (e.g., 'Signature Bank', 'First Republic Bank', 'Credit Suisse')."]
      },
      "asset_liability_mismatch_profile": {
        "primary_asset_composition": "e.g., 'Heavy concentration in long-dated US Treasuries and Mortgage-Backed Securities'. Explanation: Describes the assets whose market value fell when interest rates rose.",
        "held_to_maturity_vs_available_for_sale": "Breakdown in percentages or billions. Explanation: HTM assets hide unrealized losses from the capital ratio, but selling them to meet withdrawals crystalizes the loss.",
        "percentage_of_uninsured_depositors": "XX%. Explanation: A high percentage indicates a depositor base more likely to run, as they bear the full loss risk.",
        "depositor_concentration": "e.g., 'Heavily concentrated in venture capital firms and technology startups'. Explanation: Homogeneous depositor bases can act in a correlated, panicked manner based on industry signals."
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "macroeconomic_backdrop": "[e.g., 'Period of prolonged near-zero interest rates (post-2008 through 2021)']. Explanation: This environment made long-dated fixed-income securities appear to be safe, yield-generating assets, incentivizing banks like SVB to load up on them.",
      "industry_regulatory_orthodoxy": "[e.g., 'Post-2008 Dodd-Frank Act enhanced prudential standards, but EGRRPA (2018) raised the asset threshold for stricter oversight from $50B to $250B']. Explanation: SVB, with assets around $200B, was subject to less stringent stress testing and liquidity requirements, a culturally accepted norm at the time.",
      "institutional_business_model_narrative": "[e.g., 'SVB was celebrated as the essential bank for the innovation economy, providing specialized services to startups and VCs']. Explanation: This successful narrative masked underlying structural risks related to deposit concentration and interest rate exposure.",
      "perceived_strength_metrics_pre_crisis": "[e.g., 'SVB reported a CET1 capital ratio of 13.9% in Q4 2022, well above regulatory requirements']. Explanation: Standard regulatory metrics appeared healthy, reinforcing the notion of normality and solvency.",
      "risk_management_framework_on_paper": "[e.g., 'The bank had a designated Chief Risk Officer and reported on interest rate risk in the banking book (IRRBB)']. Explanation: Formal structures existed, creating an illusion of controlled hazard avoidance."
    },
    "stage_II_-_incubation_period": {
      "accumulation_of_unhedged_risk": "[e.g., 'Between 2019 and 2022, SVB's deposit base nearly tripled from $61B to $189B, which it invested heavily in long-dated securities']. Explanation: Rapid growth and a decision not to hedge interest rate exposure created a massive, latent vulnerability.",
      "shift_in_monetary_policy": "[e.g., 'The Federal Reserve began aggressively raising the Federal Funds rate from near 0% in March 2022 to ~4.5% by February 2023']. Explanation: This directly eroded the market value of SVB's bond portfolio, creating large unrealized losses.",
      "unrealized_losses_mounting": "[e.g., 'By end of 2022, SVB's Available-for-Sale (AFS) securities portfolio had an unrealized loss of $2.5B, and its Held-to-Maturity (HTM) portfolio an unrealized loss of $15.2B']. Explanation: These hidden losses destroyed the economic equity of the bank, though regulatory accounting obscured this from standard capital ratios.",
      "deposit_base_contraction": "[e.g., 'In 2022, as venture funding slowed, clients began burning through their cash, leading to a decline in SVB's total deposits']. Explanation: This forced the bank to consider selling assets to fund withdrawals, threatening to realize the hidden losses.",
      "internal_and_external_warnings_ignored": "[e.g., 'SVB's own interest rate risk model reportedly showed significant vulnerability to rising rates, and financial analysts began questioning its securities portfolio in mid-2022']. Explanation: These signals were at odds with the accepted belief in the bank's strength and were downplayed.",
      "communication_missteps": "[e.g., 'SVB's CEO sold $3.6M in company shares under a pre-arranged 10b5-1 plan in late February 2023']. Explanation: While potentially legal, such actions during the incubation period can later be perceived as a loss of confidence by leadership."
    },
    "stage_III_-_precipitating_event": {
      "catalyst_announcement": "[e.g., 'On March 8, 2023, SVB announced it had sold $21B of its Available-for-Sale securities, realizing a $1.8B after-tax loss, and launched a $2.25B capital raise']. Explanation: This action publicly crystallized the hidden losses and signaled severe financial stress, directly triggering panic.",
      "market_reaction_immediate": "[e.g., 'SVB's stock price (SIVB) plummeted 60% on March 9, 2023']. Explanation: The equity collapse was a public, real-time signal of extreme distress, amplifying fear.",
      "key_actor_statements": "[e.g., 'Influential venture capital firms like Peter Thiel's Founders Fund advised portfolio companies to withdraw funds from SVB on March 9']. Explanation: This coordinated action by central nodes in the bank's network transformed generalized concern into a targeted, organized run.",
      "information_amplification_channels": "[e.g., 'Panic spread rapidly through private WhatsApp and Telegram groups among startup CEOs and CFOs, and was fueled by public anxiety on Twitter and financial news networks']. Explanation: Digital communication enabled the run to achieve viral velocity, bypassing traditional slowing mechanisms."
    },
    "stage_IV_-_onset": {
      "operational_collapse": "[e.g., 'On March 10, 2023, depositors attempted to withdraw over $42B in a single day, leaving the bank with a negative cash balance of ~$958M']. Explanation: The scale and speed of withdrawals made the institution functionally illiquid, necessitating regulator intervention.",
      "regulatory_seizure": "[e.g., 'The California Department of Financial Protection and Innovation closed SVB and appointed the FDIC as receiver on March 10, 2023']. Explanation: This marked the formal failure and the start of the resolution process.",
      "immediate_systemic_spillovers": "[e.g., 'Shares of other regional banks with similar business models or balance sheet profiles crashed in after-hours and pre-market trading on March 10']. Explanation: Demonstrates the onset of contagion as the crisis moved from a single institution to a systemic threat.",
      "depositor_lockout_and_uncertainty": "[e.g., 'As of March 11, all uninsured depositors (holding ~$150B) faced uncertainty about recovering their full funds, threatening payroll for thousands of startups']. Explanation: The immediate human and economic consequence of the collapse."
    },
    "stage_V_-_rescue_and_salvage": {
      "systemic_risk_determination": "[e.g., 'On March 12, 2023, the US Treasury, Fed, and FDIC issued a joint statement declaring systemic risk and guaranteeing all deposits (insured and uninsured) at both SVB and Signature Bank']. Explanation: An unprecedented ad-hoc adjustment to prevent a broader financial crisis.",
      "liquidity_facilities_created": "[e.g., 'The Federal Reserve announced the Bank Term Funding Program (BTFP), offering loans of up to one year to banks, pledging Treasuries and MBS at par value']. Explanation: A direct policy response to the root cause (unrealized losses on bonds), allowing banks to meet withdrawals without forced sales.",
      "acquisition_process": "[e.g., 'The FDIC ran an accelerated auction process, culminating in the announcement on March 27, 2023, that First Citizens Bank would acquire SVB's deposits and loans']. Explanation: The salvage operation to resolve the failed entity.",
      "immediate_regulatory_scrutiny": "[e.g., 'The Fed, FDIC, and GAO all launched separate investigations into the supervision and failure of SVB on March 13 and 28, 2023']. Explanation: The beginning of the formal inquiry stage."
    },
    "stage_VI_-_full_cultural_readjustment": {
      "official_investigation_reports": "[e.g., 'The Federal Reserve's review, published April 28, 2023, cited SVB's management failures, catastrophic governance breakdown, and supervisory misjudgments by the San Francisco Fed']. Explanation: The authoritative post-mortem that assigns causes and forces a reassessment of beliefs.",
      "legislative_and_regulatory_proposals": "[e.g., 'Proposals included reversing parts of EGRRPA to apply stricter rules to banks with $100B+ in assets, reforming deposit insurance for business accounts, and enhancing liquidity stress testing']. Explanation: Concrete attempts to adjust precautionary norms based on the new understanding.",
      "industry_practice_changes": "[e.g., 'Banks globally accelerated efforts to hedge interest rate exposure, diversify deposit bases, and model the impact of social media-fueled runs']. Explanation: How the financial industry's internal "folkways" and "codes of practice" evolved.",
      "long_term_narrative_shift": "[e.g., 'The episode redefined "liquidity risk" to include the velocity of digital information and the behavioral dynamics of concentrated, networked depositors, not just asset maturities']. Explanation: The deepest cultural readjustment in how financial hazards are understood."
    },
    "integrated_analysis": {
      "failure_of_foresight_synthesis": "[A paragraph synthesizing how the stages linked: e.g., 'The normalcy of low rates (I) bred complacency, allowing risks to accumulate unseen (II). The capital raise announcement (III) made the invisible losses visible, triggering a networked digital run (IV) that required unprecedented state intervention (V) and a fundamental rethink of bank supervision (VI).']",
      "key_vulnerability_triad": "1. Asset-Liability Mismatch. 2. Concentrated, Uninsured Depositor Base. 3. Digital Information Velocity. Explanation: Identifies the interdependent factors that made this run particularly severe.",
      "analogy_to_other_historical_runs": "Comparison to, and distinctions from, runs like Northern Rock (2007) [retail, branch queues] or Washington Mutual (2008) [traditional wholesale]. Explanation: Places the event in historical context, highlighting the evolution of run dynamics."
    }
  }
}
"""