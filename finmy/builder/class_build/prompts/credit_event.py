

def credit_event_prompt() -> str:
    return """
You are a forensic financial historian and credit events reconstruction specialist.

**Objective:** To reconstruct a comprehensive, deeply analytical, and granular narrative of a specified credit event (e.g., corporate bankruptcy, sovereign default, major fraud-induced failure, failure to pay, debt restructuring). Your output should function as a definitive, multi-layered case study that captures not just the factual timeline but the underlying cultural, regulatory, and market dynamics at each phase of its lifecycle, as defined by the "Sequence of Events Associated with a Failure of Foresight" framework.

**Output Format:** A single, extensive, and meticulously detailed JSON object.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must strictly follow the provided schema, organizing the event into `metadata` and the six lifecycle stages (I-VI). Each stage contains multiple thematic sections, and each section contains highly specific fields.
2.  **Lifecycle Phases:** Populate each stage with data that exemplifies its theoretical definition. Stage I should establish the "accepted reality." Stage II should detail the hidden cracks. Stage III is the trigger. Stage IV is the immediate fallout. Stage V is the reactive crisis response. Stage VI is the long-term systemic change.
3.  **Granular Fields:** Every field must be populated with the most specific, verifiable data possible. Avoid summaries. Use precise figures, dates, names of reports, specific regulatory clauses, direct quotes from key individuals, detailed descriptions of financial mechanics, and explicit sequences of actions.
4.  **Integrated Explanation:** The "explanation" for each field's value is NOT a separate key. Instead, the value itself should be a rich, self-contained string that presents the factual data *and* its significance/interpretation inline, forming a coherent analytical narrative for that data point.
5.  **Fact-Based:** All information must be grounded in verified sources, such as court filings (e.g., bankruptcy petitions, SEC complaints), official regulatory reports, audit findings, credible journalistic investigations, executive statements, and market data. If certain details are speculative or estimated, clearly denote them as such (e.g., "allegedly," "estimated," "according to the prosecutor's filing").
6.  **Comprehensiveness:** The JSON must aspire to be an exhaustive dossier. Consider all dimensions: legal, financial accounting, operational, governance, market microstructure, media narrative, psychological (e.g., investor sentiment, management hubris), technological (if applicable), and geopolitical. The goal is that a reader could understand the event in profound depth from this JSON alone.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "credit_event_reconstruction": {
    "metadata": {
      "event_identification": {
        "scheme_common_name": "e.g., 'The Enron Bankruptcy', 'The Lehman Brothers Collapse', 'The Argentina 2001 Sovereign Default'. The colloquial, market-wide name for the event.",
        "official_legal_case_name": "e.g., 'In re: Lehman Brothers Holdings Inc., Case No. 08-13555 (Bankr. S.D.N.Y.)'. The formal title of the primary bankruptcy proceeding or major regulatory action.",
        "primary_entity_or_issuer": "The full legal name of the corporation, sovereign nation, or financial institution at the center of the credit event.",
        "primary_perpetrator_or_key_figure_name": "e.g., 'Bernard L. Madoff', 'Jeffrey K. Skilling', 'Richard S. Fuld Jr.'. The individual most centrally associated with causing or presiding over the event. If a sovereign, key political figures.",
        "key_associated_vehicles_entities": ["e.g., 'Lehman Brothers International (Europe)', 'Enron Offshore Partnerships (e.g., LJM1, Chewco)', 'Madoff Securities International Ltd. (London)'. A list of special purpose entities, subsidiaries, or feeder funds instrumental in the events."],
        "event_classification_type": "e.g., 'Chapter 11 Bankruptcy', 'Sovereign Default (Foreign Law Bonds)', 'Ponzi Scheme Collapse', 'Failure to Pay Coupon', 'Distressed Debt Exchange (DDE)', 'Credit Event (per ISDA Definitions)'. The precise financial/legal categorization.",
        "designated_isda_credit_event": ["e.g., 'Bankruptcy', 'Failure to Pay', 'Restructuring' (as per the 2003 or 2014 ISDA Definitions). If applicable."]
      },
      "operational_temporal_scope": {
        "suspected_inception_epoch": "e.g., 'Circa 1997, with the creation of the first off-balance-sheet partnerships'. The estimated period when the practices leading to the collapse began.",
        "precipitating_event_date": "YYYY-MM-DD HH:MM Timezone. e.g., '2008-09-15 01:45 EST, when Lehman filed Chapter 11'. The precise timestamp of the Stage III trigger.",
        "public_disclosure_collapse_date": "YYYY-MM-DD. The date the event became uncontrollably public, e.g., the bankruptcy filing date, the day a regulator shut operations.",
        "operational_duration": "e.g., 'Approximately 11 years (1997-2008)'. The span from suspected inception to public collapse.",
        "key_historical_context_period": "e.g., 'Late-1990s dot-com bubble and deregulatory environment (Gramm-Leach-Bliley Act)', 'Mid-2000s subprime mortgage securitization boom'. The broader market era in which the event incubated."
      },
      "quantitative_scale_impact": {
        "financial_scale_at_collapse": {
          "currency": "e.g., 'USD'",
          "reported_assets_pre_collapse": "e.g., '$639 billion (as per Q2 2008 10-Q filing)'. The last audited or reported balance sheet total assets.",
          "reported_liabilities_at_filing": "e.g., '$768 billion (as per Chapter 11 petition)'. The claimed liabilities at the triggering event.",
          "estimated_investor_losses": "e.g., 'In excess of $65 billion in principal, according to the SIPC trustee's final report'. A credible estimate of total value destroyed for creditors/investors.",
          "peak_market_capitalization": "e.g., '$70 billion in August 2000'. The highest equity value attained, for contrast."
        },
        "stakeholder_impact_metrics": {
          "employee_count_at_collapse": "e.g., '28,600 employees globally, all subject to termination'.",
          "creditor_count_estimate": "e.g., 'Over 100,000 entities filed claims in the bankruptcy proceeding'.",
          "retail_investor_victim_count": "e.g., 'Approximately 37,000 individual investors across 136 countries, per court documents'.",
          "counterparty_exposure_map": "e.g., 'Major exposure held by AIG ($22bn), Citigroup ($18bn), Bank of America ($15bn) – based on OCC derivatives reports'."
        },
        "systemic_risk_indicators": {
          "cds_notional_implicated": "e.g., 'An estimated $400 billion in CDS contracts were triggered, leading to a major settlement auction'.",
          "contagion_events_linked": ["e.g., 'The immediate freezing of the Reserve Primary Money Market Fund (breaking the buck)', 'Intensified pressure on AIG's liquidity', 'Accelerated the passage of TARP'."],
          "broad_market_index_move": "e.g., 'The S&P 500 fell 4.7% on the day of the bankruptcy filing, its largest one-day drop since 2001'."
        }
      },
      "geographic_jurisdictional_reach": {
        "headquarters_jurisdiction": "e.g., 'New York, New York, United States'.",
        "primary_legal_venue": "e.g., 'U.S. Bankruptcy Court for the Southern District of New York (Manhattan)'.",
        "key_offshore_operations_hubs": ["e.g., 'London (UK)', 'Cayman Islands', 'Zurich (Switzerland)'. Jurisdictions used for critical operations or special entities."],
        "primary_markets_affected": ["e.g., 'Global interbank lending markets', 'U.S. commercial paper market', 'European sovereign debt markets'."],
        "multi_regulatory_agencies_involved": ["e.g., 'U.S. Securities and Exchange Commission (SEC)', 'U.K. Financial Conduct Authority (FCA)', 'U.S. Federal Reserve', 'U.S. Department of Justice (DOJ)'."]
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "prevailing_market_ideology_and_beliefs": {
        "dominant_investment_thesis": "e.g., 'The era of the 'Great Moderation' with persistent low volatility and ever-rising asset prices, underpinned by efficient markets and sophisticated risk dispersion through securitization'.",
        "perceived_invulnerability_of_entity": "e.g., 'Lehman was considered a 'too-big-to-fail' bulge bracket investment bank with a storied 158-year history and deep government connections, making its failure unthinkable to most market participants'.",
        "cultural_accepted_practices": "e.g., 'Extensive use of off-balance-sheet Special Purpose Entities (SPEs) to manage earnings and debt ratios was a common, if aggressive, practice endorsed by major accounting firms under prevailing GAAP interpretations'.",
        "trust_in_key_figures": "e.g., 'Bernard Madoff served as NASDAQ chairman and was viewed as a market luminary; his reputation and aura of exclusivity substituted for independent due diligence by sophisticated feeder funds'."
      },
      "formal_governance_and_regulatory_precautions": {
        "applicable_accounting_standards": "e.g., 'FAS 140 (Accounting for Transfers and Servicing of Financial Assets) allowed for Qualified Special Purpose Entities (QSPEs) to be considered separate from the sponsor, provided certain conditions were met'.",
        "primary_regulatory_oversight_body": "e.g., 'The SEC's Consolidated Supervised Entity (CSE) program, a voluntary oversight regime for investment bank holding companies, was the primary regulator for Lehman'.",
        "internal_risk_management_framework_on_books": "e.g., 'The firm's official Value-at-Risk (VaR) models and the Chief Risk Officer (CRO) reported directly to the Board's Risk Committee, presenting a façade of robust control'.",
        "auditor_and_credit_rating_relationships": "e.g., 'Arthur Andersen LLP served as auditor and provided consulting on the SPE structures; credit ratings from Moody's, S&P, and Fitch remained investment-grade (A or better) until weeks before collapse'."
      },
      "entity_specific_public_narrative": {
        "core_business_model_as_described": "e.g., 'Enron portrayed itself as a 'logistics company' for gas and electricity and a pioneer in 'asset-light' trading, moving beyond a traditional pipeline utility'.",
        "key_financial_metrics_emphasized": "e.g., 'Management focused analysts on 'Recurring Net Income' and 'EBITDA', while obfuscating the growth in total debt and cash flow shortfalls from operations'.",
        "strategic_vision_statement": "e.g., 'CEO Dick Fuld's public goal was to make Lehman a 'top-tier' global investment bank, relentlessly pursuing market share in commercial and residential mortgage-backed securities'.",
        "external_perception_in_media": "e.g., 'Fortune magazine named Enron 'America's Most Innovative Company' for six consecutive years (1996-2001), cementing its elite reputation.'"
      }
    },
    "stage_II_-_incubation_period": {
      "accumulating_internal_contradictions": {
        "accounting_red_flags_ignored": "e.g., 'Persistent use of 'Repo 105' transactions in Q4 2007 and Q1 2008, temporarily removing $50+ billion from the balance sheet to lower leverage ratios for reporting dates, described internally as an 'accounting gimmick' in emails'.",
        "whistleblower_actions_and_outcomes": "e.g., 'Vice President Sherron Watkins' 2001 memo to CEO Ken Lay warning that Enron 'could implode in a wave of accounting scandals' was handed to external counsel Vinson & Elkins, which conducted a limited review that did not halt practices'.",
        "internal_control_breaches_documented": "e.g., 'The internal audit function at WorldCom under CEO Bernie Ebbers was stripped of its authority, and the Board's audit committee was intentionally starved of information regarding capital expenditure irregularities'.",
        "deteriorating_core_fundamentals_mask": "e.g., 'While reported profits grew, actual operating cash flow (CFO) turned increasingly negative from 1999-2001, a divergence obscured by complex disclosures and analyst focus on pro-forma metrics'."
      },
      "external_skepticism_and_market_signal_discounting": {
        "short_seller_analysis_publicized": "e.g., 'Hedge fund manager David Einhorn publicly questioned Lehman's valuation of commercial real estate assets and its Repo 105 accounting during the 2008 Ira Sohn Conference, leading to management hostility rather than engagement'.",
        "credit_default_swap_spread_trend": "e.g., 'The 5-year CDS spread for Lehman Brothers widened from under 100 bps in early 2007 to over 400 bps by June 2008, signaling rising counterparty concern well before the rating agencies acted'.",
        "critical_journalistic_investigations": "e.g., 'Forbes journalist Bethany McLean published 'Is Enron Overpriced?' in March 2001, questioning how it earned its profits, which management dismissively attributed to 'complexity' misunderstood by outsiders'.",
        "regulatory_missed_opportunities": "e.g., 'The SEC conducted several examinations of Madoff's brokerage operations but focused on front-running; they never verified his purported trading with the DTCC or options exchanges, which would have revealed the fraud'."
      },
      "cultural_and_psychological_drivers_within_entity": {
        "tone_at_the_top_and_incentive_structure": "e.g., 'An aggressive, bonus-driven culture that rewarded revenue generation without clawbacks for future losses. Risk managers who raised concerns were sidelined or labeled 'non-team players'.'",
        "groupthink_and_information_silos": "e.g., 'The board of directors relied heavily on presentations by CEO Skilling and CFO Fastow, who used technical jargon to confuse them; dissenting views from lower-level executives did not reach the board'.",
        "normalization_of_deviance": "e.g., 'The repeated use of the 'Repo 105' maneuver, though of questionable substance, became a standard quarterly 'tool' for the treasury team, losing its status as an extraordinary red flag'.",
        "strategic_doubling_down": "e.g., 'In 2007, as the subprime market cracked, Lehman doubled down by acquiring Archstone-Smith (a large REIT) and BNC Mortgage, increasing its exposure to the very assets causing stress'."
      }
    },
    "stage_III_-_precipitating_event": {
      "trigger_event_specification": {
        "date_and_time_precision": "e.g., 'Sunday, September 14, 2008, late evening, following the breakdown of rescue talks with Barclays and Bank of America, and the U.S. Treasury's refusal to provide a government guarantee'.",
        "immediate_catalyst": "e.g., 'The release of the Q3 2008 earnings pre-announcement revealing a $3.9 billion loss, a plan to spin off commercial real estate assets, and a credit rating downgrade warning from Moody's, which triggered a fatal loss of counterparty confidence'.",
        "key_decision_makers_actions": "e.g., 'The decision by U.S. Treasury Secretary Hank Paulson and Fed Chairman Ben Bernanke, after viewing Lehman's asset quality, to not utilize public funds for a rescue, effectively pulling the plug on any government-backed solution'.",
        "point_of_no_return_moment": "e.g., 'The moment Lehman's clearing banks ceased accepting intraday credit, paralyzing its ability to settle trades and meet cash obligations, forcing the Board to authorize the Chapter 11 filing'."
      },
      "information_cascade_and_market_reaction": {
        "first_public_announcement": "e.g., 'Press Release from Lehman Brothers Holdings Inc., filed at 1:45 AM EST on September 15, 2008: 'Lehman Brothers Holdings Inc. Announces It Intends to File Chapter 11 Bankruptcy Petition''.",
        "intraday_market_data_spikes": "e.g., 'The VIX volatility index spiked over 25% in pre-market trading; the Eurodollar futures curve inverted sharply, signaling a seizure in short-term dollar funding markets'.",
        "counterparty_panic_sequence": "e.g., 'Prime brokerage clients initiated massive asset transfers; repo lenders refused to roll overnight funding; derivatives counterparties demanded additional collateral calls that could not be met'.",
        "media_frenzy_key_headline": "e.g., 'The New York Times banner headline: 'LEHMAN FILES FOR BANKRUPTCY; MERRILL IS SOLD; AIG SEEKS CASH'; CNBC shifted to 24/7 crisis coverage.'"
      }
    },
    "stage_IV_-_onset": {
      "immediate_operational_collapse": {
        "legal_filing_details": "e.g., 'Chapter 11 petition filed in the Southern District of New York, listing $768 billion in liabilities against $639 billion in assets, the largest bankruptcy in U.S. history at the time'.",
        "employee_lockout_and_asset_freeze": "e.g., 'Global employees were informed via email; offices were secured by security personnel; trading systems were frozen, leaving positions in limbo and clients unable to access accounts'.",
        "regulatory_intervention_actions": "e.g., 'The U.K. FSA placed Lehman Brothers International (Europe) into administration under PricewaterhouseCoopers, triggering a separate, complex insolvency proceeding under U.K. law'."
      },
      "first_order_financial_consequences": {
        "counterparty_loss_realization": "e.g., 'Money market funds, such as the Reserve Primary Fund, holding Lehman commercial paper were forced to write down the value, causing its net asset value to 'break the buck' (fall below $1), triggering a wider run on prime funds'.",
        "fire_sale_dynamics_initiated": "e.g., 'The administrators began the forced liquidation of Lehman's massive portfolio of securities and derivatives, adding downward pressure on already distressed asset prices globally'.",
        "credit_market_seizure_symptoms": "e.g., 'The TED spread (3-month Libor vs. T-bills) widened to a record 450 basis points; the commercial paper market shrank dramatically as trust evaporated'."
      },
      "initial_public_and_political_response": {
        "official_statements_from_authorities": "e.g., 'Federal Reserve statement: 'The Federal Reserve is monitoring market developments closely and will provide liquidity as needed...' but explicitly noting no bailout for Lehman'.",
        "congressional_hearings_announced": "e.g., 'The House Committee on Financial Services immediately scheduled a hearing titled 'The Role of Federal Regulators in the Lehman Brothers Failure' for the following week'.",
        "public_sentiment_and_outrage_focus": "e.g., 'Media and public anger quickly focused on executive compensation paid in prior years, particularly the $484 million in cash bonuses paid to Lehman executives in early 2008, while shareholders were wiped out'."
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "crisis_management_and_triage": {
        "appointment_of_trustee_or_administrator": "e.g., 'The U.S. Bankruptcy Court appointed James W. Giddens as the SIPA Trustee for the liquidation of Lehman's broker-dealer, tasked with maximizing value for customers and creditors'.",
        "first_day_motions_and_emergency_orders": "e.g., 'The court granted debtor-in-possession (DIP) financing facilities, approved critical vendor payments to keep utilities on, and authorized the sale of key North American operations to Barclays within days'.",
        "government_liquidity_facilities_activated": "e.g., 'In response to the broader freeze, the Fed dramatically expanded its lending facilities, creating the Commercial Paper Funding Facility (CPFF) and the Primary Dealer Credit Facility (PDCF)'."
      },
      "asset_disposition_and_claims_process": {
        "major_asset_sales": "e.g., 'Sale of Lehman's flagship NYC headquarters building to Barclays for $1.29 billion; the multi-year process of selling its private equity and real estate portfolios piecemeal'.",
        "claims_reconciliation_scale": "e.g., 'The administration process received over 110,000 proofs of claim totaling approximately $1.2 trillion, requiring years of review, reconciliation, and litigation to adjudicate'.",
        "creditor_committee_formation": "e.g., 'The U.S. Trustee appointed an official committee of unsecured creditors, comprising large banks, hedge funds, and pension funds, to represent creditor interests in the bankruptcy'."
      },
      "initial_regulatory_and_legal_reckoning": {
        "first_major_lawsuits_filed": "e.g., 'The SEC filed a civil fraud lawsuit against Lehman executives, including CEO Richard Fuld, alleging materially misleading accounting disclosures regarding Repo 105'.",
        "congressional_inquiry_findings_released": "e.g., 'The House Oversight Committee released emails showing Lehman executives knew the firm was 'critically undercapitalized' while publicly expressing confidence'.",
        "immediate_regulatory_patch_announcements": "e.g., 'The SEC temporarily banned short selling on financial stocks to stem perceived predatory attacks, a controversial move criticized for impeding price discovery'."
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "official_investigations_and_post_mortems": {
        "definitive_government_commission_report": "e.g., 'The Financial Crisis Inquiry Commission (FCIC) 2011 report identified Lehman's failure as a central cause of the crisis, highlighting its excessive leverage, risky real estate holdings, and reliance on short-term funding'.",
        "bankruptcy_examiner_report_key_findings": "e.g., 'The 2,200-page report by court-appointed examiner Anton R. Valukas concluded Lehman's use of Repo 105 was 'actionable balance sheet manipulation' and that its auditors, Ernst & Young, were 'professionally negligent''.",
        "regulatory_agency_self_assessment": "e.g., 'The SEC's internal report on its oversight of Bear Stearns and Lehman admitted its CSE program was 'fundamentally flawed' and relied too heavily on the firms' own models'."
      },
      "enduring_legal_and_regulatory_reforms": {
        "major_legislation_enacted": "e.g., 'The Dodd-Frank Wall Street Reform and Consumer Protection Act (2010), which created the Orderly Liquidation Authority (OLA), the Volcker Rule, and enhanced derivatives regulation'.",
        "new_accounting_standards": "e.g., 'FAS 166/167 eliminated the QSPE concept, forcing more securitizations back onto balance sheets, and strengthened consolidation rules'.",
        "changes_to_isda_definitions": "e.g., 'The 2014 ISDA Credit Derivatives Definitions were updated to address issues like succession events and the restructuring of government debt, partly in response to sovereign credit events'.",
        "enhanced_prudential_standards": "e.g., 'Basel III's introduction of Liquidity Coverage Ratio (LCR) and Net Stable Funding Ratio (NSFR) to reduce reliance on short-term wholesale funding'."
      },
      "long_term_market_practice_and_cultural_shifts": {
        "changes_in_investor_due_diligence": "e.g., 'Institutional investors now conduct deeper operational due diligence, including on third-party custodians and administrators, moving beyond mere audited financial statements'.",
        "evolution_of_credit_rating_agency_scrutiny": "e.g., 'Regulations mandated increased transparency in rating methodologies, and investors began using CDS spreads as a real-time, market-based alternative to agency ratings'.",
        "shift_in_corporate_governance_norms": "e.g., 'Increased board independence, mandatory risk committee charters for financial firms, and 'clawback' provisions in executive compensation plans became standard'.",
        "narrative_in_academia_and_public_discourse": "e.g., 'The event became a canonical case study in business schools on risk management failure, ethical leadership, and regulatory capture, symbolizing the perils of financialization'."
      },
      "final_resolution_and_legacy": {
        "bankruptcy_plan_effective_date_and_payouts": "e.g., 'Lehman's third amended Chapter 11 plan became effective in March 2012; creditor distributions have occurred over multiple waves, with some creditor classes recovering over 100% on their claims due to interest, while equity holders received nothing'.",
        "final_legal_settlements_totals": "e.g., 'Ernst & Young settled with New York prosecutors for $10 million over its Lehman audit; no top executives faced criminal convictions for the collapse, though several pled guilty to related charges'.",
        "historical_reassessment_and_analogy_use": "e.g., 'The phrase 'a Lehman moment' entered the financial lexicon to describe the uncontrolled collapse of a systemically important institution, invoked during subsequent crises like the Eurozone debt crisis and the Archegos collapse'."
      }
    }
  }
}
"""