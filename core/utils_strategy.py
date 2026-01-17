from pydantic import BaseModel, Field, field_validator
from typing import List, Union, Optional, Literal, Dict, Any

# 1. Indicator Definitions
class IndicatorParam(BaseModel):
    name: str # e.g., 'period', 'std_dev'
    value: Union[int, float, str]

class IndicatorConfig(BaseModel):
    name: str # e.g., 'RSI', 'SMA', 'MACD', 'PRICE', 'VOLUME'
    params: Dict[str, Union[int, float, str]] = Field(default_factory=dict)

# 2. Logic Nodes
class Condition(BaseModel):
    # Left side: usually an indicator
    indicator: IndicatorConfig 
    
    # Operator
    operator: Literal['>', '<', '=', '>=', '<=', 'CROSS_UP', 'CROSS_DOWN']
    
    # Right side: can be a static value or another indicator
    # e.g., RSI > 30 (static) OR SMA_5 > SMA_20 (indicator)
    value_type: Literal['STATIC', 'INDICATOR']
    value: Union[float, int, IndicatorConfig]

class LogicNode(BaseModel):
    connector: Literal['AND', 'OR']
    conditions: List[Union['LogicNode', 'Condition']] # Recursive
    not_logic: bool = False # If True, applies NOT(...) to the entire group

# 3. Strategy Configuration (Top Level)
class DCAConfig(BaseModel):
    enabled: bool = False
    type: Literal['fixed_amount', 'fixed_quantity'] = 'fixed_amount'
    amount: float = 100000 # KRW or USD
    interval: Literal['daily', 'weekly', 'monthly', 'condition_based'] = 'monthly'
    # Optional logic for checking "when to buy" if interval is 'condition_based' matches buy_conditions generally, 
    # but DCA might have specific triggers (e.g. only buy if price drop > 5%)
    # For simplicity, we can reuse buy_conditions or add a specific condition here.

class StrategyConfig(BaseModel):
    buy_conditions: LogicNode
    sell_conditions: Optional[LogicNode] = None # Optional: Sell logic might not exist for buy-and-hold
    dca_config: DCAConfig = Field(default_factory=DCAConfig)

    @field_validator('sell_conditions')
    def validate_sell_conditions(cls, v):
        # Additional validation if needed
        return v
