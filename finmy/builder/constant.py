from enum import Enum

# Other tokens that are not included in the content length, such as system prompt, response format, etc.
OTHER_TOKEN_NUM = 3000

# Estimate the time to complete the reconstruction per token in minutes
CLASS_BUILDE_ESTIMATE_PER_TOKEN_TIME_COST = 1e-4
AGENT_BUILDE_ESTIMATE_PER_TOKEN_TIME_COST = 3e-4


class BuildType(Enum):
    """Enumeration of build types for reconstruction tasks.

    - CLASS_BUILD: Used for reconstructing class definitions.
    - AGENT_BUILD: Used for reconstructing agent or workflow logic.
    """

    CLASS_BUILD = "class_build"
    AGENT_BUILD = "agent_build"
