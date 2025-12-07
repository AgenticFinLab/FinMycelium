"""
Definition of all elements based on the financial knowledge.
"""

from typing import Literal

# =============================================================================
# SupportedFinancialScenario: Canonical financial event archetypes
# grounded in academic theory and major historical precedents.
# =============================================================================

SupportedFinancialScenario = Literal[
    # Classic Deposit Institution Crises
    # -------------------------------
    # Bank Run: A self-fulfilling loss of confidence leading to mass withdrawal of funds from a solvent but illiquid institution.
    #   Example: Silicon Valley Bank collapse (2023); Northern Rock (2007).
    "Bank Run",
    # Fraudulent Investment Schemes
    # ----------------------------
    # Ponzi Scheme: A fraudulent operation paying returns to earlier investors from funds of later investors, not from profit.
    #   Example: Bernie Madoff investment scandal (2008); Stanford Financial (2009).
    "Ponzi Scheme",
    # Equity Market Dynamics
    # ----------------------
    # Short Squeeze: A rapid price increase triggered when short sellers cover positions amid rising prices and margin pressure.
    #   Example: GameStop short squeeze (2021); Volkswagen vs. Porsche (2008).
    "Short Squeeze",
    # Sovereign Credit Risk
    # ---------------------
    # Sovereign Default: A national government's failure to meet its debt obligations, either through non-payment or restructuring.
    #   Example: Greece sovereign debt crisis (2012); Argentina default (2001).
    "Sovereign Default",
    # Liquidity and Leverage Feedback Loops
    # -------------------------------------
    # Liquidity Spiral: A self-reinforcing cycle where asset price declines force leveraged entities to sell, further depressing prices.
    #   Example: Global financial crisis margin spiral (2008); March 2020 "dash for cash".
    "Liquidity Spiral",
    # Market Integrity Violations
    # ---------------------------
    # Market Manipulation: Deliberate actions to distort prices or create false market activity.
    #   Example: Jordan Belfort's Stratton Oakmont (1990s); spoofing cases prosecuted by DOJ.
    "Market Manipulation",
    # Regulatory and Structural Arbitrage
    # ----------------------------------
    # Regulatory Arbitrage: Exploiting differences in regulatory regimes to reduce capital, liquidity, or reporting requirements.
    #   Example: Pre-2008 shadow banking growth; crypto firms relocating jurisdictions.
    "Regulatory Arbitrage",
    # Credit Risk Realization
    # -----------------------
    # Credit Event: A trigger event (e.g., bankruptcy, failure to pay) as defined in credit derivatives contracts (e.g., ISDA).
    #   Example: Evergrande missed bond payments (2021); Detroit municipal bankruptcy (2013).
    "Credit Event",
    # Exogenous Systemic Disruptions
    # ------------------------------
    # Systemic Shock: A sudden, severe external shock that propagates across multiple financial markets and institutions.
    #   Example: Lehman Brothers bankruptcy (2008); global pandemic market crash (2020).
    "Systemic Shock",
    # Financial Statement Fraud
    # -------------------------
    # Accounting Fraud: Intentional misrepresentation of financial health through fictitious revenues, hidden liabilities, or forged documentation.
    #   Example: Enron off-balance-sheet entities (2001); Wirecard fake cash balances (2020).
    "Accounting Fraud",
    # Endogenous Leverage Cycles
    # --------------------------
    # Leverage Cycle Collapse: The implosion of a highly leveraged entity or sector when funding conditions reverse.
    #   Example: Archegos Capital blowup (2021); Long-Term Capital Management (1998).
    "Leverage Cycle Collapse",
    # Digital Asset Stability Failures
    # --------------------------------
    # Stablecoin Depeg: Loss of parity between a stablecoin and its reference asset (e.g., USD), triggering redemption pressure.
    #   Example: TerraUSD (UST) collapse (2022); USDC depeg during Silicon Valley Bank crisis (2023).
    "Stablecoin Depeg",
]

# =============================================================================
# EpisodeType: Atomic, time-stamped, observable actions or disclosures
# that occur during a financial event and have direct market or regulatory impact.
#
# Each type is:
# - Concrete (not abstract)
# - Verifiable from public sources (filings, news, market data)
# - Capital-market relevant (affects pricing, risk, or liquidity)
# =============================================================================

