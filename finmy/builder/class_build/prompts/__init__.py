"""
Financial Fraud Pattern Prompts Package
Automatically collects all prompt functions from submodules
"""

from . import (
    classify,
    ponzi_scheme,
    pyramid_scheme,
    pump_and_dump,
    market_manipulation,
    accounting_fraud,
    cryptocurrency_ico_scam,
    forex_binary_options_fraud,
    advance_fee_fraud,
    affinity_fraud,
    embezzlement_misappropriation_of_funds,
    bank_run,
    short_squeeze,
    sovereig_default,
    liquidity_spiral,
    regulatory_arbitrage,
    credit_event,
    systemic_shock,
    leverage_cycle_collapse,
    stablecoin_depeg,
    other_financial_scam
)

# Define __all__ for wildcard imports
__all__ = [
    'classify',
    'ponzi_scheme',
    'pyramid_scheme',
    'pump_and_dump',
    'market_manipulation',
    'accounting_fraud',
    'cryptocurrency_ico_scam',
    'forex_binary_options_fraud',
    'advance_fee_fraud',
    'affinity_fraud',
    'embezzlement_misappropriation_of_funds',
    'bank_run',
    'short_squeeze',
    'sovereig_default',
    'liquidity_spiral',
    'regulatory_arbitrage',
    'credit_event',
    'systemic_shock',
    'leverage_cycle_collapse',
    'stablecoin_depeg',
    'other_financial_scam',
]