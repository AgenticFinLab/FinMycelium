
def leverage_cycle_collapse_prompt() -> str:
    return """
You are a financial historian and systemic risk analyst, specialized in deconstructing and reconstructing complex financial crises, with a focus on leverage cycles and their catastrophic failures.

**Objective:** To reconstruct a comprehensive, deeply detailed, and factually accurate narrative of a specified `leverage_cycle_collapse` event. Your output will serve as a definitive, multi-dimensional case study that captures not only the sequence of events but also the underlying economic, psychological, regulatory, and cultural dynamics at each stage of its lifecycle.

**Output Format:** A single, extensive JSON object. Do not include any explanatory text before or after the JSON.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must have a root key `"leverage_cycle_collapse"`. The primary sub-sections are `"metadata"`, followed by the six lifecycle stages (`stage_I` to `stage_VI`), and finally a `"synthesis_and_analysis"` section.
2.  **Lifecycle Phases:** Populate each of the six stages (`stage_I_-_notionally_normal_starting_point` through `stage_VI_-_full_cultural_readjustment`) according to the "Sequence of Events Associated with a Failure of Foresight" framework. Each stage is a JSON object containing multiple granular fields.
3.  **Granular Fields:** Every field must be populated with highly specific, concrete data. Avoid generalizations. Use precise figures, dates, names of entities and individuals, specific financial instruments, legal citations, and direct quotes where available. If exact data is unavailable from the provided/retrieved information, use qualifiers like "estimated," "reported," or "alleged" and reason logically.
4.  **Integrated Explanation:** For EVERY field within the lifecycle stages and synthesis, you MUST include an `"explanation"` sub-field. This `"explanation"` should directly follow the factual data and elucidate: *Why* this data point is significant, *how* it contributed to the stage's dynamics, what it reveals about market psychology, regulatory gaps, or systemic flaws, and its causal link to subsequent or preceding events. Treat the `"explanation"` as integral to the narrative, not just a note.
5.  **Fact-Based:** Rigorously use only information from the user-provided materials or your retrieved knowledge. Do not invent facts. Distinguish between confirmed facts, widespread reports, and allegations. Adhere to the true, documented history of the event.
6.  **Comprehensiveness:** Aim for exhaustive detail. Consider all angles: macroeconomic context, monetary policy, specific trading strategies (e.g., Total Return Swaps, Repo financing), risk management failures (at the firm, prime broker, and regulator levels), legal and compliance breakdowns, media narrative shifts, political reactions, and long-term impacts on financial theory and practice.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "leverage_cycle_collapse_reconstruction": {
    "metadata": {
      "event_common_name": {
        "value": "e.g., 'The Collapse of Archegos Capital Management'",
        "explanation": "The colloquial, widely recognized name for the event in financial media and discourse."
      },
      "official_legal_case_names": {
        "value": ["e.g., 'SEC v. Sung Kook (Bill) Hwang', 'CFTC v. Archegos Capital Management, LP et al.'"],
        "explanation": "Formal titles of major regulatory or criminal lawsuits filed in the aftermath."
      },
      "primary_entity_and_key_individual": {
        "entity_name": "e.g., 'Archegos Capital Management, LP'",
        "entity_structure": "e.g., 'Family office, formerly a Tiger Cub hedge fund, privately managed for the Hwang family and select employees'",
        "key_individual_name": "e.g., 'Sung Kook (Bill) Hwang'",
        "key_individual_background": "e.g., 'Former equity analyst at Tiger Management, founder of Tiger Asia Management, which pleaded guilty to wire fraud in 2012'",
        "explanation": "Identifies the central failing entity and its principal, detailing their history and structure, which is crucial for understanding the risk culture and regulatory perimeter."
      },
      "key_associated_counterparties_and_victims": {
        "prime_brokers": ["e.g., 'Credit Suisse', 'Nomura Holdings', 'Morgan Stanley', 'Goldman Sachs'"],
        "lenders_other": ["e.g., 'List of banks providing bespoke financing'"],
        "indirectly_affected_parties": ["e.g., 'Shareholders of ViacomCBS, Discovery, etc.', 'Counterparties to the prime brokers'"],
        "explanation": "Enumerates the network of financial institutions entangled through leverage provision (prime brokers) and those harmed by the resulting market dislocations, illustrating the contagion pathway."
      },
      "operational_and_collapse_timeline": {
        "entity_founding_year": "YYYY",
        "strategy_pivot_to_high_leverage_year": "YYYY(-MM)",
        "period_of_rapid_growth": "e.g., 'Q3 2020 - Q1 2021'",
        "precipitating_event_date": "YYYY-MM-DD",
        "margin_calls_commence_date": "YYYY-MM-DD",
        "forced_liquidation_peak_period": "YYYY-MM-DD to YYYY-MM-DD",
        "public_disclosure_date": "YYYY-MM-DD",
        "regulatory_action_announcement_date": "YYYY-MM-DD",
        "explanation": "A chronological anchor detailing the key milestones from inception to implosion and official response, highlighting the acceleration phase and the velocity of collapse."
      },
      "estimated_scale_at_collapse": {
        "gross_exposure": {
          "currency": "USD",
          "amount": "e.g., '~$160 billion'"
        },
        "net_asset_value": {
          "currency": "USD",
          "amount": "e.g., '~$10 billion'"
        },
        "implied_leverage_ratio": "e.g., '> 5x (Gross Exposure/NAV)'",
        "total_losses_to_counterparties": {
          "currency": "USD",
          "amount": "e.g., '> $10 billion'",
          "breakdown_by_counterparty": "e.g., {'Credit Suisse': '$5.5 billion', 'Nomura': '$2.9 billion', ...}"
        },
        "market_capitalization_erosion_in_holdings": {
          "currency": "USD",
          "amount": "e.g., '$35 billion over one week'"
        },
        "explanation": "Quantifies the staggering size of the hidden risk, the extreme leverage employed, and the direct financial damage inflicted on the system, demonstrating the magnitude of the failure."
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "macroeconomic_and_financial_background": {
        "value": "e.g., 'Post-GFC regulatory environment (Dodd-Frank, Volcker Rule), prolonged period of near-zero interest rates, quantitative easing, growth of private markets and family offices, strong bull market in equities, particularly in tech and media sectors.'",
        "explanation": "Describes the accepted financial and regulatory landscape that set the conditions for risk-taking. Low rates pushed yield-seeking, while post-crisis rules ostensibly made banks safer but may have pushed risk to less-regulated areas."
      },
      "cultural_and_psychological_beliefs": {
        "value": "e.g., 'Belief in the 'central bank put', faith in the continuous rise of particular thematic stocks (e.g., 'stay-at-home' stocks during COVID), reverence for concentrated, high-conviction investing modeled after Tiger Management, perception of family offices as sophisticated, low-risk entities requiring minimal oversight.'",
        "explanation": "Captures the prevailing market narratives and assumptions that shaped behavior. These beliefs created blind spots, making the extreme concentration and leverage at Archegos seem less risky to the participants themselves."
      },
      "precautionary_norms_and_regulatory_perimeter": {
        "regulatory_status_of_entity": "e.g., 'Family office exempt from SEC registration under the Investment Advisers Act, thus not required to file Form 13F disclosing holdings.'",
        "standard_risk_management_practices": "e.g., 'Prime brokers typically manage client risk via margin models (VaR, stress tests), concentration limits, and collateral requirements. Use of Total Return Swaps (TRS) was a common practice for synthetic exposure.'",
        "perceived_safeguards": "e.g., 'Diversification across multiple prime brokers was seen as a risk mitigant for both the client and the brokers. Daily margining was standard.'",
        "explanation": "Outlines the formal and informal rules believed to contain risk. Highlights the critical regulatory gap (the family office loophole) and the industry practices that, in this case, failed catastrophically due to coordination breakdowns and information asymmetry."
      },
      "initial_state_of_the_core_entity": {
        "stated_strategy": "e.g., 'Long-biased, concentrated equity investment using leverage, focusing on sectors like media, technology, and Chinese ADRs.'",
        "initial_performance_track_record": "e.g., 'Reported significant returns in 2020, attracting internal confidence and broker willingness to extend leverage.'",
        "governance_structure": "e.g., 'Decision-making highly centralized with Bill Hwang, limited independent risk oversight within the family office.'",
        "explanation": "Establishes the baseline condition of the entity before the cycle accelerated. Shows a pre-existing appetite for risk that was about to be amplified by favorable conditions."
      }
    },
    "stage_II_-_incubation_period": {
      "accumulation_of_unnoticed_anomalies": {
        "increasing_concentration_risk": {
          "value": "e.g., 'By early 2021, Archegos's portfolio was heavily concentrated in a handful of stocks (e.g., ViacomCBS, Discovery, GSX Techedu, Baidu). Its positions represented a significant, often undisclosed, percentage of the float in these companies.'",
          "explanation": "Contradicted the fundamental norm of diversification. This concentration made the portfolio hypersensitive to price moves in a few names and created massive illiquidity risk, which was underestimated or ignored."
        },
        "leverage_escalation_mechanisms": {
          "value": "e.g., 'Use of Total Return Swaps (TRS) with multiple prime brokers to gain enormous synthetic exposure without owning underlying shares, minimizing public disclosure. Brokers competed for business by offering increasingly aggressive margin terms (e.g., lower haircuts, higher concentration limits).'",
          "explanation": "The TRS structure was the key instrument that allowed leverage to explode off-balance-sheet. Broker competition eroded risk discipline, creating a classic 'race to the bottom' in underwriting standards."
        },
        "information_asymmetry_and_regulatory_arbitrage": {
          "value": "e.g., 'No single prime broker had full visibility into Archegos's total exposure across all counterparties. The lack of 13F filings meant the market and regulators were unaware of the massive concentrated bets.'",
          "explanation": "The systemic flaw: risk was fragmented and hidden. Each broker saw only their slice, missing the whole picture. The regulatory exemption prevented the normal disclosure that would have alerted the market."
        },
        "deterioration_of_risk_metrics_and_warning_signs": {
          "value": "e.g., 'Internal risk models at prime brokers may have been gamed or failed to capture tail risk of such concentrated, levered positions. Potential over-reliance on daily mark-to-market margining, which works until it doesn't during a liquidity crisis.'",
          "explanation": "The quantitative and qualitative safeguards were becoming less effective. Models based on historical volatility were blind to the novel, systemic risk being created. The margin system assumed continuous liquidity."
        }
      },
      "psychological_and_organizational_drift": {
        "normalization_of_deviance": {
          "value": "e.g., 'Continuous profitability and successful navigation of prior small drawdowns reinforced the belief that the strategy was sound and that brokers would always support them. Limits were consistently raised, becoming the new normal.'",
          "explanation": "Success bred complacency and reinforced risky behavior, a common trait in financial blow-ups. Past success was misinterpreted as evidence of skill and low risk, rather than luck and beta exposure."
        },
        "intra_broker_competition_and_siloing": {
          "value": "e.g., 'Prime broker divisions operated as profit centers, incentivized to win lucrative financing business from large clients like Archegos. Communication between credit risk teams and equities divisions, or between different brokers, was minimal or non-existent.'",
          "explanation": "Internal and external competition overrode collective risk management. The profit motive directly conflicted with the prudence motive, and organizational silos prevented a holistic view of the danger."
        }
      }
    },
    "stage_III_-_precipitating_event": {
      "triggering_shock": {
        "nature_of_event": "e.g., 'A planned secondary offering by ViacomCBS, a core Archegos holding, announced on March 22, 2021.'",
        "immediate_market_reaction": "e.g., 'The stock price of ViacomCBS fell sharply (~9% on March 23) on the news, contrary to the expectation that such offerings are often neutral or positive for well-received companies.'",
        "explanation": "The event was not extraordinarily rare, but it acted on the system's critical vulnerability—concentration. It revealed that the market could not absorb selling pressure related to Archegos's hidden holdings, triggering a loss of confidence."
      },
      "transformation_of_perception": {
        "value": "e.g., 'The price drop in ViacomCBS and other concentrated holdings immediately impacted the value of the collateral securing the TRS positions. Prime brokers' risk systems began generating large margin calls simultaneously.'",
        "explanation": "The initial shock rapidly translated into a mechanical financial crisis. The hidden, interconnected web of leverage was suddenly illuminated for the prime brokers as their collateral buffers evaporated. The period of incubation was over; the crisis was now active."
      },
      "first_movers_and_coordination_attempts": {
        "value": "e.g., 'One or more prime brokers (reportedly Goldman Sachs and Morgan Stanley) quickly calculated their exposure and the systemic risk, deciding to quietly begin liquidating their swap positions in block trades on March 24-26, 2021, before others.'",
        "explanation": "Illustrates the classic 'run' dynamic. Once the risk was recognized, the incentive was to be first to exit, maximizing recovery for oneself but guaranteeing greater losses for slower counterparts and ensuring a fire sale."
      }
    },
    "stage_IV_-_onset": {
      "cascade_of_margin_calls_and_forced_liquidation": {
        "mechanics_of_unwind": {
          "value": "e.g., 'As prime brokers liquidated billions in blocks, it further depressed the prices of the underlying stocks (ViacomCBS, Discovery, etc.), triggering additional margin shortfalls at other brokers, who then were forced to sell, creating a vicious feedback loop.'",
          "explanation": "Describes the destructive, self-reinforcing mechanism of the leverage cycle collapse. Falling prices beget forced selling, which begets lower prices. The system's design amplified the initial shock."
        },
        "market_impact_data": {
          "value": "e.g., 'ViacomCBS stock fell ~55% in one week. Discovery fell ~45%. Billions in market capitalization were wiped out. The block trades were visibly abnormal, alerting the wider market to a major distressed seller.'",
          "explanation": "Quantifies the immediate, violent market consequence. The scale of selling overwhelmed normal liquidity, confirming the existence of a 'hidden whale' and spreading contagion fear."
        }
      },
      "immediate_consequences_for_core_entity": {
        "value": "e.g., 'Archegos's net capital was completely obliterated by the losses. All positions were liquidated by its prime brokers. The family office ceased to function as a going concern, facing total ruin.'",
        "explanation": "The endpoint for the leveraged entity: total equity wipeout. Demonstrates the asymmetric payoff of extreme leverage—massive gains in the up-cycle, complete annihilation in the down-cycle."
      },
      "counterparty_losses_realization": {
        "value": "e.g., 'Credit Suisse announced a $5.5 billion loss, leading to executive ousters, strategic reviews, and credit rating downgrades. Nomura announced a $2.9 billion loss. Other banks reported smaller losses or managed to exit with minimal damage.'",
          "explanation": "The losses crystallized across the financial network, revealing the distribution of pain. The variance in outcomes highlighted differences in risk management speed and effectiveness among the prime brokers."
      },
      "public_and_media_disclosure": {
        "value": "e.g., 'Financial media broke the story on March 26, 2021, identifying Archegos as the source of the violent moves. The scale of the hidden leverage shocked the market and regulators.'",
        "explanation": "The transition from a private financial crisis to a public scandal. Media scrutiny intensified pressure on regulators and involved institutions to respond."
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "immediate_containment_actions": {
        "regulatory_mobilization": {
          "value": "e.g., 'The SEC, CFTC, and FINRA swiftly launched investigations. The SEC Chairman called the event a 'teaching moment' and highlighted the need for greater transparency.'",
          "explanation": "The first-stage official response: investigative and rhetorical. Aimed at reassuring markets and beginning the process of assigning blame and understanding the failure."
        },
        "internal_crisis_response_at_affected_banks": {
          "value": "e.g., 'Credit Suisse launched an internal investigation by a board committee, fired key executives (Head of Investment Banking, Chief Risk Officer), suspended bonuses, and pledged to overhaul its prime brokerage risk controls.'",
          "explanation": "Demonstrates the immediate, ad-hoc organizational triage within the most affected institutions. Focus is on stabilizing the firm, managing reputational damage, and showing accountability."
        },
        "legal_filings_and_asset_preservation": {
          "value": "e.g., 'Regulators filed charges against Archegos and Bill Hwang for market manipulation and fraud. Efforts began to trace and secure any remaining assets for potential restitution.'",
          "explanation": "The initiation of the formal legal process to assign culpability and attempt to recover funds for victims, though often recovery is a fraction of losses."
        }
      },
      "market_stabilization_measures": {
        "value": "e.g., 'No government bailout was required. The broader financial system absorbed the shock without triggering a systemic crisis, partly because the losses were contained within the equity market and specific banks.'",
        "explanation": "Highlights that while the event was catastrophic for the direct participants, the firebreaks in the post-2008 system (higher bank capital) prevented a full-blown systemic meltdown, making this a 'salvage' operation rather than a 'rescue' of the system."
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "official_investigations_and_reports": {
        "value": "e.g., 'The SEC released a detailed report on the Archegos collapse in October 2021, criticizing the prime brokers' risk management. Credit Suisse's internal 'Williams Report' detailed a 'fundamental failure of management and control'.'",
        "explanation": "The formal inquiry phase, producing authoritative narratives that dissect the root causes. These reports become the foundational documents for new norms and rules."
      },
      "regulatory_and_policy_reforms": {
        "proposed_or_enacted_changes": {
          "value": "e.g., 'SEC proposed rules to increase transparency for large security-based swap positions, potentially closing the family office loophole. Enhanced reporting of large positions (Form 13H-like for swaps) discussed. Basel Committee scrutiny of banks' counterparty risk management for non-bank entities.'",
          "explanation": "The concrete output of the readjustment: attempts to rewrite the precautionary norms (laws, codes of practice) to prevent an identical recurrence. Focuses on transparency, leverage monitoring, and counterparty risk."
        },
        "explanation": "Outlines how the understanding gained from the collapse is codified into new rules and supervisory practices, aiming to harden the financial system against similar future events."
      },
      "industry_practice_evolution": {
        "value": "e.g., 'Prime brokers globally reviewed their exposure to family offices and highly levered clients. Stricter concentration limits, more conservative margin models for swap books, enhanced cross-broker communication protocols (within legal limits), and deeper due diligence on client backgrounds became more common.'",
        "explanation": "Describes the informal, market-driven changes in behavior. The 'soft' cultural readjustment within firms, where risk aversion increases and certain client behaviors become red flags."
      },
      "long_term_impact_on_financial_theory_and_discourse": {
        "value": "e.g., 'Renewed focus on the systemic risks posed by the non-bank financial intermediation (NBFI) sector, particularly levered hedge funds and family offices. Debates on the adequacy of swap disclosure rules and the 'too interconnected to fail' dilemma for large, opaque market players.'",
        "explanation": "The deepest level of readjustment: how the event changes the conceptual framework of regulators, academics, and practitioners. It becomes a canonical case study in risk management failure, leverage cycles, and regulatory perimeter issues."
      }
    },
    "synthesis_and_analysis": {
      "key_mechanisms_of_failure": {
        "value": ["e.g., 'Opacity via TRS and regulatory exemption', 'Fragmented risk perception across competing prime brokers', 'Pro-cyclicality of margin lending', 'Failure of internal risk models to capture concentration and liquidity risk', 'Cultural normalization of extreme leverage in a low-rate environment.'"],
        "explanation": "Synthesizes the primary causal factors from across the stages into a concise list of failure modes."
      },
      "analogy_to_prior_events": {
        "value": "e.g., 'Similar to Long-Term Capital Management (1998) in its use of high leverage and reliance on models that failed in a crisis, and similar to the 2008 crisis in its use of opaque derivatives and counterparty risk, but distinct in its centering on a single family office and equity swaps.'",
        "explanation": "Places the event within the historical continuum of financial crises, highlighting recurring themes and unique aspects."
      },
      "hypothetical_counterfactuals": {
        "value": "e.g., 'Had a single prime broker had full visibility into the total exposure, they likely would have drastically reduced limits. Had Form 13F filing been required, the market price of the concentrated stocks might have adjusted earlier, limiting the buildup. Had broker risk teams been less siloed from revenue generators, earlier intervention might have occurred.'",
        "explanation": "Explores what could have broken the chain of causation, illuminating the critical junctures where different decisions or rules might have averted the collapse."
      }
    }
  }
}
"""