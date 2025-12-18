
def stablecoin_depeg_prompt() -> str:
    return """
You are a forensic financial historian and a systemic risk analyst specializing in cryptocurrency and decentralized finance.

**Objective:** To reconstruct a comprehensive, granular, and deeply analytical narrative of a specified stablecoin depeg event. Your output must function as a standalone, definitive case study that captures the event's full technical, economic, social, and regulatory lifecycle, akin to a meticulously detailed documentary film script backed by raw data.

**Output Format:** A single, extensive JSON object. Do not include any commentary, introductions, or conclusions outside this JSON.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must have a root key `"stablecoin_depeg"`. All data must be nested within this object, organized primarily by the six-stage lifecycle model of failure (Stages I-VI) and supplemented by comprehensive metadata and post-mortem analysis.
2.  **Lifecycle Phases:** Populate each stage (`stage_I_-_notionally_normal_starting_point` through `stage_VI_-_full_cultural_readjustment`) as a distinct object. Each stage must contain multiple, deeply nested objects and arrays that break down the events, conditions, actors, and perceptions specific to that phase. Treat each stage as a chapter in the story.
3.  **Granular Fields:** For every field, provide exceptionally detailed and specific information. Avoid summaries. Use precise dates, amounts, on-chain addresses, transaction hashes, wallet identifiers, code functions, protocol names, URLs to key social media posts or articles, price levels, and direct quotes where crucial. Quantify everything possible.
4.  **Integrated Explanation:** For *every* field in the JSON, from the root to the deepest nested key, you must include an `"explanation"` sub-field. The value of this `"explanation"` must directly and clearly state *why* this data point is significant to understanding the depeg event. Do not just restate the fact; explain its role, cause, or consequence. Treat this as inline commentary from an expert narrator.
5.  **Fact-Based:** All information must be derived from the provided user data or from verifiable, timestamped sources obtained via internet retrieval (e.g., blockchain explorers, archived social media, official announcements, court filings, reputable news reports with dates). Clearly distinguish between confirmed facts and widespread public perception at the time. If data is contested, note the different viewpoints.
6.  **Comprehensiveness:** Strive to create the most complete record possible. Consider these dimensions for each stage: **Technical** (smart contract logic, oracle mechanisms, liquidity pool dynamics, blockchain congestion), **Financial** (yields, volumes, collateral ratios, arbitrage flows, whale wallets), **Governance** (DAO votes, proposal details, key community figures), **Narrative & Sentiment** (key influencer statements, media headlines, community chat logs), **Regulatory & Legal** (warnings issued, investigations launched, lawsuits filed), and **Market-Wide Impact** (contagion to other protocols, funding rate shifts, volatility indices).

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "stablecoin_depeg_reconstruction": {
    "metadata": {
      "scheme_common_name": {
        "value": "e.g., 'The TerraUSD (UST) Depeg Collapse of May 2022'",
        "explanation": "The colloquial, widely recognized name for the event, essential for quick identification and historical referencing within the crypto community and broader public discourse."
      },
      "official_legal_case_name": {
        "value": "e.g., 'Securities and Exchange Commission v. Terraform Labs Pte. Ltd. and Do Kwon'",
        "explanation": "The formal title of the leading regulatory or civil lawsuit arising from the event, indicating the transition from market failure to legal accountability."
      },
      "primary_architect_name": {
        "value": "e.g., 'Do Kwon (Kwon Do-hyeong)'",
        "explanation": "The individual(s) most associated with the design, promotion, and leadership of the stablecoin protocol, central to the narrative of responsibility and intent."
      },
      "key_associated_entities": {
        "value": ["Terraform Labs", "The Luna Foundation Guard (LFG)", "Anchor Protocol", "Chai Corporation"],
        "explanation": "List of legal entities, foundations, and key protocols integral to the ecosystem's operation, funding, and marketing. Identifies the organizational structure behind the stablecoin."
      },
      "operational_timeframe": {
        "suspected_inception": {
          "value": "2018-01",
          "explanation": "The month/year the protocol's development or conceptual whitepaper was first announced, marking the beginning of its lifecycle."
        },
        "mainnet_launch": {
          "value": "2020-04",
          "explanation": "The date the stablecoin protocol went live on the blockchain, enabling public use and marking the start of its economic activity."
        },
        "depeg_onset_datetime_utc": {
          "value": "2022-05-08T 06:00:00Z",
          "explanation": "The precise timestamp (UTC) when the stablecoin's market price first deviated significantly (e.g., >2%) from its peg and did not recover, marking the technical start of the crisis."
        },
        "public_collapse_declaration_datetime_utc": {
          "value": "2022-05-12T 14:00:00Z",
          "explanation": "The timestamp of the official announcement (e.g., tweet, blog post) from the core team acknowledging the protocol's failure or halting operations, marking the formal end."
        },
        "duration_to_collapse": {
          "value": "25 months",
          "explanation": "The time from mainnet launch to public collapse declaration, indicating the lifespan of the 'functioning' system."
        }
      },
      "estimated_global_scale": {
        "currency": {
          "value": "USD",
          "explanation": "The fiat currency used as the benchmark for loss valuations, providing a universal measure of scale."
        },
        "market_cap_at_peak": {
          "value": "18.7 billion",
          "explanation": "The total market capitalization of the stablecoin at its highest point before depeg, indicating the maximum size of the trust-based system."
        },
        "market_cap_at_collapse": {
          "value": "0.3 billion",
          "explanation": "The market capitalization immediately after the collapse declaration, quantifying the near-total destruction of value."
        },
        "total_value_locked_peak": {
          "value": "30.1 billion",
          "explanation": "The peak aggregate value locked across all associated protocols (e.g., Anchor, Lido), showing the ecosystem's overall financial footprint."
        },
        "estimated_investor_loss_range": {
          "value": "40-50 billion",
          "explanation": "A credible estimated range of total financial losses incurred by all parties, including downstream effects, quantifying the economic damage."
        },
        "direct_holder_count_estimate": {
          "value": "~4.5 million",
          "explanation": "The approximate number of unique blockchain addresses holding the stablecoin or its governance token near the peak, indicating the breadth of direct exposure."
        },
        "geographic_reach_high_impact": {
          "value": ["South Korea", "United States", "Southeast Asia", "Europe"],
          "explanation": "List of countries/regions with the highest concentration of retail and institutional investors, highlighting the global yet uneven distribution of impact."
        }
      },
      "stablecoin_technical_specifications": {
        "stablecoin_ticker": {
          "value": "UST",
          "explanation": "The trading ticker symbol of the depegged stablecoin, a primary identifier."
        },
        "governance_token_ticker": {
          "value": "LUNA",
          "explanation": "The ticker of the native, volatile token used in the stabilization mechanism, central to understanding the death spiral dynamics."
        },
        "peg_target": {
          "value": "1.00 USD",
          "explanation": "The intended fiat currency value the stablecoin was designed to maintain, defining the 'peg'."
        },
        "stabilization_mechanism_category": {
          "value": "Algorithmic (Seigniorage/Shares Model)",
          "explanation": "Classification of the core method for maintaining the peg (e.g., Algorithmic, Crypto-Collateralized, Fiat-Backed). UST's model is fundamental to its failure mode."
        },
        "primary_blockchain": {
          "value": "Terra (Cosmos SDK)",
          "explanation": "The native blockchain on which the stablecoin was issued and primarily operated, relevant for transaction speed, cost, and ecosystem dependencies."
        },
        "key_smart_contract_addresses": {
          "mint_burn_contract": {
            "value": "terra1...abc",
            "explanation": "The on-chain address of the contract governing the UST<->LUNA mint/burn process. Essential for tracing the core stabilization actions."
          },
          "community_pool": {
            "value": "terra1...def",
            "explanation": "Address of the DAO treasury or community pool, showing reserves used for last-ditch defense efforts."
          }
        },
        "primary_yield_generation_protocol": {
          "name": {
            "value": "Anchor Protocol",
            "explanation": "The flagship lending/borrowing protocol that offered a ~20% APY on UST deposits, identified as the primary driver of demand and the critical vulnerability."
          },
          "sustained_deposit_apy": {
            "value": "19.5%",
            "explanation": "The consistently advertised yield rate, which was economically unsustainable and created a Ponzi-like dependency on new capital inflows."
          }
        }
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "dominant_industry_narratives": {
        "value": ["'Algorithmic stablecoins are the future of decentralized money'", "'DeFi can offer superior, sustainable yields through innovation'", "'The Terra ecosystem is creating a parallel financial system'"],
        "explanation": "The widely accepted and promoted beliefs within the crypto community that provided the cultural and ideological foundation for the project's growth and acceptance, masking underlying risks."
      },
      "precautionary_norms_and_guardrails": {
        "formal_regulatory_stance": {
          "value": ["SEC Chair Gary Gensler's 2021-2022 repeated warnings about 'stablecoins and crypto lending platforms' falling under securities laws", "South Korean FSC increasing scrutiny on crypto exchanges in 2021"],
          "explanation": "Official regulatory statements and actions that existed prior to the collapse, which were largely ignored or dismissed by the ecosystem, representing the formal 'rules' being bypassed."
        },
        "internal_risk_mitigations": {
          "value": ["Luna Foundation Guard (LFG) creation and Bitcoin reserve accumulation plan announced in Q1 2022", "'Emergency OTC sale' function in the Anchor Protocol code"],
          "explanation": "Measures implemented or proposed by the project team itself to address perceived risks, illustrating their awareness of fragility and the specific safeguards they trusted."
        },
        "community_and_expert_warnings": {
          "value": ["Economist Frances Coppola's 2021 blog posts critiquing the sustainability of Anchor's yield", "On-chain analyst @FatManTerra's threads on Twitter highlighting wallet concentration and risks"],
          "explanation": "Public critiques and warnings from independent analysts and experts that were circulating during the 'normal' period but did not alter mainstream investor behavior, representing ignored foresight."
        }
      },
      "perceived_strengths_and_growth_indicators": {
        "ecosystem_expansion": {
          "value": ["Integration with Ethereum via Wormhole bridge (Oct 2021)", "Partnership with Korean payment platform CHAI", "Columbus-5 mainnet upgrade (Sep 2021)"],
          "explanation": "Key technical and commercial milestones that were hailed as successes, fueling positive sentiment and the perception of inevitable growth."
        },
        "institutional_and_retail_adoption_metrics": {
          "value": ["Anchor Protocol TVL grew from $200M to $14B in 12 months", "Over 70 projects building on Terra by end of 2021", "UST used as collateral on major DeFi protocols like Abracadabra"],
          "explanation": "Quantitative metrics of adoption and usage that were cited as proof of product-market fit and network strength, creating a facade of health."
        },
        "social_and_cultural_phenomena": {
          "value": ["Aggressive 'Lunatic' community branding on Twitter", "Do Kwon's confrontational 'governments can't stop us' public persona", "#LUNAtics hashtag trend"],
          "explanation": "The social dynamics, community culture, and leadership personality that fostered extreme loyalty, suppressed dissent, and created a powerful marketing engine."
        }
      }
    },
    "stage_II_-_incubation_period": {
      "accumulating_systemic_stresses": {
        "anchor_protocol_sustainability_warnings": {
          "value": ["The 'Anchor Yield Reserve' dwindled from ~$70M to near-zero between Jan-Apr 2022, requiring repeated capital injections from LFG", "Net borrow demand on Anchor remained flat while deposits soared, creating a negative carry"],
          "explanation": "Clear, on-chain evidence that the core yield engine was fundamentally unsustainable and operating on subsidized capital, a critical internal contradiction."
        },
        "macro_financial_pressure": {
          "value": ["The U.S. Federal Reserve began signaling aggressive interest rate hikes in late 2021, leading to a bear market in crypto (BTC fell from $69K to ~$35K by May 2022)", "Risk-off sentiment across all speculative assets"],
          "explanation": "The broader macroeconomic shift that drained liquidity from the crypto ecosystem, exposing projects reliant on constant new capital inflows."
        },
        "liquidity_fragmentation_and_whale_concentration": {
          "value": ["A significant portion of UST liquidity was in the shallow Curve Finance 3pool on Ethereum, not on Terra", "On-chain data showed a handful of wallets controlled a large percentage of Anchor deposits"],
          "explanation": "Structural vulnerabilities in the liquidity landscape and high dependency on a small number of large actors, making the system prone to coordinated attacks or panics."
        }
      },
      "early_warning_signals_ignored_or_rationalized": {
        "minor_depeg_events": {
          "value": ["UST depegged to $0.985 on 2021-05-23 during a broader market crash, recovering via arbitrage within hours", "A $150M UST withdrawal from Anchor on 2022-04-30 caused a brief price dip"],
          "explanation": "Previous, smaller instances of peg stress that were successfully defended, creating a dangerous precedent of 'it always recovers' and masking the growing structural weakness."
        },
        "governance_proposals_failing_to_address_core_issues": {
          "value": ["Anchor Protocol DAO Proposal #20 to dynamically adjust rates was debated for months but not implemented in time"],
          "explanation": "Examples of the governance process being too slow or unwilling to implement necessary but painful fixes (like reducing yields), demonstrating institutional inertia."
        },
        "competitive_and_regulatory_pressures": {
          "value": ["The launch of competitive, regulated USD yield products (e.g., U.S. Treasury yields rising)", "SEC subpoenas served to Terraform Labs personnel in late 2021"],
          "explanation": "External pressures that were eroding the project's value proposition and increasing operational risk, yet were not factored into the dominant growth narrative."
        }
      },
      "risk_obfuscation_and_narrative_management": {
        "key_communications_from_core_team": {
          "value": ["Do Kwon tweet on 2022-03-14: 'I'm not selling a single LUNA until BTC hits 1M and UST is the dominant stablecoin'", "LFG announcements about aggressive Bitcoin accumulation as a 'war chest'"],
          "explanation": "Public statements from leadership that aimed to bolster confidence, divert attention from core issues, or frame risks as strengths, effectively managing market perception downward."
        },
        "community_discourse_analysis": {
          "value": ["Critics on Terra research forums were often dismissed as 'FUD spreaders' or banned from community channels", "Celebrity endorsements (e.g., from certain YouTubers) continued unabated"],
          "explanation": "Evidence of an echo chamber effect where dissenting information was suppressed and promotional content amplified, preventing a realistic risk assessment from permeating the community."
        }
      }
    },
    "stage_III_-_precipitating_event": {
      "trigger_sequence_timeline": {
        "initial_capital_movement": {
          "timestamp_utc": {
            "value": "2022-05-07T 18:00:00Z",
            "explanation": "The precise start of the coordinated or consequential capital movement that began the unstoppable chain reaction."
          },
          "action": {
            "value": "A wallet (0x8f...), believed to be associated with a large fund, removed ~$150M worth of UST liquidity from the Curve Finance 3pool over several hours.",
            "explanation": "The specific on-chain action that destabilized the primary liquidity pool for UST on Ethereum, creating immediate slippage and arbitrage pressure."
          },
          "tx_hash_initial": {
            "value": "0x123...abc",
            "explanation": "The blockchain transaction ID of the first major withdrawal, a verifiable data point marking the start of the attack/panic."
          }
        },
        "arbitrage_attack_amplification": {
          "timestamp_utc": {
            "value": "2022-05-07T 21:00:00Z onwards",
            "explanation": "The period when market actors began exploiting the growing peg deviation through the protocol's own mint/burn mechanism, accelerating the crisis."
          },
          "mechanism_exploitation": {
            "value": "Arbitrageurs sold UST at a discount (~$0.98) on exchanges, used the proceeds to buy $1 worth of LUNA via the Terra protocol's burn/mint, and sold LUNA on the open market for profit. This increased UST supply and LUNA sell pressure.",
            "explanation": "The exact feedback loop inherent in the algorithmic design that turned a loss of peg into a self-reinforcing death spiral. This is the core technical failure in action."
          }
        },
        "retail_panic_and_social_media_frenzy": {
          "timestamp_utc": {
            "value": "2022-05-08T 06:00:00Z onwards",
            "explanation": "The point when the deviation became severe enough (>3%) to trigger mass awareness and panic among retail holders, shifting the dynamic from an arbitrage opportunity to a bank run."
          },
          "key_social_catalyst": {
            "value": "Screenshots of failed Anchor withdrawals and rapidly declining UST prices flooded Twitter and Telegram. The phrase 'bank run' began trending.",
            "explanation": "The social media phenomenon that converted a technical market event into a widespread psychological panic, ensuring a mass, coordinated rush for the exits."
          }
        }
      },
      "defensive_actions_and_their_inefficacy": {
        "lfg_bitcoin_reserve_deployment": {
          "value": ["LFG began selling its Bitcoin reserves (~$3B worth) on May 9-10 to buy UST in a bid to restore the peg", "These massive sells contributed to a broader crypto market crash"],
          "explanation": "The primary, pre-planned defense mechanism being executed. Its failure to hold the peg demonstrated that the sell pressure far exceeded the designed capacity of the 'war chest'."
        },
        "protocol_parameter_changes": {
          "value": "Terra validators passed governance proposal #1623 on May 9, increasing the base pool for UST minting from $50M to $100M to slow LUNA minting.",
          "explanation": "A desperate, ad-hoc change to the core protocol parameters mid-crisis, which failed to address the fundamental incentive mismatch and was perceived as a sign of weakness."
        },
        "exchange_interventions": {
          "value": "Binance temporarily suspended LUNA and UST withdrawals on May 10 due to 'network congestion'.",
          "explanation": "Actions by centralized exchanges that, while perhaps technically necessary, exacerbated panic by trapping user funds and eliminating a potential off-ramp for some."
        }
      },
      "point_of_no_return_identification": {
        "technical_moment": {
          "value": "When the daily minting of new LUNA (to absorb burned UST) exceeded the total circulating supply by orders of magnitude, hyperinflating the token to near-zero value around May 12.",
          "explanation": "The specific technical state where the algorithmic stabilization mechanism became mathematically absurd and irreversible, destroying any remaining collateral value in LUNA."
        },
        "market_sentiment_moment": {
          "value": "The price of LUNA fell below $0.10 on May 11, destroying the collateral narrative and any remaining belief from large holders that the system could recover.",
          "explanation": "The psychological threshold where even the most committed supporters recognized total failure, leading to a complete abandonment of the ecosystem."
        }
      }
    },
    "stage_IV_-_onset": {
      "immediate_consequences": {
        "price_trajectory": {
          "ust_price_low": {
            "value": "$0.02 on 2022-05-13",
            "explanation": "The effective floor price UST reached, demonstrating a near-total loss of peg and trust."
          },
          "luna_price_low": {
            "value": "$0.000000999967 on 2022-05-13 (effectively zero)",
            "explanation": "The hyper-inflated, near-zero price of the governance token, quantifying the complete destruction of the seigniorage share component."
          }
        },
        "protocol_and_chain_failure": {
          "terra_blockchain_halt": {
            "value": "The Terra blockchain was officially halted at block height 7603700 on 2022-05-12 by validator consensus.",
            "explanation": "The ultimate failure of the underlying network, a drastic measure taken to stop the hyperinflation and assess damage, equivalent to a total system shutdown."
          },
          "anchor_protocol_freezing": {
            "value": "Anchor Protocol effectively became insolvent and frozen, with all borrow positions liquidated and deposits trapped.",
            "explanation": "The collapse of the flagship application, where the promised yields vaporized and user capital was locked or lost."
          }
        },
        "direct_financial_carnage": {
          "top_tier_investor_losses": {
            "value": ["Three Arrows Capital (3AC) reported a ~$200M loss on its LUNA position", "Jump Crypto and Galaxy Digital suffered nine-figure losses"],
            "explanation": "Documented losses from sophisticated institutional investors, highlighting that the damage was not limited to retail participants."
          },
          "retail_investor_stories": {
            "value": ["Widespread reports on social media of individuals losing life savings, college funds, and retirement accounts invested in UST via Anchor"],
            "explanation": "The human cost of the collapse, critical for understanding its societal impact and the breach of trust."
          }
        }
      },
      "contagion_and_market_wide_impact": {
        "crypto_market_capitalization_drop": {
          "value": "The total crypto market cap fell from ~$1.7T on May 5 to ~$1.2T on May 12, a ~30% drop partly triggered by the Terra collapse.",
          "explanation": "Quantifying the systemic impact, showing how the failure of one major protocol precipitated a broader market crisis."
        },
        "counterparty_crisis": {
          "value": ["Celsius Network cited 'extreme market conditions' as it halted withdrawals on June 13, 2022, a direct chain of contagion", "The hedge fund Three Arrows Capital (3AC) was vaporized, leading to defaults on loans from Voyager Digital and others"],
          "explanation": "The cascading failure of other crypto lenders, funds, and service providers that were overexposed to Terra/LUNA or caught in the resulting liquidity crunch, illustrating networked risk."
        },
        "stablecoin_scrutiny_and_fud": {
          "value": ["The price of the largest algorithmic competitor, DAI, experienced minor depeg pressure", "Tether (USDT) briefly depegged to $0.95 on May 12 on extreme market fear"],
          "explanation": "The spillover of fear and loss of confidence to other stablecoin projects, even those with different models, showing a crisis of faith in the entire category."
        }
      },
      "initial_public_and_regulatory_reaction": {
        "immediate_regulatory_statements": {
          "value": ["U.S. Treasury Secretary Janet Yellen mentioned the UST depeg in a congressional hearing on May 10, urging for stablecoin regulation 'by the end of the year'", "South Korean authorities launched an emergency meeting and investigation into Terraform Labs on May 11"],
          "explanation": "The first, rapid responses from government officials and agencies, signaling that the event had immediately escalated to the highest levels of regulatory concern."
        },
        "mainstream_media_narrative_framing": {
          "value": "Headlines such as 'The Crypto equivalent of a bank run' (Financial Times, May 10) and 'A $60 Billion Crypto Collapse Reveals the Fraud at the Heart of the System' (New York Magazine, May 13) dominated.",
          "explanation": "How the event was framed for the general public, shaping the external perception of the entire crypto industry and cementing its reputation as risky and fraudulent for many."
        }
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "immediate_post_collapse_adjustments": {
        "terra_blockchain_fork_proposal": {
          "proposal_name": {
            "value": "Terra Ecosystem Revival Plan 2",
            "explanation": "The formal name of the plan to create a new blockchain without the failed algorithmic stablecoin, marking the first step towards salvaging value."
          },
          "core_mechanism": {
            "value": "Airdrop of new 'LUNA' (later renamed 'LUNC') tokens to holders of the old LUNA and UST at a snapshot, with a specific distribution curve penalizing large holders and UST holders.",
            "explanation": "The contentious method for distributing ownership of the new chain, which was a critical political and economic decision determining who would bear the losses."
          },
          "governance_vote_outcome": {
            "value": "Passed on May 25, 2022, with 65.5% of the (remaining) validator votes.",
            "explanation": "Demonstrating that a core group of validators and stakeholders chose to attempt a revival, despite many retail holders feeling the plan was unfair."
          }
        },
        "legal_maneuvers_and_entity_dissolutions": {
          "value": ["Terraform Labs dissolved its South Korean entity in May 2022", "Key developers and Do Kwon relocated to Singapore and later Serbia"],
          "explanation": "The immediate actions taken by the founding team to limit legal liability and reorganize, indicating a shift from operational to survival mode."
        },
        "community-led_salvage_efforts": {
          "value": ["The 'LUNC Classic' community formed around the original chain (renamed Terra Classic), proposing burning mechanisms to reduce supply", "Independent developers created tools to help users claim their new chain airdrops"],
          "explanation": "Grassroots efforts by remaining community members to find value in the wreckage, illustrating the decentralized and fragmented nature of the salvage phase."
        }
      },
      "victim_compensation_attempts": {
        "lfg_remaining_asset_distribution": {
          "value": "The Luna Foundation Guard controlled ~$100M in assets after its Bitcoin sales. Its distribution plan became a subject of legal disputes and delays.",
          "explanation": "The process (or lack thereof) for using the remaining project treasury to compensate victims, a key metric of accountability and justice."
        },
        "legal_fundraisers_and_activism": {
          "value": "Korean victims formed organized groups to fund class-action lawsuits and pressure lawmakers.",
          "explanation": "Collective action by victims to seek redress outside of the failed protocol's mechanisms, moving the salvage effort into the legal arena."
        }
      },
      "market_stabilization_actions": {
        "exchange_delistings_and_handling": {
          "value": ["Binance delisted UST and suspended spot trading for LUNA on May 13", "Most major exchanges followed suit or severely restricted trading"],
          "explanation": "Actions by centralized gatekeepers to contain the damage and protect their users (and themselves), effectively quarantining the toxic assets."
        },
        "de_protocol_risk_reassessment": {
          "value": "Major DeFi protocols like Aave and Compound immediately passed governance proposals to disable UST as collateral or adjust risk parameters for similar assets.",
            "explanation": "The rapid, defensive reaction from the broader DeFi ecosystem to de-risk and prevent similar contagion, a form of systemic self-preservation."
        }
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "official_inquiries_and_legal_assessments": {
        "regulatory_investigations": {
          "value": ["The U.S. SEC's investigation culminated in a lawsuit against Terraform Labs and Do Kwon in February 2023 for 'orchestrating a multi-billion dollar crypto asset securities fraud'", "South Korean prosecutors issued an arrest warrant for Do Kwon and key associates in September 2022 for violations of the Capital Markets Act"],
          "explanation": "The formal, lengthy process of state-level investigation and accusation, which provides an official narrative of wrongdoing and seeks to establish legal precedent."
        },
        "forensic_chain_analysis_reports": {
          "value": "Firms like Elliptic and Chainalysis published detailed reports tracing the flow of funds from the LFG Bitcoin sales and identifying wallet clusters of likely attackers/exploiters.",
          "explanation": "The independent, data-driven reconstruction of events by analytics firms, contributing to a more precise factual record and aiding legal processes."
        }
      },
      "adjustment_of_beliefs_and_norms": {
        "industry_discourse_shifts": {
          "value": ["The term 'algorithmic stablecoin' became almost taboo; the focus shifted entirely to fully collateralized (over-collateralized) or regulated models", "Intense debate emerged about the 'legal engineering' of DAOs and foundation structures to avoid liability"],
          "explanation": "The profound change in industry conversation, priorities, and risk appetites directly resulting from the trauma of the event."
        },
        "new_precautionary_norms_in_defi": {
          "value": ["'Depeg risk' became a primary metric in DeFi risk frameworks like Gauntlet", "Stress testing of protocols against 'black swan' liquidity events became standard practice for serious projects", "Greater emphasis on time-locked governance and multi-sig safeguards for treasury management"],
          "explanation": "The concrete, practical changes in how new protocols are designed, audited, and managed, representing the hard-won lessons being codified into practice."
        },
        "investor_behavior_changes": {
          "value": ["Retail investors demonstrated a 'flight to quality', favoring large-cap, established tokens and regulated entities post-collapse", "Due diligence checklists now routinely include 'sustainability of yields' and 'concentration of liquidity' as key items"],
          "explanation": "The long-term change in how capital allocators (both retail and institutional) assess risk in the crypto space, reflecting a loss of innocence."
        }
      },
      "long_term_impact_and_legacy": {
        "regulatory_acceleration": {
          "value": "The Terra collapse is widely cited as the catalyst for the EU's final push to pass MiCA (Markets in Crypto-Assets) regulation and for the U.S. Biden Administration's executive order and subsequent legislative proposals focused on stablecoins.",
          "explanation": "The event's role as a definitive policy-making trigger, proving the systemic risk of unregulated crypto to lawmakers worldwide."
        },
        "philosophical_reevaluation": {
          "value": "A sustained academic and industry critique of the 'governance token as collateral' model and the inherent fragility of reflexivity in financial systems, with papers and talks referencing Terra as a canonical case study.",
          "explanation": "The event's contribution to the deeper intellectual and economic understanding of decentralized systems, moving beyond hype to rigorous analysis."
        },
        "cultural_memory_and_analogy": {
          "value": "In crypto discourse, 'doing a Terra' or 'a Terra-like death spiral' became a shorthand for a catastrophic, fast-moving collapse of an over-leveraged system based on flawed tokenomics.",
          "explanation": "The event's entry into the lexicon and collective memory of the industry, serving as a permanent cautionary tale and a benchmark for failure."
        }
      }
    }
  }
}
"""