EpisodeType = Literal[
    # Information Disclosure Events
    # ----------------------------
    # Financial Statement Disclosure: Official release of financial reports (e.g., 10-K, annual report) disclosing financial position.
    #   Example: Enron's 2000 10-K concealed off-balance-sheet debt.
    "Financial Statement Disclosure",
    # Earnings Guidance Update: Management revision of future profit, revenue, or cash flow expectations.
    #   Example: Meta withdrew Q1 2022 guidance, triggering 26% stock drop.
    "Earnings Guidance Update",
    # Whistleblower Report: Insider disclosure of hidden risks, fraud, or misconduct to regulators or media.
    #   Example: Harry Markopolos' reports on Madoff (2000–2005).
    "Whistleblower Report",
    # Short Seller Report: Public research report alleging overvaluation, fraud, or operational risk, often with short position.
    #   Example: Muddy Waters' report on Luckin Coffee (2020).
    "Short Seller Report",
    # Auditor Resignation: Public announcement by external auditor of withdrawal from client engagement.
    #   Example: EY resigned from Wirecard (2020) after €1.9B "missing cash" revelation.
    "Auditor Resignation",
    # Rating Agency Downgrade: Official reduction in credit or issuer rating by a recognized agency.
    #   Example: S&P downgraded U.S. sovereign debt from AAA to AA+ (2011).
    "Rating Agency Downgrade",
    # Trading & Liquidity Actions
    # ---------------------------
    # Large-Scale Redemption: Mass withdrawal of capital by liability-holders (e.g., depositors, fund investors).
    #   Example: $42 billion withdrawn from Silicon Valley Bank in one day (2023-03-09).
    "Large-Scale Redemption",
    # Margin Call Issuance: Formal demand by lender for additional collateral due to position losses.
    #   Example: Archegos received margin calls from multiple prime brokers (2021-03-26).
    "Margin Call Issuance",
    # Forced Asset Liquidation: Compulsory sale of assets to meet obligations, often at distressed prices.
    #   Example: Archegos' $20B fire sale of ViacomCBS and Baidu shares (2021).
    "Forced Asset Liquidation",
    # Collateral Rehypothecation: Reuse of client collateral by broker for its own financing, increasing interconnected risk.
    #   Example: MF Global used customer funds as collateral for proprietary bets (2011).
    "Collateral Rehypothecation",
    # Prime Broker Position Unwind: Coordinated liquidation of a client’s leveraged positions by multiple prime brokers.
    #   Example: Goldman Sachs and Morgan Stanley unwound Archegos positions simultaneously (2021).
    "Prime Broker Position Unwind",
    # Retail Investor Panic Selling: Mass selling by non-institutional investors driven by fear or social media.
    #   Example: GameStop retail selling after price peak (2021); crypto retail outflows during Terra crash (2022).
    "Retail Investor Panic Selling",
    # Collateral Haircut Increase: Increase in collateral requirement (reduced loan-to-value) by lender due to rising risk.
    #   Example: Prime brokers raised haircuts on Archegos equity swaps before collapse (2021).
    "Collateral Haircut Increase",
    # Regulatory & Legal Actions
    # --------------------------
    # Regulatory Investigation Launch: Formal announcement by regulator of inquiry into potential violations.
    #   Example: SEC launched investigation into FTX (2022).
    "Regulatory Investigation Launch",
    # Securities Enforcement Action: Official penalty, fine, or cease-and-desist order issued by securities regulator.
    #   Example: SEC fined Goldman Sachs $3.9B over 1MDB scandal (2020).
    "Securities Enforcement Action",
    # Trading Suspension: Temporary halt of trading in a security by exchange or regulator.
    #   Example: NYSE suspended trading in Lehman Brothers shares (2008-09-15).
    "Trading Suspension",
    # Bankruptcy Filing: Legal submission to court for debt restructuring or liquidation (e.g., Chapter 11).
    #   Example: FTX filed for Chapter 11 bankruptcy (2022-11-11).
    "Bankruptcy Filing",
    # Court Receivership Order: Judicial appointment of third party to take control of entity’s assets.
    #   Example: FDIC placed Silicon Valley Bank into receivership (2023-03-10).
    "Court Receivership Order",
    # Central Bank Emergency Lending: Provision of liquidity by central bank outside normal channels.
    #   Example: Fed launched Bank Term Funding Program (BTFP) to backstop banks (2023-03-12).
    "Central Bank Emergency Lending",
    # Market Infrastructure Events
    # ----------------------------
    # Exchange Price Limit Hit: Activation of circuit breakers or daily price bands on an exchange.
    #   Example: Chinese stock exchanges hit 10% limit down on "Black Monday" (2015-08-24).
    "Exchange Price Limit Hit",
    # Clearing House Default Declaration: Official declaration that a member has failed to meet settlement obligations.
    #   Example: LCH declared Lehman Brothers in default (2008-09-15).
    "Clearing House Default Declaration",
    # Stablecoin Redemption Suspension: Issuer halts convertibility of stablecoin to fiat or reserves.
    #   Example: Celsius suspended withdrawals (2022-06-12); TerraUSD depeg (2022-05-09).
    "Stablecoin Redemption Suspension",
    # Cross-Margin Call Cascade: Chain reaction of margin calls across interconnected leveraged positions.
    #   Example: March 2020 "dash for cash" across equities, bonds, and commodities.
    "Cross-Margin Call Cascade",
    # Fraud & Manipulation Behaviors
    # ------------------------------
    # Fictitious Revenue Recording: Inflation of income through fake sales, round-tripping, or channel stuffing.
    #   Example: Enron booked sham energy trades as revenue (2001); Luckin Coffee inflated sales by 220% (2020).
    "Fictitious Revenue Recording",
    # Fake Cash Balance Fabrication: Invention of non-existent cash or cash equivalents on balance sheet.
    #   Example: Wirecard claimed €1.9B in cash held by third-party trustees — later found to not exist (2020).
    "Fake Cash Balance Fabrication",
    # Pump and Dump Trade Pattern: Coordinated buying to inflate price ("pump"), followed by rapid selling ("dump").
    #   Example: SEC charged 16 individuals in $100M+ Telegram pump-and-dump scheme (2023).
    "Pump and Dump Trade Pattern",
]

# =============================================================================
# ParticipantRole: Functional categories of actors in financial events,
# defined by institutional mandate, market function, or information position.
#
# Each role is:
# - Systemically distinct
# - Grounded in financial market structure
# - Observable across multiple event types
# =============================================================================

ParticipantRole = Literal[
    # Issuers & Operators
    # -------------------
    # Issuer: Entity that originates a financial obligation (e.g., equity, debt, deposit) or operates a financial platform.
    #   Example: Enron (corporate issuer); Silicon Valley Bank (deposit issuer); Tether (stablecoin issuer).
    "Issuer",
    # Fund Manager: Entity managing pooled investment vehicles, with discretion over portfolio allocation.
    #   Example: Madoff Investment Securities (Ponzi scheme); FTX's Alameda Research (hedge fund).
    "Fund Manager",
    # Platform Operator: Entity operating a digital financial platform (e.g., crypto exchange, stablecoin protocol).
    #   Example: Celsius Network; Terraform Labs; FTX.
    "Platform Operator",
    # Regulators & Public Authorities
    # -------------------------------
    # Financial Regulator: Government authority with statutory power to supervise financial institutions (prudential regulation).
    #   Example: Federal Reserve; European Central Bank; China Banking and Insurance Regulatory Commission.
    "Financial Regulator",
    # Central Bank: Monetary authority acting as lender of last resort and systemic stabilizer.
    #   Example: U.S. Federal Reserve; European Central Bank; Bank of Japan.
    "Central Bank",
    # Deposit Insurance Agency: Public agency providing insurance on deposit liabilities to prevent bank runs.
    #   Example: Federal Deposit Insurance Corporation (FDIC); Canada Deposit Insurance Corporation (CDIC).
    "Deposit Insurance Agency",
    # Securities Enforcement Authority: Agency with mandate to investigate and penalize securities law violations.
    #   Example: U.S. Securities and Exchange Commission (SEC); UK Financial Conduct Authority (FCA) Enforcement.
    "Securities Enforcement Authority",
    # Market Participants
    # -------------------
    # Retail Investor: Non-institutional individual investor trading for personal account.
    #   Example: Robinhood users during GameStop rally (2021); crypto retail buyers.
    "Retail Investor",
    # Institutional Investor: Professional entity investing on behalf of others (pension funds, asset managers).
    #   Example: BlackRock; CalPERS; mutual funds.
    "Institutional Investor",
    # Hedge Fund: Private investment fund using leverage, derivatives, and short positions for absolute returns.
    #   Example: Citadel; Melvin Capital; Archegos Capital.
    "Hedge Fund",
    # Prime Broker: Investment bank providing custody, financing, and clearing to hedge funds and large traders.
    #   Example: Goldman Sachs; Morgan Stanley; Credit Suisse.
    "Prime Broker",
    # Market Maker: Entity providing continuous two-sided quotes to ensure market liquidity.
    #   Example: Jane Street; Virtu Financial; designated market makers on NYSE.
    "Market Maker",
    # Short Seller: Investor profiting from price declines by selling borrowed securities.
    #   Example: Muddy Waters Research; Hindenburg Research; activist short funds.
    "Short Seller",
    # Liquidity Provider: Entity supplying capital to markets (e.g., on decentralized exchanges or OTC desks).
    #   Example: Uniswap liquidity pools; OTC market makers in bonds.
    "Liquidity Provider",
    # Information Intermediaries
    # --------------------------
    # External Auditor: Independent firm verifying financial statement accuracy and compliance.
    #   Example: PricewaterhouseCoopers (Enron); Ernst & Young (Wirecard).
    "External Auditor",
    # Credit Rating Agency: Entity assessing creditworthiness of issuers or instruments.
    #   Example: Standard & Poor's; Moody's Investors Service; Fitch Ratings.
    "Credit Rating Agency",
    # Financial News Media: Organization disseminating financial news, data, and analysis to public.
    #   Example: Bloomberg; Reuters; Financial Times.
    "Financial News Media",
    # Independent Research Firm: Non-bank entity producing investment research, often skeptical or forensic.
    #   Example: Muddy Waters Research; Iceberg Research; Hindenburg Research.
    "Independent Research Firm",
    # Financial Infrastructure
    # ------------------------
    # Central Counterparty (CCP): Institution that interposes itself between buyers and sellers to guarantee trade settlement.
    #   Example: LCH (for rates); CME Clearing (for commodities); OCC (for options).
    "Central Counterparty (CCP)",
    # Custodian Bank: Institution holding financial assets for safekeeping on behalf of clients.
    #   Example: BNY Mellon; JPMorgan Chase; State Street.
    "Custodian Bank",
    # Payment System Operator: Entity operating system for interbank or retail payment settlement.
    #   Example: CHIPS (Clearing House Interbank Payments System); FedWire; SWIFT.
    "Payment System Operator",
]
